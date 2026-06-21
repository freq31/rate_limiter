import pytest

from src.algorithms.sliding_window import SlidingWindowInMemory
from src.rate_limiter.request import Rules


class TestSlidingWindowInMemory:
    @pytest.mark.asyncio
    async def test_allows_up_to_max_requests_then_denies(self, clock):
        clock(1000.0)
        algo = SlidingWindowInMemory(Rules(max_requests=3, time_window=10))

        for expected_remaining in (2, 1, 0):
            resp = await algo.execute("client-a")
            assert resp.allowed is True
            assert resp.remaining_requests == expected_remaining

        resp = await algo.execute("client-a")
        assert resp.allowed is False

    @pytest.mark.asyncio
    async def test_previous_window_weight_decays_over_time(self, clock):
        rules = Rules(max_requests=5, time_window=10)
        algo = SlidingWindowInMemory(rules)

        clock(1000.0)
        for _ in range(5):
            assert (await algo.execute("client-a")).allowed is True
        # current window is full; further requests in the same window are denied
        assert (await algo.execute("client-a")).allowed is False

        # just past the window boundary: the new window inherits the old one's
        # full count as "previous window", so capacity is still exhausted
        clock(1015.0)
        assert (await algo.execute("client-a")).allowed is False

        # further into the new window, the previous window's weight has decayed
        # enough (60% gone) that capacity frees up
        clock(1021.0)
        resp = await algo.execute("client-a")
        assert resp.allowed is True

    @pytest.mark.asyncio
    async def test_reset_clears_client_state(self, clock):
        clock(1000.0)
        algo = SlidingWindowInMemory(Rules(max_requests=1, time_window=10))

        assert (await algo.execute("client-a")).allowed is True
        assert (await algo.execute("client-a")).allowed is False

        assert await algo.reset("client-a") is True
        assert (await algo.execute("client-a")).allowed is True
