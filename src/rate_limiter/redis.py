import redis.asyncio as redis
from src.rate_limiter.response import Response
from .base import RateLimiter
from src.algorithms.base import AlgorithmFactory
from src.rate_limiter.request import (
    AlgorithmType,
    RateLimiterType,
    Client,
    Rules,
)


class RedisRateLimiter(RateLimiter):
    def __init__(
        self, algorithm_type: AlgorithmType, rules: Rules, redis_client: redis.Redis
    ):
        self.__algorithm_type = algorithm_type
        self.__rules = rules
        self.__redis_client = redis_client
        self.__algorithm = AlgorithmFactory.create(
            RateLimiterType.REDIS, algorithm_type, rules, self.__redis_client
        )

    async def get_response(self, client: Client) -> Response:
        return await self.__algorithm.execute(client.uId)

    async def reset(self, client: Client):
        """Reset the request count for the given user."""
        return await self.__algorithm.reset(client.uId)
