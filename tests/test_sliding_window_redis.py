import asyncio

import pytest

from src.algorithms.sliding_window import SlidingWindowInRedis
from src.rate_limiter.request import Rules


class TestSlidingWindowInRedis:
    @pytest.mark.asyncio
    async def test_allows_up_to_max_requests_then_denies(self, redis_client):
        algo = SlidingWindowInRedis(
            Rules(max_requests=3, time_window=10), redis_client=redis_client
        )

        for expected_remaining in (2, 1, 0):
            resp = await algo.execute("client-a")
            assert resp.allowed is True
            assert resp.remaining_requests == expected_remaining

        resp = await algo.execute("client-a")
        assert resp.allowed is False
        assert resp.remaining_requests == 0

    @pytest.mark.asyncio
    async def test_window_slides_as_old_entries_age_out(self, redis_client):
        # 2 requests per 1 second window. After the first two fill the window,
        # the third is denied until the oldest entry ages past the window.
        algo = SlidingWindowInRedis(
            Rules(max_requests=2, time_window=1), redis_client=redis_client
        )

        assert (await algo.execute("client-b")).allowed is True
        assert (await algo.execute("client-b")).allowed is True
        assert (await algo.execute("client-b")).allowed is False

        await asyncio.sleep(1.1)  # let both timestamps slide out of the window

        resp = await algo.execute("client-b")
        assert resp.allowed is True

    @pytest.mark.asyncio
    async def test_deny_reports_positive_reset_time(self, redis_client):
        algo = SlidingWindowInRedis(
            Rules(max_requests=1, time_window=10), redis_client=redis_client
        )

        assert (await algo.execute("client-c")).allowed is True
        resp = await algo.execute("client-c")
        assert resp.allowed is False
        # reset_time is "when the oldest entry leaves the window"; just under
        # the full window since almost no time has passed.
        assert 0 < resp.reset_time <= 10

    @pytest.mark.asyncio
    async def test_clients_are_tracked_independently(self, redis_client):
        algo = SlidingWindowInRedis(
            Rules(max_requests=1, time_window=10), redis_client=redis_client
        )

        assert (await algo.execute("client-d")).allowed is True
        assert (await algo.execute("client-d")).allowed is False
        assert (await algo.execute("client-e")).allowed is True

    @pytest.mark.asyncio
    async def test_key_has_ttl_set(self, redis_client):
        # The sorted set must expire so idle clients don't leak memory.
        algo = SlidingWindowInRedis(
            Rules(max_requests=5, time_window=30), redis_client=redis_client
        )

        await algo.execute("client-f")
        ttl = await redis_client.ttl("rl:sliding_window:client-f")
        assert 0 < ttl <= 30

    @pytest.mark.asyncio
    async def test_reset_clears_client_state(self, redis_client):
        algo = SlidingWindowInRedis(
            Rules(max_requests=1, time_window=10), redis_client=redis_client
        )

        assert (await algo.execute("client-g")).allowed is True
        assert (await algo.execute("client-g")).allowed is False

        assert await algo.reset("client-g") is True

        resp = await algo.execute("client-g")
        assert resp.allowed is True

    @pytest.mark.asyncio
    async def test_concurrent_requests_allow_exactly_max_requests(self, redis_client):
        """Proves the Lua script is atomic: 50 concurrent ZREMRANGEBYSCORE +
        ZCARD + ZADD sequences against one key must never let more than
        max_requests through."""
        max_requests = 10
        algo = SlidingWindowInRedis(
            Rules(max_requests=max_requests, time_window=100),
            redis_client=redis_client,
        )

        responses = await asyncio.gather(*(algo.execute("client-h") for _ in range(50)))

        allowed_count = sum(1 for r in responses if r.allowed)
        assert allowed_count == max_requests
