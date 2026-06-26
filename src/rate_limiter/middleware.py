import inspect
import math
from typing import List, Optional, Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.requests import Request
from src.main import RateLimiterOrchestrator


class RateLimiterMiddleware(BaseHTTPMiddleware):
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
