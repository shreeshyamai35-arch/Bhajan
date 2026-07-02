"""Train a custom RVC voice model on Replicate (no Colab, no GPU needed locally).

Steps:
  1. Zip the audio clips in `Sample Audio/` into a dataset.
  2. Run `replicate/train-rvc-model` (managed GPU) to train the voice.
  3. Print the trained-model URL and write it into `.env` as
     `REPLICATE_RVC_MODEL_URL` so BhajanForge uses it for conversion.

Usage:
  python tools/train_voice_replicate.py            # default epoch=100
  python tools/train_voice_replicate.py --epoch 150
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "Sample Audio"
DATASET_ZIP = ROOT / "_voice_dataset.zip"
ENV = ROOT / ".env"


def load_env() -> None:
    if not ENV.exists():
        return
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _to_wav(src: str, dst: Path) -> bool:
    """Convert an audio clip to WAV. Returns False if no local decoder works."""
    try:
        import soundfile as sf
        data, sr = sf.read(src)
        sf.write(str(dst), data, sr)
        return True
    except Exception:  # noqa: BLE001
        try:
            import librosa, soundfile as sf  # noqa: E401
            data, sr = librosa.load(src, sr=None, mono=False)
            if hasattr(data, "ndim") and data.ndim > 1:
                data = data.T
            sf.write(str(dst), data, sr)
            return True
        except Exception:  # noqa: BLE001
            return False


def build_dataset_zip(model_name: str) -> Path:
    """Build a zip with the structure the model requires: dataset/<name>/*.wav."""
    import shutil
    clips = [p for p in sorted(glob.glob(str(SAMPLES / "*")))
             if p.lower().endswith((".mp3", ".wav", ".m4a", ".flac"))]
    if not clips:
        sys.exit(f"No audio found in {SAMPLES}")

    tmp = ROOT / "_ds_tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    inner = tmp / "dataset" / model_name
    inner.mkdir(parents=True)
    for i, c in enumerate(clips):
        dst = inner / f"clip_{i}.wav"
        if not _to_wav(c, dst):
            # Fallback: keep original (Replicate container has ffmpeg to decode).
            shutil.copy(c, inner / f"clip_{i}{os.path.splitext(c)[1].lower()}")

    with zipfile.ZipFile(DATASET_ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for f in glob.glob(str(tmp / "**" / "*"), recursive=True):
            if os.path.isfile(f):
                z.write(f, arcname=os.path.relpath(f, tmp))
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"dataset: {len(clips)} clips -> {DATASET_ZIP.name} "
          f"(dataset/{model_name}/, {DATASET_ZIP.stat().st_size/1024/1024:.1f} MB)")
    return DATASET_ZIP


def write_model_url(url: str) -> None:
    text = ENV.read_text(encoding="utf-8")
    if re.search(r"^REPLICATE_RVC_MODEL_URL=.*$", text, flags=re.M):
        text = re.sub(r"^REPLICATE_RVC_MODEL_URL=.*$",
                      f"REPLICATE_RVC_MODEL_URL={url}", text, flags=re.M)
    else:
        text += f"\nREPLICATE_RVC_MODEL_URL={url}\n"
    ENV.write_text(text, encoding="utf-8")
    print("wrote REPLICATE_RVC_MODEL_URL to .env")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epoch", type=int, default=100)
    ap.add_argument("--sample-rate", default="48k")
    ap.add_argument("--model-name", default="shyam_voice_v1")
    args = ap.parse_args()

    load_env()
    if not os.getenv("REPLICATE_API_TOKEN"):
        sys.exit("REPLICATE_API_TOKEN not set in .env")
    train_model = os.getenv(
        "REPLICATE_RVC_TRAIN_MODEL",
        "replicate/train-rvc-model:cf360587a27f67500c30fc31de1e0f0f9aa26dcd7b866e6ac937a07bd104bad9",
    )

    import replicate

    # Resolve the CURRENT version dynamically (pinned versions get disabled).
    base = train_model.split(":", 1)[0]
    try:
        ver = replicate.models.get(base).latest_version.id
        train_ref = f"{base}:{ver}"
    except Exception as exc:  # noqa: BLE001
        print("could not resolve latest version, using configured ref:", exc)
        train_ref = train_model

    zip_path = build_dataset_zip(args.model_name)
    print(f"training on Replicate ({train_ref}, epoch={args.epoch})…")
    print("this runs on Replicate's GPU and typically takes ~6-12 min.")
    with open(zip_path, "rb") as fh:
        output = replicate.run(train_ref, input={
            "dataset_zip": fh,
            "sample_rate": args.sample_rate,
            "version": "v2",
            "f0method": "rmvpe_gpu",
            "epoch": args.epoch,
            "batch_size": "7",
        })

    item = output[0] if isinstance(output, (list, tuple)) and output else output
    url = getattr(item, "url", None) or (item if isinstance(item, str) else str(item))
    print("\nTRAINED MODEL URL:", url)
    write_model_url(url)
    try:
        DATASET_ZIP.unlink()
    except OSError:
        pass
    print("\nDone. BhajanForge will now use your cloned voice for conversion.")


if __name__ == "__main__":
    main()
