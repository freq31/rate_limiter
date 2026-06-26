"""Tests for RateLimiterMiddleware.

These run entirely in-memory (no Redis), so they're deterministic and fast.
A fixed-window in-memory limiter with max_requests=2 gives a simple sequence:
req1 -> 200 (remaining 1), req2 -> 200 (remaining 0), req3 -> 429.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.main import RateLimiterOrchestrator
from src.rate_limiter.request import AlgorithmType, RateLimiterType
from src.rate_limiter.response import Response
from src.rate_limiter.middleware import RateLimiterMiddleware


def _build_app(limiter, **mw_kwargs) -> FastAPI:
    """Build a tiny app guarded by the middleware under test."""
    app = FastAPI()
    app.add_middleware(RateLimiterMiddleware, limiter=limiter, **mw_kwargs)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/ping")
    async def ping():
        return {"message": "pong"}

    return app


def _in_memory_limiter(max_requests=2, time_window=60) -> RateLimiterOrchestrator:
    return RateLimiterOrchestrator(
        rate_limiter_type=RateLimiterType.IN_MEMORY,
        algorithm_type=AlgorithmType.FIXED_WINDOW,
        max_requests=max_requests,
        time_window=time_window,
    )


class _StubLimiter:
    """Minimal limiter whose get_response always raises (to test error paths)."""

    def get_rules(self):  # pragma: no cover - not reached on the error path
        raise AssertionError("get_rules should not be called when get_response fails")

    async def get_response(self, client_id: str) -> Response:
        raise RuntimeError("backend down")


# --- happy path -----------------------------------------------------------


def test_allowed_request_returns_200_with_headers():
    client = TestClient(_build_app(_in_memory_limiter()))
    r = client.get("/ping", headers={"X-Client-ID": "alice"})

    assert r.status_code == 200
    assert r.json() == {"message": "pong"}
    assert r.headers["X-RateLimit-Limit"] == "2"
    assert r.headers["X-RateLimit-Remaining"] == "1"
    assert "X-RateLimit-Reset" in r.headers


def test_remaining_decrements_then_429():
    app = _build_app(
        _in_memory_limiter(),
        key_func=lambda req: req.headers.get("X-Client-ID", "anon"),
    )
    client = TestClient(app)
    h = {"X-Client-ID": "bob"}

    r1 = client.get("/ping", headers=h)
    r2 = client.get("/ping", headers=h)
    r3 = client.get("/ping", headers=h)

    assert (r1.status_code, r1.headers["X-RateLimit-Remaining"]) == (200, "1")
    assert (r2.status_code, r2.headers["X-RateLimit-Remaining"]) == (200, "0")
    assert r3.status_code == 429
    assert r3.headers["X-RateLimit-Remaining"] == "0"
    assert "Retry-After" in r3.headers


# --- key separation -------------------------------------------------------


def test_distinct_clients_have_independent_buckets():
    app = _build_app(
        _in_memory_limiter(),
        key_func=lambda req: req.headers.get("X-Client-ID", "anon"),
    )
    client = TestClient(app)

    # Exhaust alice's budget.
    client.get("/ping", headers={"X-Client-ID": "alice"})
    client.get("/ping", headers={"X-Client-ID": "alice"})
    assert client.get("/ping", headers={"X-Client-ID": "alice"}).status_code == 429

    # bob is unaffected.
    assert client.get("/ping", headers={"X-Client-ID": "bob"}).status_code == 200


# --- exclusions -----------------------------------------------------------


def test_excluded_route_is_never_limited():
    app = _build_app(_in_memory_limiter(), exclude_routes=["/health"])
    client = TestClient(app)

    for _ in range(5):
        r = client.get("/health")
        assert r.status_code == 200
    # Excluded routes bypass the limiter entirely -> no rate-limit headers.
    assert "X-RateLimit-Limit" not in r.headers


# --- async key_func -------------------------------------------------------


def test_async_key_func_is_awaited():
    async def akey(req):
        return req.headers.get("X-Client-ID", "anon")

    app = _build_app(_in_memory_limiter(), key_func=akey)
    client = TestClient(app)
    assert client.get("/ping", headers={"X-Client-ID": "z"}).status_code == 200


# --- failure policy -------------------------------------------------------


def test_fail_open_lets_traffic_through_when_limiter_errors():
    app = _build_app(_StubLimiter(), fail_open=True)
    client = TestClient(app)
    r = client.get("/ping")
    assert r.status_code == 200
    assert "X-RateLimit-Limit" not in r.headers  # no headers when limiter failed


def test_fail_closed_returns_503_when_limiter_errors():
    app = _build_app(_StubLimiter(), fail_open=False)
    client = TestClient(app)
    r = client.get("/ping")
    assert r.status_code == 503
    assert r.json()["detail"] == "rate limiter unavailable"
