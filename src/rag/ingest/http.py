"""Polite HTTP: honest User-Agent, robots.txt, per-host rate limiting and retries."""

import logging
import threading
import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from rag.config import settings

log = logging.getLogger(__name__)


class RetryableHTTPError(Exception):
    pass


class Fetcher:
    def __init__(self, min_interval: float = 1.0, timeout: float = 25.0):
        self.client = httpx.Client(
            headers={"User-Agent": settings.user_agent},
            timeout=timeout,
            follow_redirects=True,
        )
        self.min_interval = min_interval
        self._robots: dict[str, RobotFileParser | None] = {}
        self._last_hit: dict[str, float] = {}
        self._lock = threading.Lock()

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        host = f"{parts.scheme}://{parts.netloc}"
        if host not in self._robots:
            try:
                r = self.client.get(f"{host}/robots.txt")
                if r.status_code >= 500:
                    self._robots[host] = None
                else:
                    rp = RobotFileParser()
                    rp.parse(r.text.splitlines() if r.status_code == 200 else [])
                    self._robots[host] = rp
            except httpx.HTTPError:
                self._robots[host] = None
        rp = self._robots[host]
        return rp is not None and rp.can_fetch(settings.user_agent, url)

    def _throttle(self, url: str) -> None:
        host = urlsplit(url).netloc
        with self._lock:
            wait = self._last_hit.get(host, 0) + self.min_interval - time.monotonic()
            self._last_hit[host] = time.monotonic() + max(wait, 0)
        if wait > 0:
            time.sleep(wait)

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, RetryableHTTPError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, max=30),
        reraise=True,
    )
    def get(self, url: str, params: dict | None = None, check_robots: bool = True) -> httpx.Response:
        if check_robots and not self.allowed(url):
            raise PermissionError(f"robots.txt disallows {url}")
        self._throttle(url)
        r = self.client.get(url, params=params)
        if r.status_code == 429 or r.status_code >= 500:
            raise RetryableHTTPError(f"{r.status_code} for {url}")
        r.raise_for_status()
        return r

    def close(self) -> None:
        self.client.close()
