"""Minimal JSON-over-HTTPS client: standard library only, cached, fail-loud.

* No third-party HTTP library: the lean image carries numpy and a web server.
* A transport function can be injected, which is how the tests run every
  adapter against recorded response shapes without touching the network.
* A source that fails is put on a short cooldown, so a multi-drug request does
  not wait out the same timeout once per pair.
"""

from __future__ import annotations

import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from typing import Callable

#: (url, timeout) -> (status, body bytes). Raises OSError on network failure.
Transport = Callable[[str, float], tuple[int, bytes]]

USER_AGENT = "DDI-Net/3.0 research prototype (+https://github.com/mametaeverzat014-cell/DDI-Net)"


class SourceUnavailable(RuntimeError):
    """The source could not be consulted. Distinct from 'consulted, no match'."""


def urllib_transport(url: str, timeout: float) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    ctx = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or None)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() if e.fp else b""


class HttpClient:
    def __init__(self, transport: Transport | None = None, timeout: float = 6.0,
                 ttl_seconds: float = 24 * 3600, max_entries: int = 2048,
                 cooldown_seconds: float = 60.0, enabled: bool | None = None) -> None:
        self.transport = transport or urllib_transport
        self.timeout = timeout
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self.cooldown = cooldown_seconds
        if enabled is None:
            enabled = os.environ.get("DDINET_EXTERNAL_SOURCES", "on").lower() not in ("off", "0", "false")
        self.enabled = enabled
        self._cache: OrderedDict[str, tuple[float, int, object]] = OrderedDict()
        self._down_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def get_json(self, source: str, url: str) -> tuple[int, object]:
        """Return (status, parsed JSON). 404 is a normal answer, not an error."""
        if not self.enabled:
            raise SourceUnavailable(f"{source}: external sources are disabled on this deployment")
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(url)
            if hit and now - hit[0] < self.ttl:
                self._cache.move_to_end(url)
                return hit[1], hit[2]
            if self._down_until.get(source, 0) > now:
                raise SourceUnavailable(f"{source}: recently unreachable; retrying after a cooldown")
        try:
            status, body = self.transport(url, self.timeout)
        except (OSError, TimeoutError) as exc:
            self._mark_down(source)
            raise SourceUnavailable(f"{source}: network error ({type(exc).__name__})") from exc
        if status in (403, 407) or status >= 500:
            self._mark_down(source)
            raise SourceUnavailable(f"{source}: HTTP {status}")
        if status == 429:
            self._mark_down(source)
            raise SourceUnavailable(f"{source}: rate limited (HTTP 429)")
        try:
            data = json.loads(body.decode("utf-8")) if body else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SourceUnavailable(f"{source}: response was not JSON") from exc
        if status in (200, 404):
            with self._lock:
                self._cache[url] = (now, status, data)
                while len(self._cache) > self.max_entries:
                    self._cache.popitem(last=False)
        return status, data

    def _mark_down(self, source: str) -> None:
        with self._lock:
            self._down_until[source] = time.monotonic() + self.cooldown
