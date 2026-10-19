FROM python:3.10-slim

WORKDIR /app

# Sistem bağımlılıkları ve ADB kurulumu
RUN apt-get update && apt-get install -y \
    adb \
    scrcpy \
    git \
    && rm -rf /var/lib/apt/lists/*

# Python kütüphanelerini kopyala ve yükle
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Proje dosyalarını içeri aktar
COPY . .

CMD ["python3", "main.py"]
