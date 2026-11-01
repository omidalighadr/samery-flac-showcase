"""Resilient Apple account bootstrap, with diagnostics that contain no secrets."""

from __future__ import annotations

import asyncio
import re
from urllib.parse import urljoin

import httpx

HOME = "https://music.apple.com"
ACCOUNT = "https://amp-api.music.apple.com/v1/me/account"


class AppleSessionError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


async def fetch(url: str, **kwargs) -> httpx.Response:
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(45, connect=30),
                follow_redirects=True,
            ) as client:
                response = await client.get(url, follow_redirects=url != ACCOUNT, **kwargs)
            if response.status_code in (401, 403):
                raise AppleSessionError(
                    "account_rejected" if url == ACCOUNT else "apple_access_denied"
                )
            if response.status_code == 429 or response.status_code >= 500:
                raise AppleSessionError("apple_unavailable")
            response.raise_for_status()
            return response
        except (httpx.TransportError, AppleSessionError) as error:
            if isinstance(error, AppleSessionError) and error.code != "apple_unavailable":
                raise
            if attempt == 2:
                raise AppleSessionError(
                    "apple_unavailable" if isinstance(error, AppleSessionError) else "network"
                ) from None
            await asyncio.sleep(1 + attempt)
        except httpx.HTTPStatusError:
            raise AppleSessionError("apple_response") from None
    raise AppleSessionError("network")


def resilient_api(api_type):
    """Keep gamdl's account/media API; replace only its short-lived login HTTP calls."""

    class ResilientAppleMusicApi(api_type):
        @staticmethod
        async def get_token():
            home = await fetch(HOME)
            asset = re.search(r'/(assets/index[~-][^/"\s]+\.js)', home.text)
            if not asset:
                raise AppleSessionError("apple_page_changed")
            script = await fetch(urljoin(HOME, "/" + asset.group(1)))
            token = re.search(
                r'"(eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)"', script.text
            )
            if not token:
                raise AppleSessionError("apple_page_changed")
            return token.group(1)

        @staticmethod
        async def get_account_info(token, media_user_token, meta="subscription"):
            response = await fetch(
                ACCOUNT,
                params={"meta": meta},
                headers={
                    "authorization": f"Bearer {token}",
                    "origin": HOME,
                    "cookie": f"media-user-token={media_user_token}",
                },
            )
            try:
                return response.json()
            except ValueError:
                raise AppleSessionError("apple_response") from None

    return ResilientAppleMusicApi
