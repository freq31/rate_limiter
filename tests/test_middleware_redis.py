"""End-to-end smoke test: the middleware on top of a *real* Redis limiter.

The other middleware tests use an in-memory limiter for speed/determinism; this
one closes the loop by exercising the full HTTP -> middleware -> Redis path,
including the atomic Lua counter and the rate-limit headers.

Driven with httpx.ASGITransport (not the sync TestClient) so the app shares the
test's event loop with the async ``redis_client`` fixture. Skips automatically
when no Redis is available (see conftest).
"""

import httpx
from fastapi import FastAPI

from rate_limiter.main import RateLimiterOrchestrator
from rate_limiter.backend.request import AlgorithmType, RateLimiterType
from rate_limiter.backend.middleware import RateLimiterMiddleware


def _build_app(redis_client) -> FastAPI:
    limiter = RateLimiterOrchestrator(
        rate_limiter_type=RateLimiterType.REDIS,
        algorithm_type=AlgorithmType.FIXED_WINDOW,
        max_requests=3,
        time_window=60,
        redis_client=redis_client,
    )
    app = FastAPI()
    app.add_middleware(
        RateLimiterMiddleware,
        limiter=limiter,
        key_func=lambda r: r.headers.get("X-Client-ID", "anon"),
    )

    @app.get("/ping")
    async def ping():
        return {"message": "pong"}

    return app


async def test_redis_backed_middleware_allows_then_blocks(redis_client):
    app = _build_app(redis_client)
    headers = {"X-Client-ID": "redis-smoke"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        responses = [await client.get("/ping", headers=headers) for _ in range(4)]

    r1, r2, r3, r4 = responses

    # First three allowed, remaining counts down through the real Redis counter.
    assert r1.status_code == 200
    assert r1.headers["X-RateLimit-Limit"] == "3"
    assert r1.headers["X-RateLimit-Remaining"] == "2"
    assert r2.headers["X-RateLimit-Remaining"] == "1"
    assert r3.headers["X-RateLimit-Remaining"] == "0"

    # Fourth is rejected with a Retry-After hint.
    assert r4.status_code == 429
    assert r4.headers["X-RateLimit-Remaining"] == "0"
    assert "Retry-After" in r4.headers


async def test_redis_backed_middleware_isolates_clients(redis_client):
    app = _build_app(redis_client)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Exhaust one client.
        for _ in range(3):
            await client.get("/ping", headers={"X-Client-ID": "heavy"})
        blocked = await client.get("/ping", headers={"X-Client-ID": "heavy"})
        # A different client is unaffected (separate Redis key).
        other = await client.get("/ping", headers={"X-Client-ID": "light"})

    assert blocked.status_code == 429
    assert other.status_code == 200
    assert other.headers["X-RateLimit-Remaining"] == "2"
