from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from .config import Settings


class ThreadsApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 500,
        code: int | None = None,
        subcode: int | None = None,
        trace_id: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.subcode = subcode
        self.trace_id = trace_id

    @property
    def is_rate_limit(self) -> bool:
        return self.status_code == 429 or self.code in {4, 17, 32, 613}

    @property
    def safe_message(self) -> str:
        suffix = f" (Meta code {self.code})" if self.code is not None else ""
        trace = f" · fbtrace_id: {self.trace_id}" if self.trace_id else ""
        return f"{self}{suffix}{trace}"


class ThreadsClient:
    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    def authorization_url(self, state: str) -> str:
        params = {
            "client_id": self.settings.meta_app_id,
            "redirect_uri": self.settings.redirect_uri,
            "scope": self.settings.oauth_scopes,
            "response_type": "code",
            "state": state,
        }
        return f"{self.settings.oauth_authorize_url}?{urlencode(params)}"

    async def _request(
        self,
        method: str,
        url: str,
        *,
        token: str | None = None,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient(timeout=30, transport=self.transport) as client:
            try:
                response = await client.request(method, url, params=params, data=data, headers=headers)
            except httpx.HTTPError as exc:
                raise ThreadsApiError(f"Không kết nối được Threads API: {exc}", status_code=503) from exc

        try:
            payload = response.json()
        except ValueError:
            payload = {}

        if response.is_error or "error" in payload:
            error = payload.get("error") or {}
            message = error.get("message") or f"Threads API trả về HTTP {response.status_code}."
            raise ThreadsApiError(
                message,
                status_code=response.status_code,
                code=error.get("code"),
                subcode=error.get("error_subcode"),
                trace_id=error.get("fbtrace_id"),
            )
        return payload

    async def exchange_code(self, code: str) -> dict[str, Any]:
        short = await self._request(
            "POST",
            f"{self.settings.graph_base_url.rstrip('/')}/oauth/access_token",
            data={
                "client_id": self.settings.meta_app_id,
                "client_secret": self.settings.meta_app_secret,
                "grant_type": "authorization_code",
                "redirect_uri": self.settings.redirect_uri,
                "code": code,
            },
        )
        short_token = short.get("access_token")
        if not short_token:
            raise ThreadsApiError("Meta không trả về access token.")
        long_lived = await self._request(
            "GET",
            f"{self.settings.graph_base_url.rstrip('/')}/access_token",
            params={
                "grant_type": "th_exchange_token",
                "client_secret": self.settings.meta_app_secret,
                "access_token": short_token,
            },
        )
        return long_lived

    async def refresh_long_lived_token(self, token: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"{self.settings.graph_base_url.rstrip('/')}/refresh_access_token",
            params={"grant_type": "th_refresh_token", "access_token": token},
        )

    async def profile(self, token: str) -> dict[str, Any]:
        try:
            return await self._request(
                "GET",
                f"{self.settings.api_root}/me",
                token=token,
                params={"fields": "id,username,threads_profile_picture_url,threads_biography"},
            )
        except ThreadsApiError:
            return await self._request(
                "GET",
                f"{self.settings.api_root}/me",
                token=token,
                params={"fields": "id,username"},
            )

    async def keyword_search(
        self,
        token: str,
        *,
        q: str,
        search_type: str,
        search_mode: str,
        limit: int,
    ) -> dict[str, Any]:
        fields = (
            "id,media_product_type,media_type,permalink,owner,username,text,timestamp,"
            "shortcode,is_quote_post,has_replies,topic_tag"
        )
        return await self._request(
            "GET",
            f"{self.settings.api_root}/keyword_search",
            token=token,
            params={
                "q": q,
                "search_type": search_type,
                "search_mode": search_mode,
                "limit": limit,
                "fields": fields,
            },
        )

    async def reply_to_post(self, token: str, *, thread_id: str, text: str) -> str:
        container = await self._request(
            "POST",
            f"{self.settings.api_root}/me/threads",
            token=token,
            data={"media_type": "TEXT", "text": text, "reply_to_id": thread_id},
        )
        creation_id = container.get("id")
        if not creation_id:
            raise ThreadsApiError("Meta không trả về creation_id khi tạo phản hồi.")
        published = await self._request(
            "POST",
            f"{self.settings.api_root}/me/threads_publish",
            token=token,
            data={"creation_id": creation_id},
        )
        published_id = published.get("id")
        if not published_id:
            raise ThreadsApiError("Meta không trả về ID phản hồi đã đăng.")
        return str(published_id)


def expires_at_from(seconds: int | None) -> str | None:
    if not seconds:
        return None
    return (datetime.now(UTC) + timedelta(seconds=int(seconds))).isoformat()

