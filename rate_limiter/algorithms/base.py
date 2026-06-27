from abc import ABC, abstractmethod

from redis.asyncio import Redis


from rate_limiter.backend.request import AlgorithmType, RateLimiterType, Rules
from rate_limiter.backend.response import Response


class Algorithm(ABC):
    @abstractmethod
    async def execute(self, client_id: str) -> Response:
        pass

    @abstractmethod
    async def reset(self, client_id: str) -> bool:
        pass


class AlgorithmFactory:
    @staticmethod
    def create(
        rate_limiter_type: RateLimiterType,
        algorithm_type: AlgorithmType,
        rules: Rules,
        redis_client: Redis | None = None,
    ) -> Algorithm:
        if rate_limiter_type == RateLimiterType.IN_MEMORY:
            if algorithm_type == AlgorithmType.FIXED_WINDOW:
                from .fixed_window import FixedWindowInMemory

                return FixedWindowInMemory(rules)
            elif algorithm_type == AlgorithmType.SLIDING_WINDOW:
                from .sliding_window import SlidingWindowInMemory

                return SlidingWindowInMemory(rules)
            elif algorithm_type == AlgorithmType.TOKEN_BUCKET:
                from .token_bucket import TokenBucketInMemory

                return TokenBucketInMemory(rules)
            else:
                raise ValueError(f"Unknown algorithm type: {algorithm_type.value}")
        elif rate_limiter_type == RateLimiterType.REDIS:
            if redis_client is None:
                raise ValueError(
                    "Redis client must be provided for Redis rate limiter."
                )
            if algorithm_type == AlgorithmType.FIXED_WINDOW:
                from .fixed_window import FixedWindowInRedis

                return FixedWindowInRedis(rules, redis_client)
            elif algorithm_type == AlgorithmType.SLIDING_WINDOW:
                from .sliding_window import SlidingWindowInRedis

                return SlidingWindowInRedis(rules, redis_client)
            elif algorithm_type == AlgorithmType.TOKEN_BUCKET:
                from .token_bucket import TokenBucketInRedis

                return TokenBucketInRedis(rules, redis_client)
            else:
                raise ValueError(f"Unknown algorithm type: {algorithm_type.value}")
