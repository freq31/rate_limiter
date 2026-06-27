# Rate Limiter — 2-Day Completion Plan

Track to "portfolio-ready". Check items off as you go.

**Done so far:** 3 algorithms (fixed/sliding/token bucket) × 2 backends (in-memory, Redis
w/ atomic Lua), factory/orchestrator design, FastAPI demo service, pluggable
`RateLimiterMiddleware`, 34 passing tests.

---

## Day 1 — Make it production-shaped

### Block 1 · Config & cleanup (~1h)
- [ ] Keep limits (`max_requests`/`time_window`) as explicit constructor args — they belong
      to whoever composes the limiter, NOT to env vars. (Library consumers pass them in code.)
- [ ] Infra config (`redis_host`/`redis_port`) stays in `Settings`/env — already correct.
- [ ] (Optional) add env-overridable *demo* limit defaults in `Settings`, still passed
      explicitly into the orchestrator — convenience only, not required.
- [ ] Fix conftest regression: `redis_host` default makes the testcontainers fallback dead code
- [ ] Run `ruff`, `black`, `mypy` clean across `src/` and `tests/`

### Block 2 · Failure policy & logging (~1h)
- [ ] Replace `print(...)` in algorithms with structured `logging`
- [ ] Document & test fail-open vs fail-closed behavior (middleware + backend)
- [ ] Edge-case tests: `time_window=0`, `max_requests=1`, Redis-down path

### Block 3 · Redis-through-middleware smoke test (~1h)
- [x] One end-to-end test: middleware + real Redis limiter → 200s then 429
- [x] Confirm `X-RateLimit-*` + `Retry-After` headers correct on the Redis path

### Block 4 · CI pipeline (~1.5h)
- [x] `.github/workflows/ci.yml`: ruff + black --check + mypy + pytest
- [x] Redis service container in CI so integration tests run (not skip)
- [x] Badge in README
- [ ] Confirm green build once pushed to GitHub

---

## Day 2 — Prove it and present it

### Block 5 · Benchmarks (~2h)
- [ ] Async benchmark script: throughput + p50/p99 latency
- [ ] Compare in-memory vs Redis, across all 3 algorithms
- [ ] Record max sustained RPS; save results to `benchmarks/RESULTS.md`

### Block 6 · Packaging (~1h)
- [ ] Fix `pyproject.toml` metadata (name `rate-limiter`, real description)
- [ ] Export public API from `src/rate_limiter/__init__.py` (`RateLimiterOrchestrator`, `RateLimiterMiddleware`)
- [ ] `pip install -e .` works; importable as a library

### Block 7 · Documentation (~2h)
- [ ] README: what/why, architecture diagram, algorithm trade-offs table
- [ ] Quickstart (`docker compose up`) + middleware usage snippet
- [ ] Embed benchmark numbers; document headers + fail-open/closed semantics

### Block 8 · Final polish (~1h)
- [ ] Pre-commit hooks pass on a clean checkout
- [ ] Tag `v0.1.0`, write release notes
- [ ] Skim README as a stranger would — fix anything unclear

---

## Resume material

**One-liner (projects/skills line):**
> Built a distributed, pluggable API rate limiter in Python (FastAPI/Redis) supporting
> token-bucket, fixed- and sliding-window algorithms with atomic Redis Lua scripts.

**Bullet points (fill `__` from your Block 5 benchmarks):**
- Designed a pluggable rate-limiting library with a Starlette/ASGI middleware that drops
  into any FastAPI app via `add_middleware`, supporting configurable client-identity,
  route exclusions, and fail-open/fail-closed policies.
- Implemented 3 algorithms (token bucket, fixed & sliding window) across in-memory and
  Redis backends behind a factory/strategy design, using **atomic Lua scripts** to keep
  Redis counter updates race-free under concurrency.
- Achieved __ req/s sustained throughput with __ ms p99 latency on the Redis backend
  (benchmarked across algorithms).
- Wrote 35+ unit/integration/concurrency tests (pytest + testcontainers), with a CI
  pipeline running lint, type-checks, and a live Redis service.
- Emitted standard `X-RateLimit-*` / `Retry-After` headers and validated 429 behavior
  end-to-end through the middleware.

**Tech tags:** Python · FastAPI · Redis · asyncio · Lua · pytest · Docker · CI/CD

---

### If you only have time for the high-impact subset
CI (Block 4) + Benchmarks (Block 5) + README (Block 7). Those three are what a reviewer
actually looks at, and they unlock the strongest resume bullets.
