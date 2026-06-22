import os
import time

import pytest
from redis.asyncio import Redis


@pytest.fixture
def clock(monkeypatch):
    """Freeze time.time() and let tests advance it explicitly."""
    state = {"t": 0.0}
    monkeypatch.setattr(time, "time", lambda: state["t"])

    def set_time(t: float) -> None:
        state["t"] = t

    return set_time


@pytest.fixture(scope="session")
def redis_endpoint():
    """Provide a (host, port) for the Redis integration tests.

    Two modes, in priority order:
      1. REDIS_HOST is set (CI / docker-compose) -> connect to it directly.
      2. Otherwise spin up a throwaway Redis via testcontainers (local dev
         with a Docker daemon).
    If neither is available, the dependent tests skip rather than fail.
    """
    host = os.getenv("REDIS_HOST")
    if host:
        yield (host, int(os.getenv("REDIS_PORT", "6379")))
        return

    try:
        from testcontainers.redis import RedisContainer

        with RedisContainer() as container:
            yield (
                container.get_container_host_ip(),
                int(container.get_exposed_port(6379)),
            )
    except Exception as e:
        pytest.skip(f"No Redis available (set REDIS_HOST or start Docker): {e}")


@pytest.fixture
async def redis_client(redis_endpoint):
    host, port = redis_endpoint
    client = Redis(host=host, port=port, decode_responses=True)
    yield client
    await client.flushall()
    await client.aclose()
