"""Rate limiting and readiness for a public deployment of /api/v3.

Unit tests drive the limiter with a fake clock; HTTP tests go through the real
app stack (CORS outside, limiter inside) with FastAPI's TestClient.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from serving.evidence.adapters.http import HttpClient, SourceUnavailable
from serving.ratelimit import (
    CLIENT_POLICY, GLOBAL_POLICY, MAX_BODY_BYTES, RateLimiter, Window, client_key, limiter, route_class,
)

from test_v3_evidence import real, real_artifact  # noqa: F401  (session fixtures)


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def scope(xff: str | None = None, peer: str = "10.0.0.9") -> dict:
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return {"headers": headers, "client": (peer, 1234)}


# ---------------------------------------------------------------- units ----
def test_route_classes():
    assert route_class("/api/v3/multi") == "multi"
    assert route_class("/api/v3/report") == route_class("/api/v3/graph") == "pair"
    assert route_class("/api/v3/resolve") == "resolve"
    assert route_class("/api/v3/sources") == route_class("/api/v3/nonexistent") == "meta"
    assert route_class("/api/analyze") is None and route_class("/api/health") is None


def test_multi_is_the_strictest_class():
    per_min = {k: next(w.limit for w in v if w.seconds == 60) for k, v in CLIENT_POLICY.items()}
    assert per_min["multi"] == min(per_min.values())
    assert per_min["multi"] < per_min["pair"] < per_min["resolve"]


def test_client_key_uses_the_proxy_appended_entry():
    # Render appends the real address; a caller can only prepend fakes.
    assert client_key(scope("6.6.6.6, 203.0.113.7"), 1) == "203.0.113.7"
    assert client_key(scope("203.0.113.7"), 1) == "203.0.113.7"
    assert client_key(scope("6.6.6.6, 203.0.113.7, 10.1.1.1"), 2) == "203.0.113.7"
    assert client_key(scope(None), 1) == "10.0.0.9"                 # no proxy: socket peer
    assert client_key(scope("6.6.6.6"), 0) == "10.0.0.9"            # header ignored when hops=0


def test_window_allows_limit_then_refuses_with_retry_after():
    clock = Clock()
    rl = RateLimiter({"multi": (Window(3, 60),)}, {}, clock=clock, enabled=True)
    assert [rl.hit("a", "multi").allowed for _ in range(3)] == [True, True, True]
    d = rl.hit("a", "multi")
    assert not d.allowed and d.scope == "client" and 1 <= d.retry_after <= 60
    assert rl.hit("b", "multi").allowed, "another client has its own window"
    clock.t += 61
    assert rl.hit("a", "multi").allowed, "the window slides"


def test_refused_requests_do_not_extend_the_wait():
    clock = Clock()
    rl = RateLimiter({"pair": (Window(1, 60),)}, {}, clock=clock, enabled=True)
    rl.hit("a", "pair")
    for _ in range(50):
        clock.t += 1
        rl.hit("a", "pair")
    clock.t = 1000.0 + 61
    assert rl.hit("a", "pair").allowed


def test_global_limit_spans_clients():
    rl = RateLimiter({"multi": (Window(100, 60),)}, {"multi": (Window(5, 60),)}, clock=Clock(), enabled=True)
    allowed = [rl.hit(f"client{i}", "multi").allowed for i in range(7)]
    assert allowed == [True] * 5 + [False] * 2
    assert rl.hit("client99", "multi").scope == "global"


def test_tracked_clients_are_bounded():
    rl = RateLimiter({"pair": (Window(5, 60),)}, {}, clock=Clock(), enabled=True, max_clients=100)
    for i in range(1000):
        rl.hit(f"c{i}", "pair")
    assert len(rl._clients) == 100


def test_external_daily_budget_stops_network_calls_not_cache_hits():
    calls = []

    def transport(url, timeout):
        calls.append(url)
        return 200, b"{}"

    http = HttpClient(transport=transport, enabled=True, daily_budget={"openfda_label": 2})
    http.get_json("openfda_label", "https://x.invalid/1")
    http.get_json("openfda_label", "https://x.invalid/2")
    http.get_json("openfda_label", "https://x.invalid/1")          # cached: free
    with pytest.raises(SourceUnavailable, match="budget"):
        http.get_json("openfda_label", "https://x.invalid/3")
    assert len(calls) == 2
    assert http.budget_status()["spent"]["openfda_label"] == 2


# ----------------------------------------------------------------- HTTP ----
@pytest.fixture()
def app_client(real_artifact, monkeypatch):  # noqa: F811
    import serving.api as api
    import serving.evidence.store as store_mod

    monkeypatch.setattr(store_mod, "ARTIFACT", real_artifact)
    monkeypatch.setattr(api, "ALLOW_NO_MODEL", True)
    monkeypatch.setenv("DDINET_EXTERNAL_SOURCES", "off")
    assert limiter.enabled, "public limits must be on by default"
    limiter.reset()
    with TestClient(api.app) as c:
        yield c
    limiter.reset()


def test_multi_limit_returns_429_with_retry_after_and_cors(app_client):
    per_min = next(w.limit for w in CLIENT_POLICY["multi"] if w.seconds == 60)
    body = {"drugs": ["warfarin", "fluconazole"], "include_labels": False}
    headers = {"Origin": "https://example.org"}
    for _ in range(per_min):
        ok = app_client.post("/api/v3/multi", json=body, headers=headers)
        assert ok.status_code == 200
        assert "x-ratelimit-remaining" in ok.headers
    r = app_client.post("/api/v3/multi", json=body, headers=headers)
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) >= 1
    assert r.json()["detail"]["route_class"] == "multi"
    assert r.headers.get("access-control-allow-origin") == "*", "the browser must be able to read the 429"
    # other classes are unaffected
    assert app_client.post("/api/v3/report", json={"drug_a": "warfarin", "drug_b": "fluconazole",
                                                   "include_labels": False}).status_code == 200


def test_clients_behind_the_proxy_are_counted_separately(app_client):
    per_min = next(w.limit for w in CLIENT_POLICY["multi"] if w.seconds == 60)
    body = {"drugs": ["warfarin", "fluconazole"], "include_labels": False}
    for _ in range(per_min):
        app_client.post("/api/v3/multi", json=body, headers={"X-Forwarded-For": "198.51.100.1"})
    assert app_client.post("/api/v3/multi", json=body, headers={"X-Forwarded-For": "198.51.100.1"}).status_code == 429
    # Spoofing a prefix does not help: the right-most entry is still the same client.
    spoof = {"X-Forwarded-For": "1.2.3.4, 198.51.100.1"}
    assert app_client.post("/api/v3/multi", json=body, headers=spoof).status_code == 429
    assert app_client.post("/api/v3/multi", json=body, headers={"X-Forwarded-For": "198.51.100.2"}).status_code == 200


def test_limits_endpoint_reports_the_key_the_server_sees(app_client):
    r = app_client.get("/api/v3/limits", headers={"X-Forwarded-For": "6.6.6.6, 203.0.113.7"}).json()
    assert r["your_client_key"] == "203.0.113.7"
    assert r["rate_limits"]["enabled"] is True
    assert "multi" in r["rate_limits"]["per_client"]
    assert "external_daily_budget" in r


def test_oversized_body_is_refused_before_parsing(app_client):
    big = {"drugs": ["warfarin"] * 2, "pad": "x" * (MAX_BODY_BYTES + 1)}
    assert app_client.post("/api/v3/multi", json=big).status_code == 413


def test_frozen_endpoints_are_not_rate_limited(app_client):
    for _ in range(next(w.limit for w in CLIENT_POLICY["meta"] if w.seconds == 60) + 5):
        assert app_client.get("/api/health").status_code == 200


def test_readiness_requires_model_and_evidence(app_client, monkeypatch):
    import serving.api as api
    import serving.api_v3 as v3

    r = app_client.get("/api/health/ready")
    expected = 200 if api._engine is not None else 503
    assert r.status_code == expected
    monkeypatch.setattr(v3, "_engine", None)
    r = app_client.get("/api/health/ready")
    assert r.status_code == 503 and r.json()["evidence_available"] is False


def test_require_evidence_fails_startup_when_the_artifact_is_missing(tmp_path, monkeypatch):
    import serving.api as api
    import serving.evidence.store as store_mod

    monkeypatch.setattr(store_mod, "ARTIFACT", tmp_path / "absent.json.gz")
    monkeypatch.setattr(api, "REQUIRE_EVIDENCE", True)
    with pytest.raises(Exception, match="evidence artifact missing"):
        api._start_evidence()


def test_global_policy_covers_every_class():
    assert set(GLOBAL_POLICY) == set(CLIENT_POLICY)
