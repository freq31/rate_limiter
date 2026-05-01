from src.rate_limiter.redis import RedisRateLimiter
from src.rate_limiter.memory import InMemoryRateLimiter
from src.rate_limiter.base import RateLimiter
from src.algorithms.base import AlgorithmFactory
from src.rate_limiter.request import (
    AlgorithmType,
    TimeUnit,
    Client,
    Rules,
    RateLimiterType,
)


class RateLimiterOrchestrator:
    def __init__(self, rate_limiter_type: RateLimiterType):
        self.rate_limiter = RateLimiterFactory.create(rate_limiter_type)

    async def is_request_allowed(
        self,
        uId: str,
        max_requests: float,
        time_window: float,
        time_unit: TimeUnit,
        algorithm_type: AlgorithmType,
    ) -> bool:
        client = Client(uId=uId)
        rules = Rules(
            max_requests=max_requests, time_window=time_window, time_unit=time_unit
        )
        algorithm = AlgorithmFactory.create(algorithm_type)
        return await self.rate_limiter.is_allowed(client, rules, algorithm)


class RateLimiterFactory:
    @staticmethod
    def create(rate_limiter_type: RateLimiterType) -> RateLimiter:
        if rate_limiter_type == RateLimiterType.IN_MEMORY:
            return InMemoryRateLimiter()
        elif rate_limiter_type == RateLimiterType.REDIS:
            return RedisRateLimiter()
        else:
            raise ValueError(
                f"Unsupported rate limiter type: {rate_limiter_type.value}"
            )
