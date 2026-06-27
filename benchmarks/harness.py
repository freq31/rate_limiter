"""Async microbenchmark harness for the rate-limiter library.

Fires N operations at a given concurrency level, records every latency
sample via time.perf_counter, and computes percentiles + throughput.
Also measures memory footprint via tracemalloc (in-memory) or
Redis MEMORY USAGE (Redis backend).
"""

from __future__ import annotations

import asyncio
import platform
import statistics
import sys
import time
import tracemalloc
from dataclasses import dataclass, field


@dataclass(frozen=True)
class BenchmarkResult:
    backend: str
    algorithm: str
    concurrency: int
    num_clients: int
    total_ops: int
    wall_time_s: float
    throughput_ops: float
    samples_us: list[float] = field(repr=False)
    p50_us: float = 0.0
    p90_us: float = 0.0
    p99_us: float = 0.0
    p999_us: float = 0.0
    min_us: float = 0.0
    max_us: float = 0.0
    errors: int = 0
    memory_bytes: int = 0

    @staticmethod
    def from_samples(
        *,
        backend: str,
        algorithm: str,
        concurrency: int,
        num_clients: int,
        total_ops: int,
        wall_time_s: float,
        samples_us: list[float],
        errors: int,
        memory_bytes: int = 0,
    ) -> BenchmarkResult:
        sorted_s = sorted(samples_us)
        q = statistics.quantiles(sorted_s, n=1000) if len(sorted_s) >= 2 else sorted_s
        return BenchmarkResult(
            backend=backend,
            algorithm=algorithm,
            concurrency=concurrency,
            num_clients=num_clients,
            total_ops=total_ops,
            wall_time_s=wall_time_s,
            throughput_ops=total_ops / wall_time_s if wall_time_s > 0 else 0,
            samples_us=sorted_s,
            p50_us=q[499] if len(q) >= 500 else sorted_s[len(sorted_s) // 2],
            p90_us=q[899] if len(q) >= 900 else sorted_s[int(len(sorted_s) * 0.9)],
            p99_us=q[989] if len(q) >= 990 else sorted_s[int(len(sorted_s) * 0.99)],
            p999_us=q[998]
            if len(q) >= 999
            else sorted_s[min(int(len(sorted_s) * 0.999), len(sorted_s) - 1)],
            min_us=sorted_s[0] if sorted_s else 0,
            max_us=sorted_s[-1] if sorted_s else 0,
            errors=errors,
            memory_bytes=memory_bytes,
        )


def measure_tracemalloc() -> tuple:
    """Start tracemalloc and return a snapshot-taker.

    Returns (start, stop) callables.  Call start() before the workload,
    stop() after — stop() returns peak memory in bytes allocated by
    Python during the interval.
    """

    def start() -> None:
        tracemalloc.stop() if tracemalloc.is_tracing() else None
        tracemalloc.start()

    def stop() -> int:
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return peak

    return start, stop


async def measure_redis_memory(redis_client, key_prefix: str) -> int:
    """Sum MEMORY USAGE across all keys matching *key_prefix**.

    Returns total bytes consumed by the rate-limiter keys in Redis.
    Falls back to 0 on error.
    """
    total = 0
    try:
        async for key in redis_client.scan_iter(match=f"{key_prefix}*"):
            usage = await redis_client.memory_usage(key)
            if usage:
                total += usage
    except Exception:
        pass
    return total


def environment_info() -> dict[str, str]:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "cpu": platform.processor() or platform.machine(),
    }


async def run_benchmark(
    coro_factory,
    *,
    total_ops: int,
    concurrency: int,
    warmup_ops: int = 0,
    backend: str = "",
    algorithm: str = "",
    num_clients: int = 1,
    redis_client=None,
    key_prefix: str = "",
) -> BenchmarkResult:
    """Run *total_ops* invocations of *coro_factory(i)* at the given concurrency.

    *coro_factory(i)* receives the operation index and must return an
    awaitable that performs the work to be measured.  For the rate limiter
    this is ``orchestrator.get_response(uId=client_id)``.

    Memory measurement:
      - in-memory backend: tracemalloc peak during the timed run.
      - redis backend: sum of ``MEMORY USAGE`` across all limiter keys
        after the run completes.
    """
    sem = asyncio.Semaphore(concurrency)
    samples: list[float] = []
    errors = 0

    async def _worker(idx: int) -> None:
        nonlocal errors
        async with sem:
            t0 = time.perf_counter()
            try:
                await coro_factory(idx)
            except Exception:
                errors += 1
            elapsed = (time.perf_counter() - t0) * 1_000_000  # → microseconds
            samples.append(elapsed)

    # --- warmup (discard) ---
    if warmup_ops > 0:
        warmup_tasks = [asyncio.create_task(_worker(i)) for i in range(warmup_ops)]
        await asyncio.gather(*warmup_tasks)
        samples.clear()
        errors = 0

    # --- memory tracking (in-memory backend) ---
    mem_start, mem_stop = measure_tracemalloc()
    is_in_memory = backend == "in_memory"
    if is_in_memory:
        mem_start()

    # --- timed run ---
    wall_t0 = time.perf_counter()
    tasks = [asyncio.create_task(_worker(i)) for i in range(total_ops)]
    await asyncio.gather(*tasks)
    wall_time = time.perf_counter() - wall_t0

    # --- collect memory ---
    memory_bytes = 0
    if is_in_memory:
        memory_bytes = mem_stop()
    elif redis_client and key_prefix:
        memory_bytes = await measure_redis_memory(redis_client, key_prefix)

    return BenchmarkResult.from_samples(
        backend=backend,
        algorithm=algorithm,
        concurrency=concurrency,
        num_clients=num_clients,
        total_ops=total_ops,
        wall_time_s=wall_time,
        samples_us=samples,
        errors=errors,
        memory_bytes=memory_bytes,
    )
