from rate_limiter.main import RateLimiterOrchestrator
from rate_limiter.backend.request import (
    AlgorithmType,
    RateLimiterType,
    Rules,
    Client,
)
from rate_limiter.backend.response import Response


def __getattr__(name: str):
    if name == "RateLimiterMiddleware":
        from rate_limiter.backend.middleware import RateLimiterMiddleware

        return RateLimiterMiddleware
    raise AttributeError(f"module 'rate_limiter' has no attribute {name!r}")


__all__ = [
    "RateLimiterOrchestrator",
    "RateLimiterMiddleware",
    "AlgorithmType",
    "RateLimiterType",
    "Rules",
    "Client",
    "Response",
]
