# src/rma/services.py
from datetime import datetime, timezone
from fastapi import HTTPException
from src.utils.db import db
from src.rma.schemas import RmaCreateRequest
import random
from collections import defaultdict

async def generate_unique_rma_number() -> str:
    """Helper untuk generate format nomor RMA otomatis (Contoh: RMA-2026-8912)"""
    year = datetime.now().year
    while True:
        random_digits = random.randint(1000, 9999)
        rma_number = f"RMA-{year}-{random_digits}"
        # Cek apakah sudah ada di database untuk menghindari duplikasi
        existing = await db.rma_request.find_unique(where={"rma_number": rma_number})
        if not existing:
            return rma_number


async def create_new_rma(payload: RmaCreateRequest):
    """Logika Bisnis untuk membuat tiket pengajuan RMA baru dari lapangan"""
    rma_number = await generate_unique_rma_number()
    
    new_rma = await db.rma_request.create(
        data={
            "rma_number": rma_number,
            "field_tech_id": payload.field_tech_id,
            "part_number": payload.part_number,
            "faulty_serial_number": payload.faulty_serial_number,
            "dop_id": payload.dop_id,
            "status": "PENDING_APPROVAL"
        }
    )
    return new_rma


async def approve_rma_request(rma_id: str, courier_id: str):
    """Logika Bisnis untuk Approval RMA + Validasi Durasi SLA 30 Menit & Penunjukan PSS Logistik"""
    # 1. Cari data RMA berdasarkan ID
    rma = await db.rma_request.find_unique(where={"id": rma_id})
    if not rma:
        return None, "RMA ticket not found", 0.0, "NOT_FOUND"
        
    if rma.status != "PENDING_APPROVAL":
        return None, f"Cannot approve RMA with current status: {rma.status}", 0.0, "INVALID_STATUS"

    # 2. Validasi apakah courier_id benar-benar ada dan rolenya adalah LOGISTIC_PARTNER
    courier = await db.user.find_unique(where={"id": courier_id})
    if not courier or courier.role != "LOGISTIC_PARTNER":
        return None, "User ID yang ditunjuk bukan PSS Logistik (LOGISTIC_PARTNER) yang sah", 0.0, "INVALID_COURIER"

    # 3. Hitung durasi waktu dari created_at sampai SEKARANG (SLA Checker)
    now = datetime.now(timezone.utc)
    created_time = rma.created_at.replace(tzinfo=timezone.utc)
    
    duration = now - created_time
    duration_minutes = duration.total_seconds() / 60.0
    
    # Tentukan apakah memenuhi SLA (Maksimal 30 menit sesuai diagram)
    sla_status = "WITHIN_SLA" if duration_minutes <= 30.0 else "SLA_BREACHED"

    # 4. Update status tiket RMA di database Neon (Langsung SHIPPED karena kurir langsung jalan)
    updated_rma = await db.rma_request.update(
        where={"id": rma_id},
        data={
            "courier_id": courier_id,
            "status": "SHIPPED",
            "approved_at": now
        }
    )
    
    message = f"RMA successfully approved. PSS Logistik {courier.name} ditugaskan membawa barang."
    if sla_status == "SLA_BREACHED":
        # 🛡️ FITUR LAMA DIJAGA: Pesan peringatan SLA Breached dipertahankan
        message += " (Breached the 30-minute SLA target)"
    
    return updated_rma, message, round(duration_minutes, 2), sla_status


async def process_good_part_pickup(rma_id: str, good_serial_number: str):
    """
    Logika Langkah 4: Konfirmasi pengambilan barang bagus di DOP oleh Field Tech.
    Mengambil data relasi field_tech untuk keperluan otomasi email feedback pada pengingat pertama.
    """
    rma = await db.rma_request.find_unique(
        where={"id": rma_id},
        include={"field_tech": True}
    )
    if not rma:
        return None, "RMA ticket not found", None, None
        
    if rma.status != "SHIPPED":
        return None, f"Invalid state transitions from {rma.status} to GOOD_PART_RECEIVED. Barang belum dikirim oleh kurir.", None, None

    updated_rma = await db.rma_request.update(
        where={"id": rma_id},
        data={
            "good_serial_number": good_serial_number,
            "status": "GOOD_PART_RECEIVED"
        }
    )
    
    tech_email = rma.field_tech.email if rma.field_tech else "field.tech@ericsson.com"
    return updated_rma, "Pickup confirmed. Status updated to GOOD_PART_RECEIVED.", tech_email, rma.rma_number


async def process_faulty_part_return(rma_id: str):
    """Logika Langkah 5: Konfirmasi barang rusak diserahkan ke kurir di DOP (Status dialihkan ke FAULTY_PART_RETURNED)"""
    rma = await db.rma_request.find_unique(where={"id": rma_id})
    if not rma:
        return None, "RMA ticket not found"
    if rma.status != "GOOD_PART_RECEIVED":
        return None, "Cannot return faulty part before picking up the good part"

    # 🔄 DISESUAIKAN: Status dialihkan ke FAULTY_PART_RETURNED terlebih dahulu sesuai alur terbaru (tidak langsung close otomatis)
    updated_rma = await db.rma_request.update(
        where={"id": rma_id},
        data={
            "status": "FAULTY_PART_RETURNED"
        }
    )
    return updated_rma, "Faulty part handed over to PSS Logistic. Status updated to FAULTY_PART_RETURNED."


async def close_rma_by_engineer(rma_id: str):
    """✨ FUNGSI BARU: E/// Engineers melakukan close tiket secara absolut setelah komponen rusak divalidasi aman di pusat"""
    rma = await db.rma_request.find_unique(where={"id": rma_id})
    if not rma:
        return None, "RMA ticket not found"
    if rma.status != "FAULTY_PART_RETURNED":
        return None, f"Tiket tidak dapat di-close sebelum komponen rusak diserahkan oleh teknisi. Status saat ini: {rma.status}"

    now = datetime.now(timezone.utc)
    updated_rma = await db.rma_request.update(
        where={"id": rma_id},
        data={
            "status": "CLOSED",
            "closed_at": now
        }
    )
    return updated_rma, "Faulty part received at warehouse. RMA ticket is now officially CLOSED by Engineer."


async def trigger_first_reminder_with_feedback(rma_id: str, rma_number: str, tech_email: str):
    """Simulasi Background Worker: Mengirimkan email pengingat pengembalian barang rusak (Reminder #1)"""
    import asyncio
    await asyncio.sleep(2)
    
    feedback_url = f"http://localhost:3000/rma/{rma_id}/feedback"
    
    print("\n----------------------------------------------------------------------")
    print(f"📧 [NOTIFICATION WORKER] -> Reminder #1 dikirim ke: {tech_email}")
    print(f"📌 Subjek: [Ericsson RMA] Pengingat Pengembalian Komponen Rusak ({rma_number})")
    print(f"📝 Halo Teknisi, unit bagus telah Anda ambil. Mohon segera serahkan kembali unit rusak Anda ke DOP.")
    print(f"⭐ Sembari menunggu, mohon luangkan waktu 1 menit untuk menilai performa portal web kami di tautan berikut:")
    print(f"🔗 Tautan Feedback: {feedback_url}")
    print("----------------------------------------------------------------------\n")


async def submit_rma_feedback(rma_id: str, rating: int, feedback_notes: str):
    """Logika bisnis untuk menyimpan rating kepuasan aplikasi dari teknisi lapangan"""
    rma = await db.rma_request.find_unique(where={"id": rma_id})
    if not rma:
        raise HTTPException(status_code=404, detail="Tiket RMA tidak ditemukan")
        
    if rma.status in ["PENDING_APPROVAL", "SHIPPED"]:
        raise HTTPException(status_code=400, detail="Feedback hanya bisa diisi setelah proses Good Part Pickup selesai.")

    updated_rma = await db.rma_request.update(
        where={"id": rma_id},
        data={
            "rating": rating,
            "feedback_notes": feedback_notes
        }
    )
    return updated_rma


async def get_rma_heatmap_data():
    """Mengambil koordinat lokasi DOP Site beserta intensitas frekuensi RMA untuk Leaflet.heat"""
    rma_list = await db.rma_request.find_many(
        include={"dop": True}
    )
    
    site_groups = defaultdict(lambda: {"lat": 0.0, "lng": 0.0, "name": "", "count": 0})
    
    for rma in rma_list:
        if rma.dop:
            s_id = rma.dop_id
            
            # 🛡️ SINKRONISASI PRISMA SCHEMA: Kolom database Anda adalah rma.dop.name (bukan site_name)
            site_groups[s_id]["name"] = rma.dop.name
            site_groups[s_id]["count"] += 1
            
            # Karena koordinat bertipe Unsupported PostGIS, kita ambil fallback lat/long koordinat 
            # regional Bandung Raya (lokasi Kampus Telkom University) agar data bisa digambar dinamis di Leaflet FE teman kamu.
            # Pada implementasi lanjut, ini bisa dibaca via fungsi raw SQL ST_X / ST_Y dari PostGIS.
            site_groups[s_id]["lat"] = -6.9744 + (random.uniform(-0.02, 0.02))
            site_groups[s_id]["lng"] = 107.6316 + (random.uniform(-0.02, 0.02))
            
    heatmap_data = [
        {
            "latitude": info["lat"],
            "longitude": info["lng"],
            "site_name": info["name"],
            "intensity": info["count"]
        }
        for info in site_groups.values()
    ]
    
    return heatmap_data


async def get_sla_analytics_dashboard():
    """Menghitung metrik performa SLA, durasi approval, dan tren pelanggaran bulanan"""
    rma_list = await db.rma_request.find_many(
        where={
            "approved_at": {"not": None}
        }
    )
    
    if not rma_list:
        return {
            "total_rma_processed": 0,
            "overall_avg_approval_minutes": 0.0,
            "total_sla_breaches": 0,
            "overall_breach_rate_percentage": 0.0,
            "monthly_trends": []
        }
        
    total_processed = len(rma_list)
    total_breaches = 0
    total_duration = 0.0
    
    monthly_data = defaultdict(lambda: {"total_duration": 0.0, "count": 0, "breaches": 0})
    
    for rma in rma_list:
        created = rma.created_at.replace(tzinfo=timezone.utc)
        approved = rma.approved_at.replace(tzinfo=timezone.utc)
        duration_minutes = (approved - created).total_seconds() / 60.0
        
        total_duration += duration_minutes
        is_breach = duration_minutes > 30.0
        if is_breach:
            total_breaches += 1
            
        month_key = rma.created_at.strftime("%Y-%m")
        monthly_data[month_key]["total_duration"] += duration_minutes
        monthly_data[month_key]["count"] += 1
        if is_breach:
            monthly_data[month_key]["breaches"] += 1

    monthly_trends = []
    for month, stats in sorted(monthly_data.items()):
        avg_dur = stats["total_duration"] / stats["count"]
        breach_rate = (stats["breaches"] / stats["count"]) * 100.0
        monthly_trends.append({
            "month": month,
            "avg_duration_minutes": round(avg_dur, 2),
            "total_requests": stats["count"],
            "breach_count": stats["breaches"],
            "breach_rate_percentage": round(breach_rate, 2)
        })
        
    overall_avg = total_duration / total_processed
    overall_breach_rate = (total_breaches / total_processed) * 100.0
    
    return {
        "total_rma_processed": total_processed,
        "overall_avg_approval_minutes": round(overall_avg, 2),
        "total_sla_breaches": total_breaches,
        "overall_breach_rate_percentage": round(overall_breach_rate, 2),
        "monthly_trends": monthly_trends
    }

async def fetch_all_rmas():
    """
    Mengambil semua data pengajuan RMA dari database Neon.
    Diurutkan berdasarkan waktu pembuatan terbaru untuk kebutuhan table feed di Frontend.
    """
    return await db.rma_request.find_many(
        order={
            "created_at": "desc"
        }
    )


async def fetch_rma_by_id(rma_id: str):
    """
    Mencari satu record detail data RMA berdasarkan Primary Key (ID).
    Digunakan saat Frontend mengklik salah satu baris baris tabel untuk melihat detail status.
    """
    return await db.rma_request.find_unique(
        where={
            "id": rma_id
        }
    )