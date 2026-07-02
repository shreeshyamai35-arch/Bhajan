"""Try to read the user's own suno.com session cookie from Chrome and write it
into .env for the self-hosted Suno provider. Local-only; the cookie is the
user's own login on their own machine.
"""
from __future__ import annotations

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
    import browser_cookie3 as bc

    wanted_domains = ("suno.com", "auth.suno.com", "clerk.suno.com")
    names = {}
    try:
        cj = bc.chrome()
    except Exception as e:  # noqa: BLE001
        print("FAILED to read Chrome cookies:", repr(e))
        return

    found = 0
    for c in cj:
        dom = (c.domain or "").lstrip(".")
        if any(dom == d or dom.endswith("." + d) or dom in wanted_domains
               for d in wanted_domains):
            if "suno.com" in dom:
                names[c.name] = c.value
                found += 1

    # Report which key cookies we got (NOT their values).
    print("cookies found for *.suno.com:", found)
    print("names:", sorted(names.keys()))
    has_client = "__client" in names
    has_session = "__session" in names
    print("__client present:", has_client, "| __session present:", has_session)

    if not has_client:
        print("RESULT: could not get __client cookie (likely Chrome app-bound "
              "encryption). Need manual cURL paste.")
        return

    cookie_str = "; ".join(f"{k}={v}" for k, v in names.items())
    # sanity: a real Clerk cookie value is a long JWT-ish string
    if len(names.get("__client", "")) < 40:
        print("RESULT: __client value looks empty/encrypted, length=",
              len(names.get("__client", "")), "-> need manual cURL paste.")
        return

    write_env("SUNO_COOKIE", cookie_str)
    write_env("SUNO_MODE", "self_hosted")
    write_env("SUNO_CLERK_URL", "https://auth.suno.com")
    write_env("SUNO_CLERK_JS_VERSION", "5.117.0")
    print("RESULT: OK — wrote SUNO_COOKIE (+ self_hosted config) to .env "
          "(%d cookies, %d chars)" % (len(names), len(cookie_str)))


if __name__ == "__main__":
    main()
