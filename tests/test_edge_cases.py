"""Edge-case and failure-policy tests.

Covers rule validation, boundary limits, and the algorithm-level behaviour when
the Redis backend errors (the algorithms fail closed -> request denied).
"""

import pytest

from rate_limiter.main import RateLimiterOrchestrator
from rate_limiter.backend.request import AlgorithmType, RateLimiterType

# --- rule validation ------------------------------------------------------


@pytest.mark.parametrize("time_window", [0, -1, -60])
def test_non_positive_time_window_is_rejected(time_window):
    with pytest.raises(ValueError, match="Time window must be a positive integer"):
        RateLimiterOrchestrator(
            rate_limiter_type=RateLimiterType.IN_MEMORY,
            algorithm_type=AlgorithmType.FIXED_WINDOW,
            max_requests=5,
            time_window=time_window,
        )


@pytest.mark.parametrize("max_requests", [0, -1, -10])
def test_non_positive_max_requests_is_rejected(max_requests):
    with pytest.raises(ValueError, match="Max requests must be a positive integer"):
        RateLimiterOrchestrator(
            rate_limiter_type=RateLimiterType.IN_MEMORY,
            algorithm_type=AlgorithmType.FIXED_WINDOW,
            max_requests=max_requests,
            time_window=60,
        )


def test_redis_type_without_client_is_rejected():
    with pytest.raises(ValueError, match="Redis client must be provided"):
        RateLimiterOrchestrator(
            rate_limiter_type=RateLimiterType.REDIS,
            algorithm_type=AlgorithmType.FIXED_WINDOW,
            max_requests=5,
            time_window=60,
            redis_client=None,
        )


# --- boundary: max_requests = 1 ------------------------------------------


async def test_max_requests_one_allows_exactly_one():
    limiter = RateLimiterOrchestrator(
        rate_limiter_type=RateLimiterType.IN_MEMORY,
        algorithm_type=AlgorithmType.FIXED_WINDOW,
        max_requests=1,
        time_window=60,
    )

    first = await limiter.get_response("c1")
    second = await limiter.get_response("c1")

    assert first.allowed is True
    assert first.remaining_requests == 0
    assert second.allowed is False


# --- backend failure: algorithms fail closed -----------------------------


class _BrokenRedis:
    """Stand-in Redis whose Lua script invocation always raises."""

    def register_script(self, script):
        async def _run(keys, args):
            raise ConnectionError("redis is down")

        return _run

    async def delete(self, *keys):
        raise ConnectionError("redis is down")


async def test_redis_backend_error_denies_request():
    limiter = RateLimiterOrchestrator(
        rate_limiter_type=RateLimiterType.REDIS,
        algorithm_type=AlgorithmType.FIXED_WINDOW,
        max_requests=5,
        time_window=60,
        redis_client=_BrokenRedis(),
    )

    result = await limiter.get_response("c1")

    # The algorithm swallows the error and denies (fail closed at this layer);
    # the middleware's fail_open flag governs what the HTTP caller sees.
    assert result.allowed is False
    assert result.remaining_requests == 0
