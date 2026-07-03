# src/auth/schemas.py
from pydantic import BaseModel, EmailStr, Field
from enum import Enum
from typing import Optional
from datetime import datetime

class UserRoleEnum(str, Enum):
    FIELD_TECH = "FIELD_TECH"
    CUST_ADMIN = "CUST_ADMIN"
    ENGINEER = "ENGINEER"
    LOGISTIC_PARTNER = "LOGISTIC_PARTNER"
    SYS_ADMIN = "SYS_ADMIN"

# Data skema internal detail user
class SkinnerUserData(BaseModel):
    id: str
    name: str
    email: str
    role: UserRoleEnum
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

# DTO Input untuk Login ke PWA / Web Portal
class LoginRequest(BaseModel):
    email: EmailStr = Field(..., example="apip.tech@telkomuniversity.ac.id")
    password: str = Field(..., example="AmangSekali123!")

# DTO Output setelah sukses Login
class LoginResponse(BaseModel):
    success: bool
    access_token: str
    token_type: str = "bearer"
    user: SkinnerUserData

# DTO untuk Sys Admin mendaftarkan kru/staf baru
class CreateUserRequest(BaseModel):
    name: str = Field(..., example="Chandra PSS Logistic")
    email: EmailStr = Field(..., example="chandra.courier@logistic.com")
    role: UserRoleEnum = Field(..., example="LOGISTIC_PARTNER")
    password: str = Field(..., description="Password awal yang di-generate sistem/admin", example="InitialPass123!")