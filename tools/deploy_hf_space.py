"""Deploy the BhajanForge voice Space to Hugging Face (no manual upload).

Creates a Docker Space, uploads hf_space/ (app + Dockerfile + your trained
model), and points BhajanForge's .env at the resulting URL.

Usage:
  python tools/deploy_hf_space.py --token hf_xxx [--space-name bhajan-voice]
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"


def write_env(key: str, val: str) -> None:
    text = ENV.read_text(encoding="utf-8")
    if re.search(rf"^{key}=.*$", text, flags=re.M):
        text = re.sub(rf"^{key}=.*$", f"{key}={val}", text, flags=re.M)
    else:
        text += f"\n{key}={val}\n"
    ENV.write_text(text, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True, help="Hugging Face write token")
    ap.add_argument("--space-name", default="bhajan-voice")
    args = ap.parse_args()

    from huggingface_hub import HfApi

    api = HfApi(token=args.token)
    user = api.whoami()["name"]
    repo_id = f"{user}/{args.space_name}"

    print("creating Space:", repo_id)
    api.create_repo(repo_id=repo_id, repo_type="space", space_sdk="docker",
                    exist_ok=True, private=False)

    print("uploading hf_space/ (includes ~170 MB model — may take a few minutes)…")
    api.upload_folder(
        folder_path=str(ROOT / "hf_space"),
        repo_id=repo_id,
        repo_type="space",
        commit_message="Deploy BhajanForge voice (RVC) Space",
    )

    host = f"{user}-{args.space_name}".lower().replace("_", "-")
    url = f"https://{host}.hf.space"
    print("\nSPACE PAGE:", f"https://huggingface.co/spaces/{repo_id}")
    print("SPACE URL :", url)

    write_env("RVC_TUNNEL_URL", url)
    write_env("VOICE_PROVIDER", "colab_tunnel")
    print("\nupdated .env -> VOICE_PROVIDER=colab_tunnel, RVC_TUNNEL_URL set")
    print("The Space is now BUILDING (Docker, ~10-15 min). When the page shows")
    print("'Running', voice conversions are free. I'll verify /health for you.")


if __name__ == "__main__":
    main()
