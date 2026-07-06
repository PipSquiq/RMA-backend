# src/rma/routes.py
from fastapi import APIRouter, HTTPException, status, BackgroundTasks, Depends
from src.rma.schemas import (
    RmaCreateRequest, 
    RmaCreateResponse, 
    RmaApproveResponse, 
    RmaApprovalRequest,
    RmaFeedbackSubmitRequest,
    HeatmapPoint, 
    SlaDashboardResponse,
    RmaResponseData
)
from src.rma import services as rma_services
from src.rma.integration import trigger_external_customer_ticket
from src.auth.guards import RoleChecker  # Guard pengaman RBAC
from pydantic import BaseModel
from typing import List

router = APIRouter()

class PickupBody(BaseModel):
    good_serial_number: str


@router.post("/", response_model=RmaCreateResponse, status_code=status.HTTP_201_CREATED)
async def open_rma(payload: RmaCreateRequest, current_user=Depends(RoleChecker(["FIELD_TECH"]))):
    """Endpoint Langkah 1: Hanya Field Tech yang bisa membuka request RMA baru dari lapangan"""
    try:
        new_rma = await rma_services.create_new_rma(payload)
        return {
            "success": True,
            "message": "RMA request created successfully.",
            "data": new_rma
        }
    except Exception as e:
        if "Unique constraint failed" in str(e):
            raise HTTPException(status_code=400, detail="Faulty serial number has already been submitted in another RMA.")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{rma_id}/approve", response_model=RmaApproveResponse)
async def approve_rma(rma_id: str, payload: RmaApprovalRequest, background_tasks: BackgroundTasks, current_user=Depends(RoleChecker(["ENGINEER"]))):
    """Endpoint Langkah 2 & 3: Hanya E/// Engineer yang bisa menyetujui RMA + Otomatisasi Request Ship Order & Tiket Eksternal"""
    
    # 1. Jalankan logika approval utama dengan menyertakan courier_id dari payload body
    updated_rma, message, duration, sla_status = await rma_services.approve_rma_request(
        rma_id=rma_id,
        courier_id=str(payload.courier_id)
    )
    
    if not updated_rma:
        raise HTTPException(status_code=400, detail=message)
        
    # 2. Jalankan background task integrasi eksternal ke Customer System
    background_tasks.add_task(
        trigger_external_customer_ticket,
        rma_id=updated_rma.id,
        rma_number=updated_rma.rma_number,
        faulty_sn=updated_rma.faulty_serial_number
    )
        
    return {
        "success": True,
        "message": f"{message} (Customer System ticket creation triggered in background)",
        "sla_status": sla_status,
        "duration_minutes": duration,
        "data": updated_rma
    }


@router.post("/{rma_id}/pickup-confirmation")
async def confirm_pickup(rma_id: str, body: PickupBody, background_tasks: BackgroundTasks, current_user=Depends(RoleChecker(["FIELD_TECH", "LOGISTIC_PARTNER"]))):
    """Endpoint Langkah 4: Dual Konfirmasi serah terima barang bagus di DOP + Otomatisasi Reminder Pertama & Link Feedback"""
    
    # 1. Tangkap pembaruan tuple data rma, email teknisi, dan nomor rma dari service layer
    updated_rma, message, tech_email, rma_number = await rma_services.process_good_part_pickup(
        rma_id=rma_id, 
        good_serial_number=body.good_serial_number
    )
    
    if not updated_rma:
        raise HTTPException(status_code=400, detail=message)
        
    # 2. Daftarkan tugas pengiriman pengingat pertama + link feedback ke background worker
    background_tasks.add_task(
        rma_services.trigger_first_reminder_with_feedback,
        rma_id=updated_rma.id,
        rma_number=rma_number,
        tech_email=tech_email
    )
    
    return {"success": True, "message": message, "data": updated_rma}


@router.post("/{rma_id}/return-faulty")
async def confirm_faulty_return(rma_id: str, current_user=Depends(RoleChecker(["LOGISTIC_PARTNER"]))):
    """Endpoint Langkah 5: Hanya PSS Logistik yang mengonfirmasi bahwa unit rusak dari teknisi sudah diamankan di DOP"""
    updated_rma, message = await rma_services.process_faulty_part_return(rma_id)
    if not updated_rma:
        raise HTTPException(status_code=400, detail=message)
    return {"success": True, "message": message, "data": updated_rma}


@router.patch("/{rma_id}/close")
async def close_rma_ticket(rma_id: str, current_user=Depends(RoleChecker(["ENGINEER"]))):
    """Endpoint Akhir: Hanya E/// Engineer yang bisa menutup tiket secara resmi setelah barang rusak dipastikan aman"""
    updated_rma, message = await rma_services.close_rma_by_engineer(rma_id)
    if not updated_rma:
        raise HTTPException(status_code=400, detail=message)
    return {"success": True, "message": message, "data": updated_rma}


@router.post("/{rma_id}/feedback", status_code=status.HTTP_200_OK)
async def submit_feedback(rma_id: str, payload: RmaFeedbackSubmitRequest, current_user=Depends(RoleChecker(["FIELD_TECH"]))):
    """Endpoint Feedback: Hanya Field Tech yang berhak mengisi kuesioner dari tautan Reminder #1"""
    try:
        updated_rma = await rma_services.submit_rma_feedback(
            rma_id=rma_id,
            rating=payload.rating,
            feedback_notes=payload.feedback_notes
        )
        return {
            "success": True,
            "message": "Terima kasih atas feedback Anda! Penilaian Anda membantu kami meningkatkan performa sistem portal.",
            "data": updated_rma
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- ENDPOINT ANALITIK DASHBOARD (Hanya ENGINEER & CUST_ADMIN) ---

@router.get("/analytics/heatmap", response_model=List[HeatmapPoint])
async def get_heatmap_analytics(current_user=Depends(RoleChecker(["ENGINEER", "CUST_ADMIN"]))):
    """Endpoint Analitik: Menarik data koordinat sebaran bad-batch hardware untuk Leaflet.heat"""
    try:
        data = await rma_services.get_rma_heatmap_data()
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal memuat data heatmap: {str(e)}")


@router.get("/analytics/sla-dashboard", response_model=SlaDashboardResponse)
async def get_sla_dashboard_metrics(current_user=Depends(RoleChecker(["ENGINEER", "CUST_ADMIN"]))):
    """Endpoint Analitik: Memantau visualisasi grafik tren durasi approval 30 menit tim Engineer"""
    try:
        data = await rma_services.get_sla_analytics_dashboard()
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal memuat metrik dashboard: {str(e)}")

@router.get("", response_model=List[RmaResponseData])
async def get_all_rma_list(current_user=Depends(RoleChecker(["FIELD_TECH", "ENGINEER", "LOGISTIC_PARTNER", "DOP_STAFF", "CUST_ADMIN"]))):
    """Endpoint: Mengambil semua daftar data RMA (Urut dari yang terbaru)"""
    try:
        data = await rma_services.fetch_all_rmas()
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal mengambil daftar RMA: {str(e)}")


@router.get("/{rma_id}", response_model=RmaResponseData)
async def get_rma_detail_by_id(rma_id: str, current_user=Depends(RoleChecker(["FIELD_TECH", "ENGINEER", "LOGISTIC_PARTNER", "DOP_STAFF", "CUST_ADMIN"]))):
    """Endpoint: Mengambil detail data RMA spesifik berdasarkan ID"""
    data = await rma_services.fetch_rma_by_id(rma_id)
    if not data:
        raise HTTPException(status_code=404, detail="Data RMA tidak ditemukan.")
    return data