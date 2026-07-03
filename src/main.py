# src/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from src.auth.routes import router as auth_router
from src.utils.db import db
from src.rma.routes import router as rma_router
from src.tracking.routes import router as tracking_router
# Import scheduler engine yang sudah kita buat
from src.rma.scheduler import scheduler, check_and_generate_replenishment

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Konek ke Neon DB saat aplikasi start
    await db.connect()
    
    # 2. Konfigurasi Jadwal Cron Job (2x Sehari: Jam 12 Siang & Jam 5 Sore)
    scheduler.add_job(check_and_generate_replenishment, 'cron', hour=12, minute=0)
    scheduler.add_job(check_and_generate_replenishment, 'cron', hour=17, minute=0)
    
    # 💡 TRICK SIMULASI: Jalankan sekali secara instan saat server menyala agar bisa langsung kita verifikasi
    scheduler.add_job(check_and_generate_replenishment, 'date')
    
    # Start scheduler engine
    scheduler.start()
    print("⏰ [System] APScheduler Berhasil Diaktifkan (2x Daily L3 to L4 Replenish Active).")
    
    yield
    
    # 3. Matikan scheduler dan putus koneksi DB saat aplikasi mati
    scheduler.shutdown()
    await db.disconnect()
    print("🛑 [System] APScheduler dan Koneksi Database Berhasil Dimatikan.")

app = FastAPI(
    title="Ericsson RMA Core Backend",
    version="1.0.0",
    lifespan=lifespan
)

# Izinkan Frontend Teman Anda Mengakses API (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Di fase produksi, ganti dengan URL Vercel teman Anda
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Daftarkan Router per Modul
app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication & Access Control"])
app.include_router(rma_router, prefix="/api/v1/rma", tags=["RMA Management"])
app.include_router(tracking_router, prefix="/api/v1/tracking", tags=["Geolocation Tracking"])

@app.get("/")
def health_check():
    return {"status": "healthy", "service": "RMA Backend"}