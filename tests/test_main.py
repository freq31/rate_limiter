import pytest
from unittest.mock import MagicMock

from src.main import RateLimiterOrchestrator, RateLimiterFactory
from src.rate_limiter.request import (
    AlgorithmType,
    RateLimiterType,
    Rules,
)
from src.rate_limiter.response import Response
from src.rate_limiter.base import RateLimiter


class TestRateLimiterFactory:
    """Test cases for RateLimiterFactory"""

    def test_create_in_memory_rate_limiter(self):
        """Test creating an in-memory rate limiter"""
        rate_limiter = RateLimiterFactory.create(
            RateLimiterType.IN_MEMORY,
            AlgorithmType.FIXED_WINDOW,
            Rules(max_requests=1, time_window=60),
        )
        assert rate_limiter is not None
        assert isinstance(rate_limiter, RateLimiter)

    def test_create_redis_rate_limiter(self):
        """Test creating a Redis rate limiter"""
        rate_limiter = RateLimiterFactory.create(
            RateLimiterType.REDIS,
            AlgorithmType.FIXED_WINDOW,
            Rules(max_requests=1, time_window=60),
        )
        assert rate_limiter is not None
        assert isinstance(rate_limiter, RateLimiter)

    def test_create_unsupported_rate_limiter(self):
        """Test creating an unsupported rate limiter type raises error"""
        with pytest.raises(ValueError, match="Unsupported rate limiter type"):
            # Create a mock unsupported type
            unsupported_type = MagicMock()
            unsupported_type.value = "unsupported"
            RateLimiterFactory.create(
                unsupported_type,
                AlgorithmType.FIXED_WINDOW,
                Rules(max_requests=1, time_window=60),
            )


class TestRateLimiterOrchestrator:
    """Test cases for RateLimiterOrchestrator"""

    @pytest.fixture
    def orchestrator(self):
        """Create an orchestrator instance with in-memory rate limiter"""
        # construct with a default algorithm and rules (original API)
        return RateLimiterOrchestrator(
            RateLimiterType.IN_MEMORY, AlgorithmType.FIXED_WINDOW, 10, 60
        )

    @pytest.mark.asyncio
    async def test_is_request_allowed_with_valid_inputs(self, orchestrator):
        """Test is_request_allowed with valid inputs"""
        resp = await orchestrator.get_response(uId="user123")
        assert isinstance(resp, Response)

    @pytest.mark.asyncio
    async def test_is_request_allowed_with_different_algorithm_types(
        self, orchestrator
    ):
        """Test is_request_allowed with different algorithm types"""
        algorithms = [
            AlgorithmType.FIXED_WINDOW,
            AlgorithmType.SLIDING_WINDOW,
            AlgorithmType.TOKEN_BUCKET,
        ]

        for algo in algorithms:
            orch = RateLimiterOrchestrator(RateLimiterType.IN_MEMORY, algo, 10, 60)
            resp = await orch.get_response(uId="user123")
            assert isinstance(resp, Response)

    @pytest.mark.asyncio
    async def test_is_request_allowed_with_different_time_units(self, orchestrator):
        """Test is_request_allowed with different time units"""
        # use equivalent seconds for 1 unit each: seconds, minutes, hours
        time_windows = [1, 60, 3600]

        for tw in time_windows:
            orch = RateLimiterOrchestrator(
                RateLimiterType.IN_MEMORY, AlgorithmType.FIXED_WINDOW, 10, tw
            )
            resp = await orch.get_response(uId="user123")
            assert isinstance(resp, Response)

    @pytest.mark.asyncio
    async def test_is_request_allowed_multiple_users(self, orchestrator):
        """Test is_request_allowed with multiple different users"""
        users = ["user1", "user2", "user3"]

        for user_id in users:
            orch = RateLimiterOrchestrator(
                RateLimiterType.IN_MEMORY, AlgorithmType.FIXED_WINDOW, 5, 60
            )
            resp = await orch.get_response(uId=user_id)
            assert isinstance(resp, Response)

    @pytest.mark.asyncio
    async def test_is_request_allowed_with_zero_max_requests(self, orchestrator):
        """Test is_request_allowed with zero max requests"""
        orch = RateLimiterOrchestrator(
            RateLimiterType.IN_MEMORY, AlgorithmType.FIXED_WINDOW, 0, 60
        )
        resp = await orch.get_response(uId="user123")
        assert isinstance(resp, Response)

    @pytest.mark.asyncio
    async def test_is_request_allowed_with_high_max_requests(self, orchestrator):
        """Test is_request_allowed with high max requests"""
        orch = RateLimiterOrchestrator(
            RateLimiterType.IN_MEMORY, AlgorithmType.FIXED_WINDOW, 1000000, 3600
        )
        resp = await orch.get_response(uId="user123")
        assert isinstance(resp, Response)

    def test_orchestrator_initialization_with_in_memory(self):
        """Test orchestrator initialization with in-memory rate limiter"""
        orchestrator = RateLimiterOrchestrator(
            RateLimiterType.IN_MEMORY, AlgorithmType.FIXED_WINDOW, 10, 60
        )
        assert isinstance(orchestrator, RateLimiterOrchestrator)

    def test_orchestrator_initialization_with_redis(self):
        """Test orchestrator initialization with Redis rate limiter"""
        orchestrator = RateLimiterOrchestrator(
            RateLimiterType.REDIS, AlgorithmType.FIXED_WINDOW, 10, 60
        )
        assert isinstance(orchestrator, RateLimiterOrchestrator)
