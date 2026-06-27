import inspect
import math
from typing import List, Optional, Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.requests import Request
from src.main import RateLimiterOrchestrator


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that rate-limits incoming requests.

    Drop it into any Starlette/FastAPI app::

        app.add_middleware(
            RateLimiterMiddleware,
            limiter=my_orchestrator,
            key_func=lambda r: r.headers.get("X-API-Key") or r.client.host,
            exclude_routes=["/health"],
            fail_open=True,
        )

    On every non-excluded request it derives a client id via ``key_func``,
    consults ``limiter``, and attaches standard rate-limit headers
    (``X-RateLimit-Limit``/``-Remaining``/``-Reset``) to the response. When the
    client is over budget it short-circuits with ``429`` and a ``Retry-After``
    header, so the wrapped application is never invoked.

    Args:
        limiter: A configured ``RateLimiterOrchestrator`` (the caller owns its
            lifecycle, e.g. the Redis connection). Limits live on the limiter,
            not here.
        key_func: ``request -> str`` (sync or async) identifying the client.
            Defaults to the client IP.
        exclude_routes: Exact paths that bypass limiting entirely (no headers,
            no counting) — e.g. health checks and docs.
        fail_open: Failure policy used when the limiter itself raises
            (e.g. Redis is unreachable):

            * ``True`` (default) — **fail open**: let the request through
              un-limited, favouring availability. No rate-limit headers are
              added, since the limiter produced no result.
            * ``False`` — **fail closed**: reject with ``503`` so a degraded
              limiter can't be bypassed, favouring safety.

            Note this only governs *limiter* errors. Exceptions raised by the
            downstream application propagate normally and are never retried.
    """

    def __init__(
        self,
        app,
        *,
        limiter: RateLimiterOrchestrator,
        key_func: Optional[Callable] = None,
        exclude_routes: Optional[List[str]] = None,
        fail_open: bool = True,
    ):
        super().__init__(app)
        self._limiter = limiter
        self._key_func = key_func or (
            lambda r: r.client.host if r.client else "unknown"
        )
        self._exclude_routes = set(exclude_routes or ())
        self._fail_open = fail_open

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self._exclude_routes:
            return await call_next(request)

        client_id = self._key_func(request)
        # Support for async key_func
        if inspect.isawaitable(client_id):
            client_id = await client_id

        try:
            result = await self._limiter.get_response(client_id)
        except Exception:
            if self._fail_open:
                return await call_next(request)
            return JSONResponse(
                content={"detail": "rate limiter unavailable"}, status_code=503
            )

        limit = self._limiter.get_rules().max_requests
        headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(result.remaining_requests),
            "X-RateLimit-Reset": str(math.ceil(result.reset_time)),
        }

        if not result.allowed:
            headers["Retry-After"] = str(math.ceil(result.reset_time))
            return JSONResponse(
                content={
                    "detail": f"Rate limit exceeded. Try again in {result.reset_time} seconds."
                },
                status_code=429,
                headers=headers,
            )

        response = await call_next(request)
        response.headers.update(headers)
        return response
