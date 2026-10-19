"""Server-side rate limiting for the public /api/v3 endpoints.

WHY. The evidence layer is free to call and some requests fan out: one
multi-drug report with labels can reach openFDA up to 32 times (8 drugs, 28
pairs, cached per label). Without limits a single script could exhaust the
openFDA quota for every visitor, or keep the instance busy. The frozen
/api/analyze endpoint is a cheap numpy lookup and is left as it was.

DESIGN.
* Standard library only — the lean image carries no rate-limiting package.
* Sliding-window logs per (client, route class, window) and the same per
  route class across all clients ("global"), so one abusive client is stopped
  by its own limit and a crowd is stopped before the external quota is.
* Multi-drug requests have the strictest limits.
* Memory is bounded: at most ``max_clients`` client keys are tracked (least
  recently seen evicted), and each log holds at most ``limit`` timestamps.
* A refused request gets HTTP 429, a ``Retry-After`` header and a JSON body
  saying which limit applied. Accepted requests carry ``X-RateLimit-Limit`` and
  ``X-RateLimit-Remaining`` for the tightest window of their class.
* POST bodies to /api/v3 must declare a Content-Length of at most 16 KiB
  (requests are a few drug names; anything larger is refused before parsing).

CLIENT IDENTITY. Behind Render's proxy every request comes from the proxy's
address, so the client is read from ``X-Forwarded-For``. Render appends to that
header without clearing it, so a caller can PREPEND fake addresses; the entry
the proxy itself added is the right-most one. The key is therefore the entry
``DDINET_PROXY_HOPS`` positions from the right (default 1). With no proxy
(local development) the socket peer address is used. ``GET /api/v3/limits``
returns the key the server sees for the caller, so the setting can be checked
on a deployment by sending a spoofed header (docs/DDINET_V3_DEPLOYMENT.md).

CONFIGURATION (environment):
    DDINET_RATE_LIMIT=off          disable entirely (not for public deployments)
    DDINET_PROXY_HOPS=1            trusted proxies in front of the app; 0 = ignore
                                   X-Forwarded-For and use the socket peer
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Callable

MAX_BODY_BYTES = 16 * 1024
PREFIX = "/api/v3/"


@dataclass(frozen=True)
class Window:
    limit: int
    seconds: int

    def describe(self) -> str:
        return f"{self.limit} per {self.seconds} s"


#: Per-client limits by route class. Chosen for a person using the site: the
#: Mechanisms page issues two requests per pair change, the Analyzer one.
CLIENT_POLICY: dict[str, tuple[Window, ...]] = {
    "resolve": (Window(60, 60), Window(600, 3600)),
    "pair": (Window(30, 60), Window(300, 3600)),     # /report, /graph
    "multi": (Window(4, 60), Window(30, 3600)),      # /multi — strictest
    "meta": (Window(20, 60),),                       # /sources, /limits, unknown paths
}

#: Limits across all clients together, by route class.
GLOBAL_POLICY: dict[str, tuple[Window, ...]] = {
    "resolve": (Window(1200, 60),),
    "pair": (Window(600, 60),),
    "multi": (Window(40, 60), Window(600, 3600)),
    "meta": (Window(300, 60),),
}


def route_class(path: str) -> str | None:
    """The limit class of a path, or None when it is not rate limited."""
    if not path.startswith(PREFIX):
        return None
    tail = path[len(PREFIX):].strip("/")
    if tail == "resolve":
        return "resolve"
    if tail in ("report", "graph"):
        return "pair"
    if tail == "multi":
        return "multi"
    return "meta"


def client_key(scope: dict, proxy_hops: int) -> str:
    """Right-most trusted X-Forwarded-For entry, else the socket peer."""
    if proxy_hops > 0:
        for name, value in scope.get("headers") or []:
            if name == b"x-forwarded-for":
                parts = [p.strip() for p in value.decode("latin-1").split(",") if p.strip()]
                if len(parts) >= proxy_hops:
                    return parts[-proxy_hops]
                break
    client = scope.get("client")
    return client[0] if client else "unknown"


@dataclass
class Decision:
    allowed: bool
    scope: str = "client"            # which policy refused: client | global
    window: Window | None = None
    retry_after: int = 0
    limit: int = 0
    remaining: int = 0


class RateLimiter:
    def __init__(self, client_policy=None, global_policy=None, *, max_clients: int = 20_000,
                 clock: Callable[[], float] = time.monotonic, enabled: bool | None = None,
                 proxy_hops: int | None = None) -> None:
        self.client_policy = client_policy or CLIENT_POLICY
        self.global_policy = global_policy or GLOBAL_POLICY
        self.max_clients = max_clients
        self.clock = clock
        if enabled is None:
            enabled = os.environ.get("DDINET_RATE_LIMIT", "on").lower() not in ("off", "0", "false")
        self.enabled = enabled
        if proxy_hops is None:
            proxy_hops = int(os.environ.get("DDINET_PROXY_HOPS", "1"))
        self.proxy_hops = max(0, proxy_hops)
        self._lock = threading.Lock()
        self._clients: OrderedDict[str, dict[tuple[str, int], deque]] = OrderedDict()
        self._global: dict[tuple[str, int], deque] = {}

    def reset(self) -> None:
        with self._lock:
            self._clients.clear()
            self._global.clear()

    @staticmethod
    def _check(log: deque, w: Window, now: float) -> tuple[bool, int, int]:
        """(allowed, retry_after_s, remaining_after_this_request)."""
        cutoff = now - w.seconds
        while log and log[0] <= cutoff:
            log.popleft()
        if len(log) >= w.limit:
            return False, max(1, math.ceil(log[0] + w.seconds - now)), 0
        return True, 0, w.limit - len(log) - 1

    def hit(self, key: str, cls: str) -> Decision:
        """Count one request of class ``cls`` from ``key`` if every window allows it."""
        now = self.clock()
        with self._lock:
            logs = self._clients.get(key)
            if logs is None:
                logs = {}
                self._clients[key] = logs
                while len(self._clients) > self.max_clients:
                    self._clients.popitem(last=False)
            else:
                self._clients.move_to_end(key)
            checks = []
            for w in self.client_policy.get(cls, ()):
                checks.append(("client", w, logs.setdefault((cls, w.seconds), deque())))
            for w in self.global_policy.get(cls, ()):
                checks.append(("global", w, self._global.setdefault((cls, w.seconds), deque())))
            tightest = None
            for scope, w, log in checks:
                ok, retry, remaining = self._check(log, w, now)
                if not ok:
                    return Decision(False, scope, w, retry, w.limit, 0)
                if scope == "client" and (tightest is None or remaining < tightest[1]):
                    tightest = (w.limit, remaining)
            for _, _, log in checks:
                log.append(now)
            limit, remaining = tightest if tightest else (0, 0)
            return Decision(True, limit=limit, remaining=remaining)

    def describe(self) -> dict:
        return {
            "enabled": self.enabled,
            "per_client": {k: [w.describe() for w in v] for k, v in self.client_policy.items()},
            "global": {k: [w.describe() for w in v] for k, v in self.global_policy.items()},
            "max_body_bytes": MAX_BODY_BYTES,
            "proxy_hops": self.proxy_hops,
        }


#: Process-wide limiter. One worker process (see the Dockerfiles), so in-memory
#: state is the whole state; with several workers each would count separately.
limiter = RateLimiter()


async def _send_json(send, status: int, body: dict, headers: list[tuple[bytes, bytes]] = ()) -> None:
    payload = json.dumps(body).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(payload)).encode()), *headers]})
    await send({"type": "http.response.body", "body": payload})


class RateLimitMiddleware:
    """Pure ASGI middleware; install inside CORS so 429s still carry CORS headers."""

    def __init__(self, app, limiter_: RateLimiter | None = None) -> None:
        self.app = app
        self.limiter = limiter_ or limiter

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self.limiter.enabled:
            return await self.app(scope, receive, send)
        cls = route_class(scope.get("path", ""))
        if cls is None or scope.get("method") == "OPTIONS":
            return await self.app(scope, receive, send)

        if scope.get("method") == "POST":
            length = None
            for name, value in scope.get("headers") or []:
                if name == b"content-length":
                    try:
                        length = int(value)
                    except ValueError:
                        length = None
            if length is None:
                return await _send_json(send, 411, {"detail": "Content-Length is required."})
            if length > MAX_BODY_BYTES:
                return await _send_json(send, 413, {"detail": f"Request body over {MAX_BODY_BYTES} bytes."})

        key = client_key(scope, self.limiter.proxy_hops)
        d = self.limiter.hit(key, cls)
        if not d.allowed:
            who = "this client" if d.scope == "client" else "all clients together"
            return await _send_json(send, 429, {"detail": {
                "message": f"Rate limit reached for {who}: {d.window.describe()} on {cls} requests. "
                           "Please try again shortly.",
                "retry_after_seconds": d.retry_after,
                "scope": d.scope,
                "route_class": cls,
            }}, [(b"retry-after", str(d.retry_after).encode())])

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers += [(b"x-ratelimit-limit", str(d.limit).encode()),
                            (b"x-ratelimit-remaining", str(d.remaining).encode())]
                message = {**message, "headers": headers}
            await send(message)

        return await self.app(scope, receive, send_with_headers)
