# src/auth/routes.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm  # 💡 Tambahkan impor ini
from src.auth.schemas import LoginRequest, LoginResponse, CreateUserRequest, SkinnerUserData
from src.auth import services as auth_services
from src.auth.guards import RoleChecker

router = APIRouter()

@router.post("/login", response_model=LoginResponse)
async def login(
    # 💡 Menggunakan Depends untuk mendeteksi apakah data datang dari Form (Swagger) atau JSON (Postman/FE)
    payload: LoginRequest = None,
    form_data: OAuth2PasswordRequestForm = Depends(None)
):
    """
    Endpoint Autentikasi Tunggal: Mendukung login via JSON (PWA/Frontend) 
    maupun Form Data (Fitur "Authorize" di Swagger UI).
    """
    # 1. Jika request datang dari Swagger UI (menggunakan Form Data)
    if form_data is not None:
        email_input = form_data.username  # Swagger memetakan input 'username' ke field ini
        password_input = form_data.password
    # 2. Jika request datang dari PWA / Postman / Frontend (menggunakan JSON)
    elif payload is not None:
        email_input = payload.email
        password_input = payload.password
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload login tidak valid. Kirimkan data melalui JSON atau Form Data."
        )

    # Jalankan verifikasi ke Neon DB via service layer
    user = await auth_services.authenticate_user(email_input, password_input)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email atau password yang Anda masukkan salah."
        )
        
    token_payload = {"id": str(user.id), "role": user.role.value if hasattr(user.role, 'value') else str(user.role)}
    access_token = auth_services.create_access_token(token_payload)
    
    return {
        "success": True,
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }