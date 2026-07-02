# BhajanForge — CPU-only image (no GPU). All heavy AI runs via cloud APIs.
FROM python:3.11-slim

# ffmpeg for audio I/O (librosa/pydub/yt-dlp); build tools for some wheels.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir -e .

# Run as a non-root user (defense in depth).
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["bhajanforge", "serve", "--host", "0.0.0.0", "--port", "8000"]
