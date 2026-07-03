# src/auth/guards.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from src.auth.services import SECRET_KEY, ALGORITHM

# fastapi membaca token bearer dari header 'Authorization' otomatis
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")

async def get_current_user_claims(token: str = Depends(oauth2_scheme)):
    """Membongkar isi token bearer untuk mendapatkan ID dan Role pengguna yang aktif"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload  # Mengembalikan data dict seperti: {"id": "uuid-str", "role": "FIELD_TECH"}
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesi Anda telah berakhir. Silakan login kembali."
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token autentikasi tidak sah atau rusak."
        )

class RoleChecker:
    """Interceptor Otoritas untuk mencocokkan kewenangan aktor dengan matriks Sequence Diagram"""
    def __init__(self, allowed_roles: list):
        self.allowed_roles = allowed_roles

    def __call__(self, user_claims: dict = Depends(get_current_user_claims)):
        user_role = user_claims.get("role")
        if user_role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail=f"Akses Ditolak! Anda bertindak sebagai {user_role}. Tindakan ini hanya diizinkan untuk role: {self.allowed_roles}"
            )
        return user_claims