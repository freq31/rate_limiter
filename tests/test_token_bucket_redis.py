import asyncio

import pytest

from rate_limiter.algorithms.token_bucket import TokenBucketInRedis
from rate_limiter.backend.request import Rules


class TestTokenBucketInRedis:
    @pytest.mark.asyncio
    async def test_drains_full_bucket_then_denies(self, redis_client):
        # First request seeds a full bucket of max_requests tokens. With a slow
        # refill (5 tokens / 60s) and back-to-back calls, effectively no tokens
        # refill between them, so exactly max_requests should pass.
        algo = TokenBucketInRedis(
            Rules(max_requests=5, time_window=60), redis_client=redis_client
        )

        for expected_remaining in (4, 3, 2, 1, 0):
            resp = await algo.execute("client-a")
            assert resp.allowed is True
            assert resp.remaining_requests == expected_remaining

        resp = await algo.execute("client-a")
        assert resp.allowed is False
        assert resp.remaining_requests == 0

    @pytest.mark.asyncio
    async def test_refills_over_time(self, redis_client):
        # 2 tokens / 1s => refill rate of 2 tokens per second.
        algo = TokenBucketInRedis(
            Rules(max_requests=2, time_window=1), redis_client=redis_client
        )

        assert (await algo.execute("client-b")).allowed is True
        assert (await algo.execute("client-b")).allowed is True
        assert (await algo.execute("client-b")).allowed is False  # bucket empty

        await asyncio.sleep(1.1)  # ~2 tokens refill

        resp = await algo.execute("client-b")
        assert resp.allowed is True

    @pytest.mark.asyncio
    async def test_refill_does_not_exceed_capacity(self, redis_client):
        algo = TokenBucketInRedis(
            Rules(max_requests=3, time_window=1), redis_client=redis_client
        )

        # drain the bucket
        for _ in range(3):
            assert (await algo.execute("client-c")).allowed is True
        assert (await algo.execute("client-c")).allowed is False

        await asyncio.sleep(2.0)  # long enough to refill far beyond capacity

        # capacity is capped at 3: should allow exactly 3, not more
        allowed = 0
        for _ in range(5):
            if (await algo.execute("client-c")).allowed:
                allowed += 1
        assert allowed == 3

    @pytest.mark.asyncio
    async def test_deny_reports_positive_reset_time(self, redis_client):
        algo = TokenBucketInRedis(
            Rules(max_requests=1, time_window=10), redis_client=redis_client
        )

        assert (await algo.execute("client-d")).allowed is True
        resp = await algo.execute("client-d")
        assert resp.allowed is False
        # time for one token to accrue at 1 token / 10s == ~10s
        assert 0 < resp.reset_time <= 10

    @pytest.mark.asyncio
    async def test_clients_are_tracked_independently(self, redis_client):
        algo = TokenBucketInRedis(
            Rules(max_requests=1, time_window=60), redis_client=redis_client
        )

        assert (await algo.execute("client-e")).allowed is True
        assert (await algo.execute("client-e")).allowed is False
        assert (await algo.execute("client-f")).allowed is True

    @pytest.mark.asyncio
    async def test_key_has_ttl_set(self, redis_client):
        # The bucket hash must expire so idle clients don't leak memory.
        algo = TokenBucketInRedis(
            Rules(max_requests=5, time_window=30), redis_client=redis_client
        )

        await algo.execute("client-g")
        ttl = await redis_client.ttl("rl:token_bucket:client-g")
        assert 0 < ttl <= 30

    @pytest.mark.asyncio
    async def test_reset_clears_client_state(self, redis_client):
        algo = TokenBucketInRedis(
            Rules(max_requests=1, time_window=60), redis_client=redis_client
        )

        assert (await algo.execute("client-h")).allowed is True
        assert (await algo.execute("client-h")).allowed is False

        assert await algo.reset("client-h") is True

        resp = await algo.execute("client-h")
        assert resp.allowed is True

    @pytest.mark.asyncio
    async def test_concurrent_requests_allow_exactly_capacity(self, redis_client):
        """Proves the Lua script is atomic: 50 concurrent refill-and-consume
        sequences against one bucket must never let more than max_requests
        through (with a slow refill, no extra tokens accrue mid-burst)."""
        max_requests = 10
        algo = TokenBucketInRedis(
            Rules(max_requests=max_requests, time_window=600),
            redis_client=redis_client,
        )

        responses = await asyncio.gather(*(algo.execute("client-i") for _ in range(50)))

        allowed_count = sum(1 for r in responses if r.allowed)
        assert allowed_count == max_requests
