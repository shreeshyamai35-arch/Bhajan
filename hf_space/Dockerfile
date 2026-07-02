FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/home/user/.cache/huggingface

# System deps: git (clone RVC), ffmpeg (audio), build tools for fairseq/pyworld.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git ffmpeg build-essential wget ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Run as the non-root user HF Spaces expects.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH
WORKDIR /home/user/app

# CPU-only PyTorch first (keeps the image small, no CUDA).
RUN pip install --no-cache-dir --user \
        torch==2.1.2 torchaudio==2.1.2 \
        --index-url https://download.pytorch.org/whl/cpu

# RVC inference code (official RVC-Project WebUI).
RUN git clone --depth 1 \
        https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI \
        rvc

# Build deps + fairseq from a build-patched fork (the pinned fairseq fails to
# build on modern Python — same fix we use everywhere else). numpy + Cython must
# be present BEFORE building fairseq because we use --no-build-isolation.
RUN pip install --no-cache-dir --user "setuptools<82" wheel Cython "numpy<2" && \
    pip install --no-cache-dir --user --no-build-isolation \
        "git+https://github.com/One-sixth/fairseq.git"

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Pretrained assets needed for inference (HuBERT + rmvpe pitch model).
RUN mkdir -p rvc/assets/hubert rvc/assets/rmvpe && \
    wget -q https://huggingface.co/lj1995/VoiceConversionWebUI/resolve/main/hubert_base.pt \
         -O rvc/assets/hubert/hubert_base.pt && \
    wget -q https://huggingface.co/lj1995/VoiceConversionWebUI/resolve/main/rmvpe.pt \
         -O rvc/assets/rmvpe/rmvpe.pt

# App + your uploaded model (models/ is created/filled in the Space UI).
COPY --chown=user app.py .
COPY --chown=user models/ ./models/

EXPOSE 7860
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
