import pytest
from unittest.mock import MagicMock

from src.main import RateLimiterOrchestrator, RateLimiterFactory
from src.rate_limiter.request import (
    AlgorithmType,
    TimeUnit,
    RateLimiterType,
)
from src.rate_limiter.base import RateLimiter


class TestRateLimiterFactory:
    """Test cases for RateLimiterFactory"""

    def test_create_in_memory_rate_limiter(self):
        """Test creating an in-memory rate limiter"""
        rate_limiter = RateLimiterFactory.create(RateLimiterType.IN_MEMORY)
        assert rate_limiter is not None
        assert isinstance(rate_limiter, RateLimiter)

    def test_create_redis_rate_limiter(self):
        """Test creating a Redis rate limiter"""
        rate_limiter = RateLimiterFactory.create(RateLimiterType.REDIS)
        assert rate_limiter is not None
        assert isinstance(rate_limiter, RateLimiter)

    def test_create_unsupported_rate_limiter(self):
        """Test creating an unsupported rate limiter type raises error"""
        with pytest.raises(ValueError, match="Unsupported rate limiter type"):
            # Create a mock unsupported type
            unsupported_type = MagicMock()
            unsupported_type.value = "unsupported"
            RateLimiterFactory.create(unsupported_type)


class TestRateLimiterOrchestrator:
    """Test cases for RateLimiterOrchestrator"""

    @pytest.fixture
    def orchestrator(self):
        """Create an orchestrator instance with in-memory rate limiter"""
        return RateLimiterOrchestrator(RateLimiterType.IN_MEMORY)

    @pytest.mark.asyncio
    async def test_is_request_allowed_with_valid_inputs(self, orchestrator):
        """Test is_request_allowed with valid inputs"""
        result = await orchestrator.is_request_allowed(
            uId="user123",
            max_requests=10,
            time_window=60,
            time_unit=TimeUnit.SECONDS,
            algorithm_type=AlgorithmType.FIXED_WINDOW,
        )
        assert isinstance(result, bool)

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
            result = await orchestrator.is_request_allowed(
                uId="user123",
                max_requests=10,
                time_window=60,
                time_unit=TimeUnit.SECONDS,
                algorithm_type=algo,
            )
            assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_is_request_allowed_with_different_time_units(self, orchestrator):
        """Test is_request_allowed with different time units"""
        time_units = [TimeUnit.SECONDS, TimeUnit.MINUTES, TimeUnit.HOURS]

        for time_unit in time_units:
            result = await orchestrator.is_request_allowed(
                uId="user123",
                max_requests=10,
                time_window=1,
                time_unit=time_unit,
                algorithm_type=AlgorithmType.FIXED_WINDOW,
            )
            assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_is_request_allowed_multiple_users(self, orchestrator):
        """Test is_request_allowed with multiple different users"""
        users = ["user1", "user2", "user3"]

        for user_id in users:
            result = await orchestrator.is_request_allowed(
                uId=user_id,
                max_requests=5,
                time_window=60,
                time_unit=TimeUnit.SECONDS,
                algorithm_type=AlgorithmType.FIXED_WINDOW,
            )
            assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_is_request_allowed_with_zero_max_requests(self, orchestrator):
        """Test is_request_allowed with zero max requests"""
        result = await orchestrator.is_request_allowed(
            uId="user123",
            max_requests=0,
            time_window=60,
            time_unit=TimeUnit.SECONDS,
            algorithm_type=AlgorithmType.FIXED_WINDOW,
        )
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_is_request_allowed_with_high_max_requests(self, orchestrator):
        """Test is_request_allowed with high max requests"""
        result = await orchestrator.is_request_allowed(
            uId="user123",
            max_requests=1000000,
            time_window=3600,
            time_unit=TimeUnit.SECONDS,
            algorithm_type=AlgorithmType.FIXED_WINDOW,
        )
        assert isinstance(result, bool)

    def test_orchestrator_initialization_with_in_memory(self):
        """Test orchestrator initialization with in-memory rate limiter"""
        orchestrator = RateLimiterOrchestrator(RateLimiterType.IN_MEMORY)
        assert orchestrator.rate_limiter is not None
        assert isinstance(orchestrator.rate_limiter, RateLimiter)

    def test_orchestrator_initialization_with_redis(self):
        """Test orchestrator initialization with Redis rate limiter"""
        orchestrator = RateLimiterOrchestrator(RateLimiterType.REDIS)
        assert orchestrator.rate_limiter is not None
        assert isinstance(orchestrator.rate_limiter, RateLimiter)
