from abc import ABC, abstractmethod


from src.rate_limiter.request import AlgorithmType, RateLimiterType, Rules
from src.rate_limiter.response import Response


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
        rate_limiter_type: RateLimiterType, algorithm_type: AlgorithmType, rules: Rules
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
            if algorithm_type == AlgorithmType.FIXED_WINDOW:
                from .fixed_window import FixedWindowInRedis

                return FixedWindowInRedis(rules)
            elif algorithm_type == AlgorithmType.SLIDING_WINDOW:
                from .sliding_window import SlidingWindowInRedis

                return SlidingWindowInRedis(rules)
            elif algorithm_type == AlgorithmType.TOKEN_BUCKET:
                from .token_bucket import TokenBucketInRedis

                return TokenBucketInRedis(rules)
            else:
                raise ValueError(f"Unknown algorithm type: {algorithm_type.value}")
