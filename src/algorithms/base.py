from abc import ABC, abstractmethod

from src.rate_limiter.request import AlgorithmType


class Algorithm(ABC):
    @abstractmethod
    async def execute(self):
        pass


class AlgorithmFactory:
    @staticmethod
    def create(algorithm_type: AlgorithmType) -> Algorithm:
        if algorithm_type == AlgorithmType.FIXED_WINDOW:
            from .fixed_window import FixedWindow

            return FixedWindow()
        elif algorithm_type == AlgorithmType.SLIDING_WINDOW:
            from .sliding_window import SlidingWindow

            return SlidingWindow()
        elif algorithm_type == AlgorithmType.TOKEN_BUCKET:
            from .token_bucket import TokenBucket

            return TokenBucket()
        else:
            raise ValueError(f"Unknown algorithm type: {algorithm_type.value}")
