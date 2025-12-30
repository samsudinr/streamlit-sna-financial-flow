# Gunakan python versi ringan
FROM python:3.11-slim

# Atur direktori kerja di dalam kontainer
WORKDIR /app

# Instal kebutuhan sistem untuk library tertentu jika diperlukan
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Salin file requirements terlebih dahulu agar build lebih cepat (caching)
COPY requirements.txt .

# Instal library python
RUN pip install --no-cache-dir -r requirements.txt

# Salin seluruh isi folder proyek ke dalam kontainer
COPY . .

# Beritahu Docker bahwa aplikasi berjalan di port 8501
EXPOSE 8501

# Perintah untuk menjalankan streamlit
ENTRYPOINT ["streamlit", "run", "streamliet_new.py", "--server.port=8501", "--server.address=0.0.0.0"]