# src/rma/scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from src.utils import db as db_module 

scheduler = AsyncIOScheduler()

async def check_and_generate_replenishment():
    """
    Cron Job Logic: Berjalan 2x sehari (Jam 12 & Jam 17).
    Mendeteksi stok DOP di bawah threshold dan otomatis menerbitkan Replenish Order Draft.
    """
    print("🕒 [Cron Job] Memulai pengecekan otomatis stok komponen di seluruh DOP (2x Daily L3 to L4)...")
    
    # Ambil instance prisma dari modul utils/db.py secara dinamis
    db = getattr(db_module, 'db', getattr(db_module, 'prisma', getattr(db_module, 'prisma_client', None)))
    
    if db is None:
        print("❌ [Cron Job] Gagal memuat instance Prisma dari src/utils/db.py!")
        return

    try:
        # 1. Ambil semua inventori yang jumlah stoknya <= batas minimum threshold menggunakan Raw SQL
        raw_criticals = await db.query_raw(
            '''
            SELECT id, dop_id, part_number, stock_good_qty, min_threshold 
            FROM dop_inventories 
            WHERE stock_good_qty <= min_threshold
            '''
        )
        
        if not raw_criticals:
            print("✅ [Cron Job] Semua stok aman. Tidak ada DOP yang menyentuh batas minimum threshold.")
            return

        print(f"⚠️ [Cron Job] Terdeteksi {len(raw_criticals)} item stok kritis di bawah threshold aman!")

        # Deteksi secara dinamis model tabel replenish_order yang terdaftar di Prisma Client Python Anda
        replenish_table = getattr(db, 'replenish_order', getattr(db, 'replenishorder', None))
        if replenish_table is None:
            print("❌ [Cron Job] Atribut model replenish_order tidak ditemukan pada objek Prisma!")
            return

        for item in raw_criticals:
            dop_id = item['dop_id']
            part_number = item['part_number']
            stock_good_qty = item['stock_good_qty']
            min_threshold = item['min_threshold']

            # Ambil data tambahan (DOP & Part) secara asinkron menggunakan ORM agar data nama terisi
            dop_detail = await db.dop_site.find_unique(where={"id": dop_id})
            part_detail = await db.part.find_unique(where={"part_number": part_number})
            
            dop_name = dop_detail.name if dop_detail else "Unknown DOP"
            part_name = part_detail.name if part_detail else "Unknown Part"

            # Hitung berapa kuantitas yang harus dikirim dari L3/L4 (kita isi ulang sampai batas threshold + 5)
            ideal_stock = min_threshold + 5
            qty_needed = ideal_stock - stock_good_qty
            
            # Cek apakah hari ini sudah pernah dibuatkan draf untuk item tersebut agar tidak double draft
            existing_draft = await replenish_table.find_first(
                where={
                    "dop_id": dop_id,
                    "part_number": part_number,
                    "status": "DRAFT"
                }
            )
            
            if existing_draft:
                print(f"ℹ️ [Cron Job] Draf Replenish Order untuk {part_name} di {dop_name} sudah ada sebelumnya. Skip.")
                continue
                
            # 2. Buat Draf Order Pengisian Ulang secara otomatis menggunakan tabel objek hasil deteksi dinamis
            new_order = await replenish_table.create(
                data={
                    "dop_id": dop_id,
                    "part_number": part_number,
                    "quantity_to_ship": qty_needed,
                    "status": "DRAFT"
                }
            )
            print(f"🚀 [Cron Job] Selesai Mengonstruksi Draf Replenish Order Baru [ID: {new_order.id}]!")
            print(f"   👉 Kirim {qty_needed} unit {part_number} dari L3/L4 Hub menuju {dop_name}.")
            
    except Exception as e:
        print(f"❌ [Cron Job] Terjadi kesalahan fatal pada scheduler: {e}")
