# src/tracking/schemas.py
from pydantic import BaseModel, Field
from typing import List, Optional

class LocationPingRequest(BaseModel):
    rma_id: str = Field(..., description="ID UUID dari RMA Request")
    # 🛡️ DISESUAIKAN: user_id dihapus dari body payload karena dipasok otomatis oleh secure JWT Guard
    latitude: float = Field(..., example=-6.89148)
    longitude: float = Field(..., example=107.61065)
    battery_level: Optional[int] = Field(50, ge=0, le=100, example=85)


# --- DTO UNTUK VALIDASI RESPONSE OUTPUT FASTAPI ---

class PositionDetail(BaseModel):
    latitude: float
    longitude: float
    updated_at: str

class HistoryLogItem(BaseModel):
    latitude: float
    longitude: float
    timestamp: str

class TrackingHistoryData(BaseModel):
    rma_id: str
    latest_position: Optional[PositionDetail] = None
    location_history: List[HistoryLogItem]

class TrackingHistoryContainerResponse(BaseModel):
    """Menjaga pembungkus standar response {"success": True, "data": ...} untuk Frontend"""
    success: bool
    data: TrackingHistoryData