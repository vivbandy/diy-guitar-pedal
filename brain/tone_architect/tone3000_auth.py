"""Sign in to TONE3000 as yourself, so `tone3000-sync` can read your favorited/created tones.

Why this exists: the secret key (`t3k_cs_...`) authenticates the *app*, not a user, so
`/tones/favorited` comes back empty with it. User-scoped endpoints need an OAuth access token.
The device flow fits a CLI: no redirect URI, no local web server — you approve a short code in
the browser and the command picks up the token.

The token is stored at ~/.config/tone-architect/tone3000.json (mode 0600, outside the repo) and
refreshed automatically when it expires.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

API_BASE = os.getenv("TONE3000_API_BASE", "https://www.tone3000.com/api/v1")
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
# Refresh a little early so a sync never starts with a token that dies mid-pagination.
EXPIRY_SLACK_S = 60


class AuthError(RuntimeError):
    pass


def token_path() -> Path:
    override = os.getenv("TONE3000_TOKEN_FILE")
    if override:
        return Path(override).expanduser()
    base = Path(os.getenv("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "tone-architect" / "tone3000.json"


def load_tokens(path: Path | None = None) -> dict | None:
    path = path or token_path()
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def save_tokens(tokens: dict, path: Path | None = None) -> Path:
    path = path or token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    # Create with 0600 from the start rather than chmod-after, so the token is never world-readable.
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(tokens, fh, indent=2)
    os.replace(tmp, path)
    return path


def _with_expiry(body: dict, client_id: str, now: float) -> dict:
    return {
        "access_token": body["access_token"],
        "refresh_token": body.get("refresh_token"),
        "expires_at": now + float(body.get("expires_in") or 3600),
        "scope": body.get("scope"),
        "client_id": client_id,
    }


def _http(base: str = API_BASE):
    import httpx

    return httpx.Client(base_url=base, timeout=30.0)


def device_login(
    client_id: str,
    http: Any,
    echo: Callable[[str], None] = print,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.time,
) -> dict:
    response = http.post("/oauth/device_authorization", data={"client_id": client_id})
    if response.status_code != 200:
        raise AuthError(f"device authorization failed: {_error(response)}")
    start = response.json()

    echo(f"Open {start.get('verification_uri_complete') or start['verification_uri']}")
    echo(
        f"and enter the code {start['user_code']} to let Tone Architect read your TONE3000 library."
    )
    echo("Waiting for approval...")

    interval = float(start.get("interval") or 5)
    deadline = clock() + float(start.get("expires_in") or 600)
    while clock() < deadline:
        sleep(interval)
        poll = http.post(
            "/oauth/token",
            data={
                "grant_type": DEVICE_GRANT,
                "device_code": start["device_code"],
                "client_id": client_id,
            },
        )
        if poll.status_code == 200:
            return _with_expiry(poll.json(), client_id, clock())
        code = _error(poll)
        if code == "authorization_pending":
            continue
        if code == "slow_down":
            interval += 5
            continue
        raise AuthError(f"sign-in failed: {code}")
    raise AuthError("sign-in timed out; run tone3000-login again")


def refresh(tokens: dict, http: Any, clock: Callable[[], float] = time.time) -> dict:
    client_id = tokens.get("client_id") or os.getenv("TONE3000_CLIENT_ID")
    if not tokens.get("refresh_token") or not client_id:
        raise AuthError("TONE3000 sign-in expired; run tone3000-login again")
    response = http.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": client_id,
        },
    )
    if response.status_code != 200:
        raise AuthError(f"TONE3000 sign-in expired ({_error(response)}); run tone3000-login again")
    fresh = _with_expiry(response.json(), client_id, clock())
    # Some servers don't rotate refresh tokens; keep the old one if none came back.
    fresh["refresh_token"] = fresh["refresh_token"] or tokens["refresh_token"]
    return fresh


def resolve_token(
    http: Any | None = None, clock: Callable[[], float] = time.time
) -> tuple[str, str]:
    """Return (token, source). A stored sign-in wins over TONE3000_TOKEN, since only it is
    user-scoped; the secret key still works for `--scope search`."""
    tokens = load_tokens()
    if tokens:
        if clock() >= float(tokens.get("expires_at") or 0) - EXPIRY_SLACK_S:
            owns_http = http is None
            http = http or _http()
            try:
                tokens = refresh(tokens, http, clock)
            finally:
                if owns_http:
                    http.close()
            save_tokens(tokens)
        return tokens["access_token"], "signed-in"
    secret = os.getenv("TONE3000_TOKEN")
    if secret:
        return secret, "secret-key"
    raise AuthError("not signed in to TONE3000: run tone3000-login (or set TONE3000_TOKEN)")


def _error(response: Any) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    return body.get("error") or body.get("message") or f"HTTP {response.status_code}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tone3000-login",
        description="Sign in to TONE3000 so tone3000-sync can read your favorited/created tones.",
    )
    parser.add_argument("--logout", action="store_true", help="delete the stored sign-in")
    args = parser.parse_args(argv)

    path = token_path()
    if args.logout:
        path.unlink(missing_ok=True)
        print(f"signed out (removed {path})")
        return 0

    client_id = os.getenv("TONE3000_CLIENT_ID")
    if not client_id:
        print(
            "TONE3000_CLIENT_ID is not set: use your TONE3000 *publishable* key",
            file=sys.stderr,
        )
        return 1

    http = _http()
    try:
        tokens = device_login(client_id, http)
    except AuthError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        http.close()
    print(f"signed in; token saved to {save_tokens(tokens, path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
