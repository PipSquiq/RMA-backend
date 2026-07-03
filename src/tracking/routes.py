# src/tracking/routes.py
from fastapi import APIRouter, HTTPException, Depends, status
from src.tracking.schemas import LocationPingRequest, TrackingHistoryContainerResponse
from src.tracking import services as tracking_services
from src.auth.guards import RoleChecker
from src.utils.db import db

router = APIRouter()

@router.post("/ping", status_code=status.HTTP_201_CREATED)
async def courier_ping_location(payload: LocationPingRequest, current_courier=Depends(RoleChecker(["LOGISTIC_PARTNER"]))):
    """
    Endpoint berkala (Tiap 3-5 menit) otomatis dari HP Kurir (PSS Logistik) untuk mengirim koordinat spasial.
    Hanya menerima ping dari PSS Logistik yang valid dan terdaftar pada rma_id terkait.
    """
    # 1. Ambil data RMA untuk memverifikasi siapa kurir yang ditugaskan
    rma = await db.rma_request.find_unique(where={"id": payload.rma_id})
    if not rma:
        raise HTTPException(status_code=404, detail="Tiket RMA tidak ditemukan")

    # 2. Validasi status penanganan rute logistik
    if rma.status != "SHIPPED":
        raise HTTPException(
            status_code=400, 
            detail=f"Pelacakan ditolak. Tiket tidak dalam status pengiriman (Status saat ini: {rma.status})"
        )

    # 3. 🛡️ KUNCI VALIDASI: Memastikan ID kurir dari Token JWT cocok dengan courier_id penugasan tiket di DB
    if rma.courier_id != current_courier["id"]:
        raise HTTPException(
            status_code=403, 
            detail="Akses ditolak. Anda bukan PSS Logistik yang ditugaskan untuk mengantar unit RMA ini!"
        )

    try:
        # 4. Amankan penulisan koordinat spasial ke tabel PostGIS melalui tracking services
        await tracking_services.save_location_ping(payload, courier_id=current_courier["id"])
        return {"success": True, "message": "Location ping recorded successfully for PSS Logistic."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal memproses data spasial ke database: {str(e)}")


@router.get("/{rma_id}/history", response_model=TrackingHistoryContainerResponse, status_code=status.HTTP_200_OK)
async def get_live_tracking_history(rma_id: str, current_user=Depends(RoleChecker(["FIELD_TECH", "ENGINEER", "CUST_ADMIN"]))):
    """
    Endpoint Peta ala Go-Jek: Menarik seluruh riwayat perjalanan kurir untuk digambar ke 
    Peta Leaflet.js milik Field Tech (atau dashboard) dengan struktur response yang konsisten.
    """
    try:
        # Ambil log koordinat ter-format dari service layer
        history_data = await tracking_services.get_rma_tracking_history(rma_id)
        
        # 🛡️ STRUKTUR RESPONSE LAMA DIJAGA: Tetap dibungkus objek {"success": True, "data": ...}
        # Model ini valid dan lolos sensor skema TrackingHistoryContainerResponse
        return {
            "success": True,
            "data": history_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal memproses data history tracking: {str(e)}")