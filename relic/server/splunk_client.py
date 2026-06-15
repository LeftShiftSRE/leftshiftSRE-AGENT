import os
import random
import asyncio

import httpx

from .mock_splunk import mock_search

RETRYABLE_STATUS = {429, 503, 504}
MAX_RETRIES = 3
BASE_BACKOFF = 0.5
JITTER_RANGE = 0.25


class SplunkRateLimited(Exception):
    def __init__(self, retry_after: float | None = None):
        self.retry_after = retry_after


class SplunkRetriesExhausted(Exception):
    pass


class SplunkClient:
    def __init__(
        self,
        base_url: str = "",
        token: str = "",
        semaphore_size: int = 4,
        use_mock: bool | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        if use_mock is None:
            use_mock = os.getenv("RELIC_MOCK", "1") == "1"
        self.use_mock = use_mock
        self._semaphore = asyncio.Semaphore(semaphore_size)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                limits=httpx.Limits(max_connections=4, max_keepalive_connections=4),
                timeout=httpx.Timeout(30.0),
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _with_retry(self, coro_factory):
        last_exc = None
        for attempt in range(MAX_RETRIES):
            try:
                async with self._semaphore:
                    return await coro_factory()
            except SplunkRateLimited as e:
                last_exc = e
                if attempt == MAX_RETRIES - 1:
                    break
                sleep = BASE_BACKOFF * (2 ** attempt) * (
                    1 + random.uniform(-JITTER_RANGE, JITTER_RANGE)
                )
                if e.retry_after:
                    sleep = min(sleep, e.retry_after)
                await asyncio.sleep(sleep)
            except httpx.HTTPStatusError as e:
                if e.response.status_code in RETRYABLE_STATUS:
                    last_exc = e
                    if attempt == MAX_RETRIES - 1:
                        break
                    sleep = BASE_BACKOFF * (2 ** attempt) * (
                        1 + random.uniform(-JITTER_RANGE, JITTER_RANGE)
                    )
                    await asyncio.sleep(sleep)
                else:
                    raise
        raise SplunkRetriesExhausted(
            f"Failed after {MAX_RETRIES} attempts"
        ) from last_exc

    async def search(
        self, query: str, earliest: str = "-24h", latest: str = "now"
    ) -> dict:
        if self.use_mock:
            return mock_search(query)

        async def _do():
            client = await self._get_client()
            resp = await client.post(
                f"{self.base_url}/services/search/jobs/export",
                headers={"Authorization": f"Bearer {self.token}"},
                data={
                    "search": query,
                    "earliest_time": earliest,
                    "latest_time": latest,
                    "output_mode": "json",
                    "dispatch.ttl": "120",
                    "role": "relic_role",
                },
            )
            if resp.status_code == 429:
                retry_after = float(
                    resp.headers.get("Retry-After", "1")
                )
                raise SplunkRateLimited(retry_after)
            if resp.status_code == 403:
                raise SplunkRateLimited(1.0)
            resp.raise_for_status()
            return resp.json()

        return await self._with_retry(_do)
