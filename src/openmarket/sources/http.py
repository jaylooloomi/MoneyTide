from __future__ import annotations

import asyncio

import httpx

from ..config import HTTP_RETRY_DELAY_SECONDS, HTTP_TIMEOUT_SECONDS, USER_AGENT


def make_client() -> httpx.AsyncClient:
    # Keep httpx's default certifi verification: the Windows system store fails TWSE/TPEx
    # chains on Python >= 3.13 (VERIFY_X509_STRICT, "Missing Subject Key Identifier").
    return httpx.AsyncClient(
        timeout=HTTP_TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-TW,zh;q=0.9"},
        follow_redirects=True,
    )


async def get_with_retry(client: httpx.AsyncClient, url: str, retries: int = 1) -> httpx.Response:
    for attempt in range(retries + 1):
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp
        except httpx.HTTPError:
            if attempt == retries:
                raise
            await asyncio.sleep(HTTP_RETRY_DELAY_SECONDS)
    raise AssertionError("unreachable")
