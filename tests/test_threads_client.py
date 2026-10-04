from urllib.parse import parse_qs

import httpx
import pytest

from app.config import Settings
from app.threads_client import ThreadsApiError, ThreadsClient


def make_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_base_url="https://dami.example.com",
        meta_app_id="app-id",
        meta_app_secret="app-secret",
        app_admin_password="password",
        session_secret="session-secret",
        token_encryption_key="test-key",
    )


@pytest.mark.asyncio
async def test_keyword_search_uses_official_endpoint_and_filters():
    observed = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["authorization"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={"data": [{"id": "real-thread", "username": "student", "text": "cần chụp kỷ yếu"}]},
        )

    client = ThreadsClient(make_settings(), transport=httpx.MockTransport(handler))
    payload = await client.keyword_search(
        "real-token", q="kỷ yếu", search_type="RECENT", search_mode="KEYWORD", limit=10
    )
    assert payload["data"][0]["id"] == "real-thread"
    assert "/v1.0/keyword_search" in observed["url"]
    assert "search_type=RECENT" in observed["url"]
    assert observed["authorization"] == "Bearer real-token"


@pytest.mark.asyncio
async def test_reply_creates_container_then_publishes():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, parse_qs(request.content.decode())))
        if request.url.path.endswith("/me/threads"):
            return httpx.Response(200, json={"id": "container-123"})
        if request.url.path.endswith("/me/threads_publish"):
            return httpx.Response(200, json={"id": "published-456"})
        return httpx.Response(404, json={"error": {"message": "unexpected"}})

    client = ThreadsClient(make_settings(), transport=httpx.MockTransport(handler))
    published_id = await client.reply_to_post(
        "real-token", thread_id="target-789", text="Nội dung đã duyệt"
    )
    assert published_id == "published-456"
    assert calls[0][2]["reply_to_id"] == ["target-789"]
    assert calls[1][2]["creation_id"] == ["container-123"]


@pytest.mark.asyncio
async def test_rate_limit_is_recognized():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={"error": {"message": "Rate limit", "code": 4, "fbtrace_id": "trace-1"}},
        )

    client = ThreadsClient(make_settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(ThreadsApiError) as raised:
        await client.keyword_search(
            "token", q="kỷ yếu", search_type="RECENT", search_mode="KEYWORD", limit=10
        )
    assert raised.value.is_rate_limit is True
    assert "trace-1" in raised.value.safe_message
