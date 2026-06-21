from src.rate_limiter.redis import RedisRateLimiter
from src.rate_limiter.memory import InMemoryRateLimiter
from src.rate_limiter.base import RateLimiter
from src.rate_limiter.request import (
    AlgorithmType,
    Client,
    Rules,
    RateLimiterType,
)
from src.rate_limiter.response import Response
from redis.asyncio import Redis


class RateLimiterOrchestrator:
    def __init__(
        self,
        rate_limiter_type: RateLimiterType,
        algorithm_type: AlgorithmType,
        max_requests: float,
        time_window: float,
        redis_client: Redis,
    ):
        self.__rate_limiter_type = rate_limiter_type
        self.__algorithm_type = algorithm_type
        self.__rules = Rules(max_requests=max_requests, time_window=time_window)
        self.__rate_limiter = RateLimiterFactory.create(
            rate_limiter_type, algorithm_type, self.__rules, redis_client
        )

    async def get_response(self, uId: str) -> Response:
        client = Client(uId=uId)
        return await self.__rate_limiter.get_response(client)


class RateLimiterFactory:
    @staticmethod
    def create(
        rate_limiter_type: RateLimiterType,
        algorithm_type: AlgorithmType,
        rules: Rules,
        redis_client: Redis,
    ) -> RateLimiter:
        if rate_limiter_type == RateLimiterType.IN_MEMORY:
            return InMemoryRateLimiter(algorithm_type, rules)
        elif rate_limiter_type == RateLimiterType.REDIS:
            return RedisRateLimiter(algorithm_type, rules, redis_client)
        else:
            raise ValueError(
                f"Unsupported rate limiter type: {rate_limiter_type.value}"
            )
