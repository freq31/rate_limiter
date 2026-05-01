from abc import ABC, abstractmethod

from src.algorithms.base import Algorithm
from src.rate_limiter.request import Client, Rules


class RateLimiter(ABC):
    @abstractmethod
    async def is_allowed(
        self, client: Client, rules: Rules, algorithm: Algorithm
    ) -> bool:
        """Check if the request with the given user is allowed."""
        pass
