"""Fetch the BUILD logs of the HF Space to diagnose a BUILD_ERROR."""
from __future__ import annotations

import argparse


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True)
    ap.add_argument("--repo", default="shreeshyamai35/bhajan-voice")
    args = ap.parse_args()

    import httpx

    headers = {"Authorization": f"Bearer {args.token}"}
    url = f"https://huggingface.co/api/spaces/{args.repo}/logs/build"
    try:
        with httpx.stream("GET", url, headers=headers, timeout=60.0) as r:
            print("HTTP", r.status_code)
            text = []
            for line in r.iter_lines():
                if line:
                    text.append(line)
            out = "\n".join(text)
            # print the tail, which holds the error
            print(out[-6000:])
    except Exception as e:  # noqa: BLE001
        print("could not stream logs:", e)
        # fallback non-stream
        r = httpx.get(url, headers=headers, timeout=60.0)
        print("HTTP", r.status_code)
        print(r.text[-6000:])


if __name__ == "__main__":
    main()
