from .base import RateLimiter


class InMemoryRateLimiter(RateLimiter):
    def __init__(self):
        self.client_requests = {}

    async def is_allowed(self, client, rules, algorithm) -> bool:
        # Implement the in-memory rate limiting logic here
        # This is a placeholder implementation and should be replaced with actual logic
        return True
