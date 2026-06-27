import pytest

from rate_limiter.algorithms.fixed_window import FixedWindowInMemory
from rate_limiter.backend.request import Rules


class TestFixedWindowInMemory:
    @pytest.mark.asyncio
    async def test_allows_up_to_max_requests_then_denies(self, clock):
        clock(1000.0)
        algo = FixedWindowInMemory(Rules(max_requests=3, time_window=10))

        for expected_remaining in (2, 1, 0):
            resp = await algo.execute("client-a")
            assert resp.allowed is True
            assert resp.remaining_requests == expected_remaining

        resp = await algo.execute("client-a")
        assert resp.allowed is False
        assert resp.remaining_requests == 0

    @pytest.mark.asyncio
    async def test_window_resets_after_expiry(self, clock):
        clock(1000.0)
        algo = FixedWindowInMemory(Rules(max_requests=2, time_window=10))

        assert (await algo.execute("client-a")).allowed is True
        assert (await algo.execute("client-a")).allowed is True
        assert (await algo.execute("client-a")).allowed is False

        clock(1011.0)  # past the 10s window
        resp = await algo.execute("client-a")
        assert resp.allowed is True
        assert resp.remaining_requests == 1

    @pytest.mark.asyncio
    async def test_clients_are_tracked_independently(self, clock):
        clock(1000.0)
        algo = FixedWindowInMemory(Rules(max_requests=1, time_window=10))

        assert (await algo.execute("client-a")).allowed is True
        assert (await algo.execute("client-a")).allowed is False
        # a different client has its own, unconsumed quota
        assert (await algo.execute("client-b")).allowed is True

    @pytest.mark.asyncio
    async def test_reset_clears_client_state(self, clock):
        clock(1000.0)
        algo = FixedWindowInMemory(Rules(max_requests=1, time_window=10))

        assert (await algo.execute("client-a")).allowed is True
        assert (await algo.execute("client-a")).allowed is False

        assert await algo.reset("client-a") is True

        resp = await algo.execute("client-a")
        assert resp.allowed is True
