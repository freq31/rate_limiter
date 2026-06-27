from abc import ABC, abstractmethod


from rate_limiter.backend.request import Client
from rate_limiter.backend.response import Response


class RateLimiter(ABC):
    @abstractmethod
    async def get_response(self, client: Client) -> Response:
        """Check if the request with the given user is allowed."""
        pass

    @abstractmethod
    async def reset(self, client: Client):
        """Reset the request count for the given user."""
        pass
