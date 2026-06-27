import pytest

from rate_limiter.algorithms.token_bucket import TokenBucketInMemory
from rate_limiter.backend.request import Rules


class TestTokenBucketInMemory:
    @pytest.mark.asyncio
    async def test_allows_up_to_capacity_then_denies(self, clock):
        clock(1000.0)
        # capacity = 5 tokens, refill rate = max_requests / time_window = 0.5 token/s
        algo = TokenBucketInMemory(Rules(max_requests=5, time_window=10))

        for expected_remaining in (4, 3, 2, 1, 0):
            resp = await algo.execute("client-a")
            assert resp.allowed is True
            assert resp.remaining_requests == expected_remaining

        resp = await algo.execute("client-a")
        assert resp.allowed is False
        assert resp.remaining_requests == 0

    @pytest.mark.asyncio
    async def test_refill_replenishes_tokens_after_elapsed_time(self, clock):
        clock(1000.0)
        algo = TokenBucketInMemory(Rules(max_requests=5, time_window=10))

        for _ in range(5):
            assert (await algo.execute("client-a")).allowed is True
        assert (await algo.execute("client-a")).allowed is False  # bucket empty

        clock(1004.0)  # 4s elapsed * 0.5 token/s = 2 tokens refilled
        resp = await algo.execute("client-a")
        assert resp.allowed is True
        assert resp.remaining_requests == 1

    @pytest.mark.asyncio
    async def test_refill_does_not_exceed_bucket_capacity(self, clock):
        clock(1000.0)
        algo = TokenBucketInMemory(Rules(max_requests=5, time_window=10))

        for _ in range(5):
            assert (await algo.execute("client-a")).allowed is True

        clock(2000.0)  # huge elapsed time would refill far beyond capacity
        resp = await algo.execute("client-a")
        assert resp.allowed is True
        # tokens are capped at capacity (5), not the uncapped refill amount
        assert resp.remaining_requests == 4

    @pytest.mark.asyncio
    async def test_reset_clears_client_state(self, clock):
        clock(1000.0)
        algo = TokenBucketInMemory(Rules(max_requests=1, time_window=10))

        assert (await algo.execute("client-a")).allowed is True
        assert (await algo.execute("client-a")).allowed is False

        assert await algo.reset("client-a") is True
        assert (await algo.execute("client-a")).allowed is True
