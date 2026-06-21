import asyncio

import pytest

from src.main import RateLimiterOrchestrator
from src.rate_limiter.request import AlgorithmType, RateLimiterType


@pytest.mark.parametrize(
    "algorithm_type",
    [
        AlgorithmType.FIXED_WINDOW,
        AlgorithmType.SLIDING_WINDOW,
        AlgorithmType.TOKEN_BUCKET,
    ],
)
@pytest.mark.asyncio
async def test_concurrent_requests_allow_exactly_max_requests(algorithm_type):
    """50 requests fire concurrently for one client; the asyncio.Lock inside each
    algorithm must serialize access so exactly max_requests are allowed, proving
    there's no race condition under concurrent access."""
    max_requests = 10
    orchestrator = RateLimiterOrchestrator(
        RateLimiterType.IN_MEMORY, algorithm_type, max_requests, time_window=100
    )

    responses = await asyncio.gather(
        *(orchestrator.get_response(uId="client-a") for _ in range(50))
    )

    allowed_count = sum(1 for resp in responses if resp.allowed)
    assert allowed_count == max_requests
