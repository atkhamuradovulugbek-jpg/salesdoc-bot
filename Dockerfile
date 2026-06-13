FROM python:3.11-slim

# DejaVu shriftlarini o'rnatish — PIL rasm matnlari uchun ZARUR.
# Bularsiz PIL kichik standart bitmap shriftga tushib qoladi (matn mitti chiqadi).
RUN apt-get update && \
    apt-get install -y --no-install-recommends fonts-dejavu-core && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
