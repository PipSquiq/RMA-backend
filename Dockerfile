# 1. Gunakan base image resmi Python versi 3.10 slim agar ukuran container ringan
FROM python:3.10-slim

# 2. Install dependensi OS yang dibutuhkan oleh Prisma Engine dan PostgreSQL (OpenSSL)
RUN apt-get update && apt-get install -y \
    openssl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 3. Buat user khusus non-root bernama "user" (Wajib mematuhi regulasi keamanan Hugging Face)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# 4. Tentukan direktori kerja di dalam container Docker
WORKDIR $HOME/app

# 5. Copy file daftar library (requirements.txt) ke dalam container
COPY --chown=user:user requirements.txt .

# 6. Install seluruh library Python yang dibutuhkan aplikasi
RUN pip install --no-cache-dir --user -r requirements.txt

# 7. Copy seluruh source code backend dari laptopmu ke dalam container
COPY --chown=user:user . .

# 8. Generate Prisma Client Python agar siap dipakai berkomunikasi dengan Neon DB
RUN prisma generate

# 9. Informasikan bahwa aplikasi akan berjalan di port standar Hugging Face yaitu 7860
EXPOSE 7860

# 10. Perintah utama untuk menyalakan Uvicorn Server saat container aktif
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "7860"]