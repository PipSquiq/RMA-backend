# src/tracking/services.py
from src.utils.db import db
from src.tracking.schemas import LocationPingRequest

async def save_location_ping(payload: LocationPingRequest, courier_id: str) -> bool:
    """
    Menyimpan koordinat ping dari PWA secara berkala ke database Neon.
    Menggunakan fungsi ST_SetSRID dan ST_MakePoint milik PostGIS demi akurasi spasial.
    """
    # Catatan: Di PostGIS ST_MakePoint menerima parameter (Longitude/X, Latitude/Y)
    query = """
        INSERT INTO location_logs (rma_id, user_id, battery_level, coordinate, pinged_at)
        VALUES ($1::uuid, $2::uuid, $3, ST_SetSRID(ST_MakePoint($4, $5), 4326), NOW())
    """
    
    await db.execute_raw(
        query,
        payload.rma_id,
        courier_id,  # 🛡️ Diambil dari token JWT yang sudah tervalidasi di route layer
        payload.battery_level,
        payload.longitude,  # X coordinate (Long)
        payload.latitude    # Y coordinate (Lat)
    )
    return True


async def get_rma_tracking_history(rma_id: str):
    """
    Mengambil lokasi terakhir dan riwayat koordinat terurut berdasarkan waktu
    untuk dikirim ke Frontend (Leaflet.js map) untuk penggambaran polyline rute.
    """
    # 🛠️ MEMPERTAHANKAN LOGIKA ASLI: Menggunakan fungsi ST_Y & ST_X native PostGIS
    query = """
        SELECT 
            id,
            user_id,
            battery_level,
            ST_Y(coordinate::geometry) as latitude,
            ST_X(coordinate::geometry) as longitude,
            pinged_at
        FROM location_logs
        WHERE rma_id = $1::uuid
        ORDER BY pinged_at ASC
    """
    
    raw_logs = await db.query_raw(query, rma_id)
    
    if not raw_logs:
        return {
            "rma_id": rma_id,
            "latest_position": None,
            "location_history": []
        }
    
    # Format data riwayat untuk mempermudah teman FE membuat jalur garis (Polyline)
    location_history = [
        {
            "latitude": log["latitude"],
            "longitude": log["longitude"],
            "timestamp": log["pinged_at"].isoformat() if hasattr(log["pinged_at"], "isoformat") else str(log["pinged_at"])
        }
        for log in raw_logs
    ]
    
    # Ambil posisi paling terakhir (index terakhir karena sudah di-ORDER BY ASC)
    latest_log = raw_logs[-1]
    latest_position = {
        "latitude": latest_log["latitude"],
        "longitude": latest_log["longitude"],
        "updated_at": latest_log["pinged_at"].isoformat() if hasattr(latest_log["pinged_at"], "isoformat") else str(latest_log["pinged_at"])
    }
    
    return {
        "rma_id": rma_id,
        "latest_position": latest_position,
        "location_history": location_history
    }