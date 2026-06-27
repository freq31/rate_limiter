import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from redis.asyncio import Redis
from src.main import RateLimiterOrchestrator
from src.rate_limiter.request import AlgorithmType, RateLimiterType
from src.settings import get_settings
from src.rate_limiter.middleware import RateLimiterMiddleware

# Logging is configured here, at the application layer. The library only ever
# calls logging.getLogger(__name__); it must not configure the root logger.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

settings = get_settings()
redis_client: Redis = Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    decode_responses=True,
)
rate_limiter = RateLimiterOrchestrator(
    rate_limiter_type=RateLimiterType.REDIS,
    algorithm_type=AlgorithmType.TOKEN_BUCKET,
    max_requests=10,
    time_window=60,
    redis_client=redis_client,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI application."""
    # Perform startup tasks here
    yield
    # aclose() exists at runtime (redis>=5); the bundled type stubs lag behind.
    await redis_client.aclose()  # type: ignore[attr-defined]


app = FastAPI(lifespan=lifespan)


app.add_middleware(
    RateLimiterMiddleware,
    limiter=rate_limiter,
    key_func=lambda r: r.headers.get(
        "X-Client-ID", r.client.host if r.client else "unknown"
    ),
    exclude_routes=["/health", "/docs", "/openapi.json"],
    fail_open=True,
)


@app.get("/health")
async def health_check():
    """Health check endpoint to verify the service is running."""
    return {"status": "ok"}


@app.get("/ping")
async def ping():
    """Ping endpoint to verify the service is responsive."""
    return {"message": "pong"}
