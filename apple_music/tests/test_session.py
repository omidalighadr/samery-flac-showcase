import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import httpx
import pytest
from scripts import apple_session as session


def client_factory(monkeypatch, responder):
    original = httpx.AsyncClient
    transport = httpx.MockTransport(responder)
    options = []

    def factory(**kwargs):
        options.append(kwargs)
        return original(transport=transport, **kwargs)

    async def no_sleep(seconds):
        return None

    monkeypatch.setattr(session.httpx, "AsyncClient", factory)
    monkeypatch.setattr(session.asyncio, "sleep", no_sleep)
    return options

def test_account_timeout_retried_with_longer_timeout(monkeypatch):
    requests = []

    def respond(request):
        requests.append(request)
        if len(requests) == 1:
            raise httpx.ReadTimeout("synthetic", request=request)
        return httpx.Response(200, json={"meta": {"subscription": {"active": True}}})

    options = client_factory(monkeypatch, respond)
    api = session.resilient_api(object)
    result = asyncio.run(api.get_account_info("synthetic-dev", "synthetic-user"))
    assert result["meta"]["subscription"]["active"]
    assert len(requests) == 2
    assert all(o["timeout"].connect == 30 and o["timeout"].read == 45 for o in options)
    assert requests[0].headers["cookie"] == "media-user-token=synthetic-user"

def test_rejected_cookie_classified_without_exposing_secret(monkeypatch):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(403, text="synthetic-private-response")

    client_factory(monkeypatch, respond)
    with pytest.raises(session.AppleSessionError) as caught:
        asyncio.run(session.fetch(session.ACCOUNT, headers={"cookie": "private"}))
    assert caught.value.code == "account_rejected"
    assert str(caught.value) == "account_rejected"
    assert len(requests) == 1

def test_exhausted_network_retry_is_not_bad_cookie(monkeypatch):
    count = []

    def respond(request):
        count.append(True)
        raise httpx.ConnectTimeout("synthetic-private-url", request=request)

    client_factory(monkeypatch, respond)
    with pytest.raises(session.AppleSessionError) as caught:
        asyncio.run(session.fetch(session.ACCOUNT))
    assert caught.value.code == "network"
    assert len(count) == 3
    assert "private" not in str(caught.value)

def test_token_discovery_uses_public_apple_asset(monkeypatch):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            text=(
                '<script src="/assets/index~test.js"></script>'
                if len(requests) == 1
                else '"eyJabc.eyJdef.test"'
            ),
        )

    client_factory(monkeypatch, respond)
    assert asyncio.run(session.resilient_api(object).get_token()) == "eyJabc.eyJdef.test"
    assert str(requests[1].url) == "https://music.apple.com/assets/index~test.js"
    assert "cookie" not in requests[1].headers

def test_account_credentials_not_forwarded_to_redirect(monkeypatch):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(302, headers={"location": "https://other.example/"})

    client_factory(monkeypatch, respond)
    with pytest.raises(session.AppleSessionError):
        asyncio.run(session.fetch(session.ACCOUNT, headers={"cookie": "synthetic-private"}))
    assert len(requests) == 1
