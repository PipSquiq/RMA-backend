# src/auth/services.py
from datetime import datetime, timedelta, timezone
import jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status
from src.utils.db import db
from src.auth.schemas import CreateUserRequest

# Konfigurasi hashing algoritma Bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = "SUPER_SECRET_KEY_PORTAL_ERICSSON_2026_TUMBUH_POKETTO" # Amankan di .env jika produksi
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 8  # Token expired dalam waktu 8 jam kerja kurir/teknisi

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    """Menerbitkan token akses digital yang memuat klaim ID dan Role user"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def authenticate_user(email: str, plain_password: str):
    """Mencari user dan memvalidasi keaslian password hash di database Neon"""
    user = await db.user.find_unique(where={"email": email})
    if not user:
        return None
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Akun Anda dinonaktifkan oleh System Administrator.")
    if not verify_password(plain_password, user.password_hash):
        return None
    return user

async def admin_create_user(payload: CreateUserRequest):
    """Logika pembuatan akun terpusat oleh Sys Admin"""
    existing = await db.user.find_unique(where={"email": payload.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email tersebut sudah terdaftar di dalam sistem.")
        
    hashed_pwd = hash_password(payload.password)
    new_user = await db.user.create(
        data={
            "name": payload.name,
            "email": payload.email,
            "role": payload.role.value,
            "password_hash": hashed_pwd,
            "is_active": True
        }
    )
    return new_user