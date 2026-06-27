from rate_limiter.backend.redis import RedisRateLimiter
from rate_limiter.backend.memory import InMemoryRateLimiter
from rate_limiter.backend.base import RateLimiter
from rate_limiter.backend.request import (
    AlgorithmType,
    Client,
    Rules,
    RateLimiterType,
)
from rate_limiter.backend.response import Response
from redis.asyncio import Redis
import logging


class RateLimiterOrchestrator:
    def __init__(
        self,
        rate_limiter_type: RateLimiterType,
        algorithm_type: AlgorithmType,
        max_requests: int,
        time_window: int,
        redis_client: Redis | None = None,
    ):
        self.__validate_rules(time_window, max_requests)
        self.logger = logging.getLogger(__name__)
        self.__rate_limiter_type = rate_limiter_type
        self.__algorithm_type = algorithm_type
        self.__rules = Rules(max_requests=max_requests, time_window=time_window)
        self.__rate_limiter = RateLimiterFactory.create(
            rate_limiter_type, algorithm_type, self.__rules, redis_client
        )

    def __validate_rules(self, time_window: int, max_requests: int):
        if time_window <= 0:
            raise ValueError("Time window must be a positive integer.")
        if max_requests <= 0:
            raise ValueError("Max requests must be a positive integer.")

    async def get_response(self, uId: str) -> Response:
        client = Client(uId=uId)
        return await self.__rate_limiter.get_response(client)

    def get_rules(self) -> Rules:
        return self.__rules


class RateLimiterFactory:
    @staticmethod
    def create(
        rate_limiter_type: RateLimiterType,
        algorithm_type: AlgorithmType,
        rules: Rules,
        redis_client: Redis | None = None,
    ) -> RateLimiter:
        if rate_limiter_type == RateLimiterType.IN_MEMORY:
            return InMemoryRateLimiter(algorithm_type, rules)
        elif rate_limiter_type == RateLimiterType.REDIS:
            if redis_client is None:
                raise ValueError(
                    "Redis client must be provided for Redis rate limiter."
                )
            return RedisRateLimiter(algorithm_type, rules, redis_client)
        else:
            raise ValueError(
                f"Unsupported rate limiter type: {rate_limiter_type.value}"
            )
