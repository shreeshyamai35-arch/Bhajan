#!/usr/bin/env bash
# BhajanForge — EC2 GPU bootstrap for RVC voice cloning.
#
# Run this ON the instance (or paste it as EC2 "user data" at launch) on an
# Ubuntu 22.04 g4dn.xlarge (T4) / g5.xlarge (A10G) box. It installs RVC,
# downloads pretrained assets, drops in rvc_server.py, and exposes a public
# /convert URL via cloudflared (no signup) that BhajanForge calls.
#
# Total disk used ~15 GB -> use a 60 GB+ EBS volume.
set -euo pipefail

RVC_ROOT=/opt/rvc
export DEBIAN_FRONTEND=noninteractive

echo "==> System deps"
sudo apt-get update -y
sudo apt-get install -y git python3-pip python3-venv ffmpeg wget unzip

echo "==> NVIDIA driver check"
nvidia-smi || echo "WARN: no GPU driver yet (Deep Learning AMI ships one)."

echo "==> Clone RVC"
sudo mkdir -p "$RVC_ROOT"
sudo chown "$USER" "$RVC_ROOT"
if [ ! -d "$RVC_ROOT/.git" ]; then
  git clone https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI.git "$RVC_ROOT"
fi
cd "$RVC_ROOT"

echo "==> Python env"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt || pip install -r requirements/main.txt || true
pip install fastapi uvicorn soundfile numpy python-multipart

echo "==> Download RVC pretrained assets"
python tools/download_models.py || \
  bash -lc 'echo "If download_models.py is missing, fetch assets/hubert + assets/pretrained_v2 per RVC README."'

echo "==> Install BhajanForge RVC server"
# Expects rvc_server.py copied alongside (scp) or pulled from your repo.
if [ -f /home/ubuntu/rvc_server.py ]; then
  cp /home/ubuntu/rvc_server.py "$RVC_ROOT/rvc_server.py"
fi

echo "==> cloudflared (free public tunnel, no signup)"
wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O /tmp/cloudflared
sudo install /tmp/cloudflared /usr/local/bin/cloudflared

cat <<'EOF'

==========================================================================
SETUP DONE. To start serving your cloned voice:

  cd /opt/rvc && source .venv/bin/activate
  RVC_ROOT=/opt/rvc PORT=7865 python rvc_server.py &
  cloudflared tunnel --url http://localhost:7865

cloudflared prints a https://<random>.trycloudflare.com URL. On your PC put
in BhajanForge .env:

  VOICE_PROVIDER=colab_tunnel
  RVC_TUNNEL_URL=https://<that-url>

and set config/learning.yaml -> voice_profile.active_rvc_model: shyam_voice_v1
==========================================================================
EOF
