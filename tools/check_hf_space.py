"""Check the build/run status of the BhajanForge HF Space."""
from __future__ import annotations

import argparse


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True)
    ap.add_argument("--repo", default="shreeshyamai35/bhajan-voice")
    args = ap.parse_args()

    from huggingface_hub import HfApi

    api = HfApi(token=args.token)
    rt = api.get_space_runtime(args.repo)
    print("stage:", rt.stage)
    print("hardware:", getattr(rt, "hardware", None))

    # If running, hit /health
    if str(rt.stage).upper() in {"RUNNING", "RUNNING_APP_STARTING"}:
        import httpx
        url = "https://shreeshyamai35-bhajan-voice.hf.space/health"
        try:
            r = httpx.get(url, timeout=30.0)
            print("health:", r.status_code, r.text[:200])
        except Exception as e:  # noqa: BLE001
            print("health check failed (app may still be starting):", e)


if __name__ == "__main__":
    main()
