from src.algorithms.base import AlgorithmFactory
from src.rate_limiter.response import Response
from .base import RateLimiter
from src.rate_limiter.request import (
    AlgorithmType,
    RateLimiterType,
    Client,
    Rules,
)


class InMemoryRateLimiter(RateLimiter):
    def __init__(self, algorithm_type: AlgorithmType, rules: Rules):
        self.__algorithm_type = algorithm_type
        self.__algorithm = AlgorithmFactory.create(
            RateLimiterType.IN_MEMORY, algorithm_type, rules
        )

    async def get_response(self, client: Client) -> Response:
        # Implement the in-memory rate limiting logic here
        # This is a placeholder implementation and should be replaced with actual logic
        return await self.__algorithm.execute(client.uId)

    async def reset(self, client: Client):
        """Reset the request count for the given user."""
        return await self.__algorithm.reset(client.uId)
