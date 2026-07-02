"""Download + save the trained RVC voice model locally (the Replicate URL
expires in ~24h), and archive the converted voice sample."""
from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env() -> dict[str, str]:
    env = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def main() -> None:
    env = load_env()
    url = env.get("REPLICATE_RVC_MODEL_URL", "").strip()
    if not url:
        raise SystemExit("REPLICATE_RVC_MODEL_URL not set in .env")

    models_dir = ROOT / "models" / "rvc"
    models_dir.mkdir(parents=True, exist_ok=True)
    zip_path = models_dir / "shyam_voice_v1.zip"

    import httpx
    print("downloading trained model from Replicate…")
    with httpx.Client(timeout=300.0, follow_redirects=True) as c:
        r = c.get(url)
        r.raise_for_status()
        zip_path.write_bytes(r.content)
    print(f"saved model zip: {zip_path} ({zip_path.stat().st_size/1024/1024:.1f} MB)")

    # extract .pth + .index for easy upload to a Hugging Face Space
    extract_dir = models_dir / "shyam_voice_v1"
    extract_dir.mkdir(exist_ok=True)
    root_resolved = extract_dir.resolve()
    with zipfile.ZipFile(zip_path) as z:
        for member in z.namelist():
            # Guard against Zip-Slip: ensure each member stays inside extract_dir.
            target = (extract_dir / member).resolve()
            if not str(target).startswith(str(root_resolved)):
                raise SystemExit(f"unsafe path in zip, refusing to extract: {member}")
        z.extractall(extract_dir)
    files = [p.name for p in extract_dir.rglob("*") if p.is_file()]
    print("extracted files:", files)

    # archive the converted voice sample
    sample_src = ROOT / "_voice_test_out.wav"
    if sample_src.exists():
        sample_dir = ROOT / "output" / "voice_clone_sample"
        sample_dir.mkdir(parents=True, exist_ok=True)
        dst = sample_dir / "my_cloned_voice_sample.wav"
        shutil.copy(sample_src, dst)
        print("saved voice sample:", dst)

    print("\nDONE. Your voice model lives in:", extract_dir)


if __name__ == "__main__":
    main()
