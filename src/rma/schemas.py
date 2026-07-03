# src/rma/schemas.py
from pydantic import BaseModel, Field, UUID4
from datetime import datetime
from enum import Enum
from typing import Optional, List

# 1. Definisi Enum Status RMA sesuai Skema Database
class RmaStatusEnum(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    SHIPPED = "SHIPPED"
    GOOD_PART_RECEIVED = "GOOD_PART_RECEIVED"
    FAULTY_PART_RETURNED = "FAULTY_PART_RETURNED"
    CLOSED = "CLOSED"

# 2. Skema untuk Request POST /api/v1/rma (Dibuat oleh Field Tech)
class RmaCreateRequest(BaseModel):
    field_tech_id: str = Field(..., example="b301e1aa-1234-4bc2-8888-abcdef123456")
    part_number: str = Field(..., example="PN-ERIC-4412")
    faulty_serial_number: str = Field(..., example="SN-FAULTY-99X")
    dop_id: str = Field(..., example="e604e4dd-1234-4bc2-8888-abcdef123456")

# 3. Skema Data Internal Objek RMA (Mendukung konversi otomatis dari Prisma ORM)
class RmaResponseData(BaseModel):
    id: str
    rma_number: str
    field_tech_id: str
    courier_id: Optional[str] = None
    part_number: str
    faulty_serial_number: str
    good_serial_number: Optional[str] = None
    dop_id: str
    status: RmaStatusEnum
    rating: Optional[int] = None
    feedback_notes: Optional[str] = None
    created_at: datetime
    approved_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

    class Config:
        from_attributes = True  # Pydantic v2 (sebelumnya bernama orm_mode = True di v1)

# 4. Skema Response Akhir Pembuatan RMA
class RmaCreateResponse(BaseModel):
    success: bool
    message: str
    data: RmaResponseData

# 5. Skema Response Akhir Persetujuan (Approval) beserta Metrik SLA 30 Menit
class RmaApproveResponse(BaseModel):
    success: bool
    message: str
    sla_status: str        # Menampilkan: "SLA_MET" atau "SLA_BREACHED"
    duration_minutes: float # Durasi dari rma dibuat hingga di-approve oleh Engineer
    data: RmaResponseData

# 6. Skema Request untuk Endpoint PATCH /approve
class RmaApprovalRequest(BaseModel):
    courier_id: UUID4

# 7. Skema Request untuk Endpoint PATCH /rating
class RmaFeedbackSubmitRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="Skala rating kepuasan dari 1 sampai 5", example=5)
    feedback_notes: Optional[str] = Field(None, description="Catatan masukan untuk performa sistem portal", example="Portal web sangat responsif dan pelacakan kurir presisi!")

class HeatmapPoint(BaseModel):
    latitude: float
    longitude: float
    site_name: str
    intensity: int  # Jumlah total kasus RMA di site ini

class SlaMonthlyTrend(BaseModel):
    month: str  # Format: "YYYY-MM"
    avg_duration_minutes: float
    total_requests: int
    breach_count: int
    breach_rate_percentage: float

class SlaDashboardResponse(BaseModel):
    total_rma_processed: int
    overall_avg_approval_minutes: float
    total_sla_breaches: int
    overall_breach_rate_percentage: float
    monthly_trends: List[SlaMonthlyTrend]