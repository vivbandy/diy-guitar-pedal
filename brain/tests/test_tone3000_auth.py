from __future__ import annotations

import stat

import httpx
import pytest

from tone_architect import tone3000_auth as auth


class FakeClock:
    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += s


def _http(handler) -> httpx.Client:
    return httpx.Client(base_url="https://t3k.test/api/v1", transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def token_file(tmp_path, monkeypatch):
    path = tmp_path / "tone3000.json"
    monkeypatch.setenv("TONE3000_TOKEN_FILE", str(path))
    monkeypatch.delenv("TONE3000_TOKEN", raising=False)
    monkeypatch.delenv("TONE3000_CLIENT_ID", raising=False)
    return path


def test_device_login_polls_through_pending_and_slow_down():
    polls: list[str] = []
    replies = iter(
        [
            (400, {"error": "authorization_pending"}),
            (400, {"error": "slow_down"}),
            (200, {"access_token": "at", "refresh_token": "rt", "expires_in": 3600}),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        form = dict(httpx.QueryParams(request.content.decode()))
        if request.url.path.endswith("/device_authorization"):
            assert form == {"client_id": "pub"}
            return httpx.Response(
                200,
                json={
                    "device_code": "dc",
                    "user_code": "ABCD-EFGH",
                    "verification_uri": "https://www.tone3000.com/activate",
                    "interval": 5,
                    "expires_in": 600,
                },
            )
        assert form["grant_type"] == auth.DEVICE_GRANT
        assert form["device_code"] == "dc"
        polls.append(form["client_id"])
        status, body = next(replies)
        return httpx.Response(status, json=body)

    clock = FakeClock()
    shown: list[str] = []
    tokens = auth.device_login(
        "pub", _http(handler), echo=shown.append, sleep=clock.sleep, clock=clock
    )

    assert tokens["access_token"] == "at"
    assert tokens["client_id"] == "pub"
    assert len(polls) == 3
    assert clock.t == 1000 + 5 + 5 + 10  # slow_down adds 5s to the interval
    assert tokens["expires_at"] == clock.t + 3600
    assert any("ABCD-EFGH" in line for line in shown)


def test_device_login_stops_on_denial():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/device_authorization"):
            return httpx.Response(
                200, json={"device_code": "dc", "user_code": "X", "verification_uri": "u"}
            )
        return httpx.Response(400, json={"error": "access_denied"})

    clock = FakeClock()
    with pytest.raises(auth.AuthError, match="access_denied"):
        auth.device_login(
            "pub", _http(handler), echo=lambda _: None, sleep=clock.sleep, clock=clock
        )


def test_saved_token_file_is_private(token_file):
    auth.save_tokens({"access_token": "at"})
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
    assert auth.load_tokens() == {"access_token": "at"}


def test_signed_in_token_wins_over_secret_key(monkeypatch):
    monkeypatch.setenv("TONE3000_TOKEN", "t3k_cs_secret")
    auth.save_tokens({"access_token": "user", "expires_at": 10_000, "client_id": "pub"})
    assert auth.resolve_token(clock=FakeClock(1000)) == ("user", "signed-in")


def test_secret_key_is_the_fallback(monkeypatch):
    monkeypatch.setenv("TONE3000_TOKEN", "t3k_cs_secret")
    assert auth.resolve_token() == ("t3k_cs_secret", "secret-key")


def test_nothing_configured_says_how_to_sign_in():
    with pytest.raises(auth.AuthError, match="tone3000-login"):
        auth.resolve_token()


def test_expired_token_is_refreshed_and_saved():
    auth.save_tokens(
        {"access_token": "old", "refresh_token": "rt", "expires_at": 1000, "client_id": "pub"}
    )

    def handler(request: httpx.Request) -> httpx.Response:
        form = dict(httpx.QueryParams(request.content.decode()))
        assert form == {"grant_type": "refresh_token", "refresh_token": "rt", "client_id": "pub"}
        return httpx.Response(200, json={"access_token": "new", "expires_in": 3600})

    token, source = auth.resolve_token(http=_http(handler), clock=FakeClock(1000))

    assert (token, source) == ("new", "signed-in")
    saved = auth.load_tokens()
    assert saved["access_token"] == "new"
    assert saved["refresh_token"] == "rt"  # kept when the server doesn't rotate it


def test_dead_refresh_token_asks_to_sign_in_again():
    auth.save_tokens(
        {"access_token": "old", "refresh_token": "rt", "expires_at": 0, "client_id": "pub"}
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    with pytest.raises(auth.AuthError, match="tone3000-login"):
        auth.resolve_token(http=_http(handler), clock=FakeClock(1000))
