import asyncio

import pytest
from redis.asyncio import Redis
from testcontainers.redis import RedisContainer

from src.algorithms.fixed_window import FixedWindowInRedis
from src.rate_limiter.request import Rules


@pytest.fixture(scope="module")
def redis_container():
    """Spins up a real Redis in Docker for the duration of this test module.
    Skips (rather than failing) when Docker isn't available locally - CI is
    expected to have it."""
    try:
        with RedisContainer() as container:
            yield container
    except Exception as e:
        pytest.skip(f"Docker is not available: {e}")


@pytest.fixture
async def redis_client(redis_container):
    client = Redis(
        host=redis_container.get_container_host_ip(),
        port=int(redis_container.get_exposed_port(6379)),
        decode_responses=True,
    )
    yield client
    await client.flushall()
    await client.aclose()


class TestFixedWindowInRedis:
    @pytest.mark.asyncio
    async def test_allows_up_to_max_requests_then_denies(self, redis_client):
        algo = FixedWindowInRedis(
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
    async def test_window_resets_after_ttl_expiry(self, redis_client):
        algo = FixedWindowInRedis(
            Rules(max_requests=1, time_window=1), redis_client=redis_client
        )

        assert (await algo.execute("client-b")).allowed is True
        assert (await algo.execute("client-b")).allowed is False

        await asyncio.sleep(1.2)  # let the Redis key TTL expire

        resp = await algo.execute("client-b")
        assert resp.allowed is True

    @pytest.mark.asyncio
    async def test_clients_are_tracked_independently(self, redis_client):
        algo = FixedWindowInRedis(
            Rules(max_requests=1, time_window=10), redis_client=redis_client
        )

        assert (await algo.execute("client-c")).allowed is True
        assert (await algo.execute("client-c")).allowed is False
        assert (await algo.execute("client-d")).allowed is True

    @pytest.mark.asyncio
    async def test_reset_clears_client_state(self, redis_client):
        algo = FixedWindowInRedis(
            Rules(max_requests=1, time_window=10), redis_client=redis_client
        )

        assert (await algo.execute("client-e")).allowed is True
        assert (await algo.execute("client-e")).allowed is False

        assert await algo.reset("client-e") is True

        resp = await algo.execute("client-e")
        assert resp.allowed is True

    @pytest.mark.asyncio
    async def test_concurrent_requests_across_redis_allow_exactly_max_requests(
        self, redis_client
    ):
        """Proves the Lua script is atomic: many concurrent INCR+EXPIRE calls
        against the same key, from the same process, must never let more than
        max_requests through."""
        max_requests = 10
        algo = FixedWindowInRedis(
            Rules(max_requests=max_requests, time_window=100),
            redis_client=redis_client,
        )

        responses = await asyncio.gather(*(algo.execute("client-f") for _ in range(50)))

        allowed_count = sum(1 for r in responses if r.allowed)
        assert allowed_count == max_requests
