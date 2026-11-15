FROM python:3.11-slim

# Haqiqiy H.264 .mp4 + AAC audio (zvuk) Reels video render qilish uchun ffmpeg va shriftlar
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p data/photos data/audio && chmod -R 777 /app

ENV PORT=7860
EXPOSE 7860
CMD ["python", "-u", "main.py"]
