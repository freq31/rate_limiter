# rate-limiter

[![CI](https://github.com/freq31/rate_limiter/actions/workflows/python-package.yml/badge.svg)](https://github.com/freq31/rate_limiter/actions/workflows/python-package.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A pluggable, async-native rate-limiting library for Python. Supports **token bucket**, **fixed window**, and **sliding window log** algorithms across **in-memory** and **Redis** backends, with a drop-in ASGI middleware for FastAPI/Starlette.

## Features

- **3 algorithms** — fixed window, sliding window log, token bucket — selectable at construction time
- **2 backends** — in-memory (single-process, ~70k ops/s) and Redis (distributed, ~27k ops/s via atomic Lua scripts)
- **ASGI middleware** — drop into any FastAPI/Starlette app with `X-RateLimit-*` headers, `429` responses, and `Retry-After`
- **Async-native** — built on `asyncio` and `redis-py` async; no blocking calls
- **Bring-your-own Redis** — the caller owns the `redis.asyncio.Redis` instance and its lifecycle
- **Configurable failure policy** — fail-open (favour availability) or fail-closed (favour safety)
- **Fully typed** — Pydantic models, mypy-clean

## Algorithm trade-offs

| Algorithm | Accuracy | Redis memory | Redis ops | Best for |
|---|---|---|---|---|
| **Fixed window** | Can allow 2x burst at window boundaries | O(1) — 64 B/key | `INCR` + `EXPIRE` | Simple rate caps where boundary bursts are acceptable |
| **Sliding window log** | Exact — no boundary bursts | O(N) — grows with `max_requests` | `ZADD` + `ZREMRANGEBYSCORE` + `ZCARD` | Strict per-client fairness |
| **Token bucket** | Smooth — allows controlled bursts up to bucket capacity | O(1) — 141 B/key | `HGET` + `HSET` + `TIME` | APIs that want to allow short bursts while enforcing an average rate |

## Quick start

### Installation

```bash
pip install async-ratelimit
```

### In-memory rate limiting

```python
import asyncio
from rate_limiter import RateLimiterOrchestrator, AlgorithmType, RateLimiterType

limiter = RateLimiterOrchestrator(
    rate_limiter_type=RateLimiterType.IN_MEMORY,
    algorithm_type=AlgorithmType.TOKEN_BUCKET,
    max_requests=100,       # 100 requests
    time_window=60,         # per 60-second window
)

async def main():
    response = await limiter.get_response(uId="user-123")
    print(response.allowed)             # True
    print(response.remaining_requests)  # 99
    print(response.reset_time)          # seconds until the bucket refills

asyncio.run(main())
```

### Distributed rate limiting with Redis

```python
from redis.asyncio import Redis

redis_client = Redis(host="localhost", port=6379, decode_responses=True)

limiter = RateLimiterOrchestrator(
    rate_limiter_type=RateLimiterType.REDIS,
    algorithm_type=AlgorithmType.SLIDING_WINDOW,
    max_requests=1000,
    time_window=3600,
    redis_client=redis_client,      # bring your own client
)

# Use it the same way — Redis backend is transparent
response = await limiter.get_response(uId="user-123")

# Clean up when done
await redis_client.aclose()
```

### FastAPI middleware

```python
from fastapi import FastAPI
from redis.asyncio import Redis
from rate_limiter import RateLimiterOrchestrator, RateLimiterMiddleware, AlgorithmType, RateLimiterType

app = FastAPI()

redis_client = Redis(host="localhost", port=6379, decode_responses=True)
limiter = RateLimiterOrchestrator(
    rate_limiter_type=RateLimiterType.REDIS,
    algorithm_type=AlgorithmType.TOKEN_BUCKET,
    max_requests=10,
    time_window=60,
    redis_client=redis_client,
)

app.add_middleware(
    RateLimiterMiddleware,
    limiter=limiter,
    key_func=lambda r: r.headers.get("X-API-Key") or r.client.host,
    exclude_routes=["/health", "/docs"],
    fail_open=True,     # let requests through if the limiter errors
)

@app.get("/ping")
async def ping():
    return {"message": "pong"}
```

Every response includes standard rate-limit headers:

```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 7
X-RateLimit-Reset: 45
```

When the limit is exceeded, the middleware returns `429 Too Many Requests` with a `Retry-After` header — the downstream handler is never invoked.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     RateLimiterOrchestrator                      │
│  (public API — validates config, delegates to backend)           │
├──────────────┬───────────────────────────────────────────────────┤
│              │                                                   │
│  ┌───────────▼──────────┐       ┌───────────────────────────┐   │
│  │  InMemoryRateLimiter │       │    RedisRateLimiter       │   │
│  │  (asyncio.Lock)      │       │    (BYO redis client)     │   │
│  └───────────┬──────────┘       └───────────┬───────────────┘   │
│              │                              │                    │
│              ▼                              ▼                    │
│     AlgorithmFactory.create()       AlgorithmFactory.create()    │
│              │                              │                    │
│   ┌──────────┼──────────┐       ┌───────────┼──────────┐        │
│   │          │          │       │           │          │         │
│   ▼          ▼          ▼       ▼           ▼          ▼         │
│ FixedW   SlidingW   TokenB   FixedW    SlidingW    TokenB       │
│ InMem    InMem      InMem    InRedis   InRedis     InRedis      │
│ (dict)   (dict)     (dict)   (Lua)     (Lua)       (Lua)        │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                    RateLimiterMiddleware                          │
│  (ASGI — key_func, exclude_routes, fail_open/closed)             │
│  Wraps RateLimiterOrchestrator, adds X-RateLimit-* headers       │
└──────────────────────────────────────────────────────────────────┘
```

**Design decisions:**

- **Strategy + Factory pattern** — algorithms are interchangeable behind a common `Algorithm` ABC. The factory dispatches on `(backend, algorithm)` to the correct implementation.
- **Bring-your-own Redis** — the library never creates or configures a Redis connection. The caller passes in a `redis.asyncio.Redis` instance and owns its lifecycle (`aclose()`). This avoids env-var coupling and lets the caller control connection pooling, TLS, sentinels, etc.
- **Atomic Lua scripts** — all Redis algorithms use `EVAL`/`EVALSHA` to run their logic server-side in a single atomic operation. No distributed locks needed.

## Redis Lua scripts

Each Redis algorithm runs as a single Lua script executed atomically by Redis:

| Algorithm | Script | Operations | Atomicity guarantee |
|---|---|---|---|
| Fixed window | `INCR` → conditional `EXPIRE` → `TTL` | Increment counter, set TTL on first request | Counter + expiry can never diverge |
| Sliding window | `ZREMRANGEBYSCORE` → `ZCARD` → `ZADD` → `EXPIRE` | Prune expired entries, count, add if under limit | No request can slip between prune and count |
| Token bucket | `TIME` → `HGET` → refill math → `HSET` → `EXPIRE` | Server-authoritative clock, lazy token refill | Refill + consume is one atomic step |

## Benchmarks

Microbenchmark results on Apple Silicon (M-series), Python 3.14.2, Redis 7 on localhost. Full methodology and commands in [BENCHMARKS.md](BENCHMARKS.md).

### Throughput (ops/s) — hot key, 1 client

| Backend | Algorithm | Conc=1 | Conc=10 | Conc=50 | Conc=100 | Conc=250 |
|---|---|---:|---:|---:|---:|---:|
| in_memory | fixed_window | 68,404 | 69,823 | 67,906 | 66,705 | 59,387 |
| in_memory | sliding_window | 57,341 | 59,153 | 60,474 | 60,604 | 58,528 |
| in_memory | token_bucket | 70,934 | 69,237 | 71,112 | 69,173 | 69,721 |
| redis | fixed_window | 8,533 | 25,317 | 29,456 | 27,889 | 27,315 |
| redis | sliding_window | 7,631 | 21,407 | 24,718 | 25,011 | 23,390 |
| redis | token_bucket | 7,721 | 23,101 | 26,864 | 27,676 | 25,393 |

### Latency at peak load (concurrency=250)

| Backend | Algorithm | p50 | p99 | p99.9 |
|---|---|---:|---:|---:|
| in_memory | fixed_window | 7.2 µs | 24.2 µs | 85.5 µs |
| in_memory | sliding_window | 8.8 µs | 9.4 µs | 14.6 µs |
| in_memory | token_bucket | 6.7 µs | 7.1 µs | 11.5 µs |
| redis | fixed_window | 6.7 ms | 25.0 ms | 58.6 ms |
| redis | sliding_window | 7.9 ms | 27.7 ms | 50.5 ms |
| redis | token_bucket | 7.2 ms | 28.1 ms | 53.7 ms |

### Redis memory per client key

| Algorithm | Memory | Data structure |
|---|---|---|
| Fixed window | **64 B** | String (counter) — O(1) |
| Token bucket | **141 B** | Hash (3 fields) — O(1) |
| Sliding window | **6.4 MB** | Sorted set (1 member/request) — O(N) |

### Key observations

- **In-memory throughput is ~8x higher than Redis** (~70k vs ~8k ops/s at concurrency=1) because Redis operations pay a network round-trip (~100 µs) even on localhost.
- **Redis throughput scales 3x with concurrency** (8k → 27k ops/s from c=1 → c=50) because asyncio coroutines overlap I/O waits. It plateaus as Redis's single-threaded command processing saturates.
- **In-memory throughput is flat across concurrency** because asyncio is single-threaded — all coroutines serialize through `asyncio.Lock`.
- **Sliding window is the most memory-expensive** at O(N) per client. With 50k max_requests, a single key uses 6.4 MB. Fixed window and token bucket use O(1) space regardless of request volume.

For the full benchmark suite, methodology, multi-client results, and chart generation, see [BENCHMARKS.md](BENCHMARKS.md).

## Testing

```bash
# Run all tests (Redis required — via local instance, testcontainers, or REDIS_HOST env)
pytest -v

# In-memory tests only (no Redis needed)
pytest -v tests/test_fixed_window.py tests/test_sliding_window.py tests/test_token_bucket.py

# With Docker Compose (spins up Redis automatically)
docker compose up --build
```

The test suite includes:

- **Behavioral tests** — allow/deny, window expiry, token refill, weight decay, reset
- **Redis integration tests** — same behavioral coverage against a live Redis with Lua scripts
- **Concurrency tests** — 50-way `asyncio.gather` across all algorithms
- **Middleware tests** — 429 responses, `X-RateLimit-*` headers, `Retry-After`, fail-open/closed
- **Edge-case tests** — zero/negative config validation

55 tests total, all passing in CI with a Redis service container.

## Development

```bash
# Clone and install dev dependencies
git clone https://github.com/freq31/rate_limiter.git
cd rate_limiter
pip install -r requirements.txt

# Lint and type-check
ruff check .
black --check rate_limiter tests
mypy rate_limiter

# Run benchmarks
python -m benchmarks.run --ops 50000 --concurrency 1,10,50,100,250

# Generate charts
python -m benchmarks.plot benchmarks/results/<csv_file>.csv
```

## Project structure

```
rate_limiter/
├── __init__.py                 # Public API re-exports
├── main.py                     # RateLimiterOrchestrator (public API) + Factory
├── app.py                      # FastAPI demo application
├── settings.py                 # Pydantic settings for the demo app
├── algorithms/
│   ├── base.py                 # Algorithm ABC + AlgorithmFactory
│   ├── fixed_window.py         # FixedWindowInMemory, FixedWindowInRedis
│   ├── sliding_window.py       # SlidingWindowInMemory, SlidingWindowInRedis
│   └── token_bucket.py         # TokenBucketInMemory, TokenBucketInRedis
├── backend/
│   ├── base.py                 # RateLimiter ABC
│   ├── memory.py               # InMemoryRateLimiter
│   ├── redis.py                # RedisRateLimiter (BYO client)
│   ├── middleware.py           # RateLimiterMiddleware (ASGI)
│   ├── request.py              # Rules, Client, AlgorithmType, RateLimiterType
│   └── response.py             # Response model
└── scripts/
    ├── fixed_window.py         # Lua: INCR + EXPIRE
    ├── sliding_window.py       # Lua: sorted set log
    └── token_bucket.py         # Lua: hash + TIME + refill math
tests/                          # 55 tests — behavioral, integration, concurrency, middleware
benchmarks/                     # Async microbenchmark harness + chart generation
```

## License

MIT
