#!/usr/bin/env python3
"""Run the rate-limiter microbenchmark matrix.

Usage examples::

    # Full matrix, in-memory only (no Redis needed)
    python -m benchmarks.run --backend in_memory

    # Redis only, single algorithm, custom concurrency levels
    python -m benchmarks.run --backend redis --algorithm token_bucket --concurrency 1,50,200

    # Everything
    python -m benchmarks.run

Results are written to ``benchmarks/results/bench_<timestamp>.csv``.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
from datetime import datetime, timezone

from redis.asyncio import Redis

from benchmarks.harness import BenchmarkResult, environment_info, run_benchmark
from src.main import RateLimiterOrchestrator
from src.rate_limiter.request import AlgorithmType, RateLimiterType

ALGORITHMS = {
    "fixed_window": AlgorithmType.FIXED_WINDOW,
    "sliding_window": AlgorithmType.SLIDING_WINDOW,
    "token_bucket": AlgorithmType.TOKEN_BUCKET,
}
BACKENDS = {
    "in_memory": RateLimiterType.IN_MEMORY,
    "redis": RateLimiterType.REDIS,
}

CSV_COLUMNS = [
    "backend",
    "algorithm",
    "concurrency",
    "num_clients",
    "total_ops",
    "wall_time_s",
    "throughput_ops",
    "p50_us",
    "p90_us",
    "p99_us",
    "p999_us",
    "min_us",
    "max_us",
    "errors",
    "memory_bytes",
]

KEY_PREFIXES = {
    "fixed_window": "rl:fixed_window:",
    "sliding_window": "rl:sliding_window:",
    "token_bucket": "rl:token_bucket:",
}


def _fmt_bytes(b: int) -> str:
    if b >= 1_048_576:
        return f"{b / 1_048_576:.1f} MB"
    if b >= 1_024:
        return f"{b / 1_024:.1f} KB"
    return f"{b} B"


def parse_int_list(s: str) -> list[int]:
    return [int(x.strip()) for x in s.split(",")]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Rate-limiter microbenchmark")
    p.add_argument(
        "--backend",
        choices=[*BACKENDS, "all"],
        default="all",
        help="Which backend(s) to benchmark (default: all)",
    )
    p.add_argument(
        "--algorithm",
        choices=[*ALGORITHMS, "all"],
        default="all",
        help="Which algorithm(s) to benchmark (default: all)",
    )
    p.add_argument(
        "--concurrency",
        type=str,
        default="1,10,50,100",
        help="Comma-separated concurrency levels (default: 1,10,50,100)",
    )
    p.add_argument(
        "--ops",
        type=int,
        default=10_000,
        help="Operations per benchmark cell (default: 10000)",
    )
    p.add_argument(
        "--warmup",
        type=int,
        default=1_000,
        help="Warmup operations, discarded (default: 1000)",
    )
    p.add_argument(
        "--clients",
        type=int,
        default=1,
        help="Distinct client keys (1 = hot-key contention, >1 = spread) (default: 1)",
    )
    p.add_argument(
        "--redis-host",
        default=os.getenv("REDIS_HOST", "localhost"),
    )
    p.add_argument(
        "--redis-port",
        type=int,
        default=int(os.getenv("REDIS_PORT", "6379")),
    )
    p.add_argument(
        "--output",
        type=str,
        default="",
        help="Output CSV path (default: auto-generated in benchmarks/results/)",
    )
    return p


async def bench_one(
    *,
    backend_name: str,
    algo_name: str,
    concurrency: int,
    ops: int,
    warmup: int,
    num_clients: int,
    redis_client: Redis | None,
) -> BenchmarkResult:
    max_requests = ops + warmup + 1000
    orch = RateLimiterOrchestrator(
        rate_limiter_type=BACKENDS[backend_name],
        algorithm_type=ALGORITHMS[algo_name],
        max_requests=max_requests,
        time_window=3600,
        redis_client=redis_client,
    )

    def make_coro(idx: int):
        client_id = f"bench-client-{idx % num_clients}"
        return orch.get_response(uId=client_id)

    return await run_benchmark(
        make_coro,
        total_ops=ops,
        concurrency=concurrency,
        warmup_ops=warmup,
        backend=backend_name,
        algorithm=algo_name,
        num_clients=num_clients,
        redis_client=redis_client,
        key_prefix=KEY_PREFIXES.get(algo_name, ""),
    )


async def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    backends = list(BACKENDS) if args.backend == "all" else [args.backend]
    algos = list(ALGORITHMS) if args.algorithm == "all" else [args.algorithm]
    concurrencies = parse_int_list(args.concurrency)

    # Set up Redis once if needed
    redis_client: Redis | None = None
    if "redis" in backends:
        redis_client = Redis(
            host=args.redis_host,
            port=args.redis_port,
            decode_responses=True,
        )
        try:
            await redis_client.ping()
        except Exception as e:
            print(
                f"Cannot connect to Redis at {args.redis_host}:{args.redis_port}: {e}"
            )
            print("Skipping Redis benchmarks.")
            backends = [b for b in backends if b != "redis"]
            await redis_client.aclose()
            redis_client = None

    if not backends:
        print("No backends available. Exiting.")
        return

    results: list[BenchmarkResult] = []
    env = environment_info()

    print(f"\n{'='*70}")
    print("  Rate-Limiter Microbenchmark")
    print(f"  Python {env['python']}  |  {env['platform']}  |  {env['cpu']}")
    print(
        f"  ops/cell: {args.ops}  |  warmup: {args.warmup}  |  clients: {args.clients}"
    )
    print(f"{'='*70}\n")

    total_cells = len(backends) * len(algos) * len(concurrencies)
    cell = 0

    for backend in backends:
        for algo in algos:
            for conc in concurrencies:
                cell += 1
                label = f"[{cell}/{total_cells}] {backend}/{algo} @ concurrency={conc}"
                print(f"  {label} ...", end="", flush=True)

                client = redis_client if backend == "redis" else None
                if backend == "redis" and redis_client:
                    await redis_client.flushall()

                result = await bench_one(
                    backend_name=backend,
                    algo_name=algo,
                    concurrency=conc,
                    ops=args.ops,
                    warmup=args.warmup,
                    num_clients=args.clients,
                    redis_client=client,
                )
                results.append(result)

                mem = _fmt_bytes(result.memory_bytes)
                print(
                    f"  {result.throughput_ops:>10,.0f} ops/s"
                    f"  p50={result.p50_us:>8,.1f}µs"
                    f"  p99={result.p99_us:>8,.1f}µs"
                    f"  mem={mem:>8s}"
                    f"  err={result.errors}"
                )

    # Clean up Redis
    if redis_client:
        await redis_client.flushall()
        await redis_client.aclose()

    # Write CSV
    out_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = args.output or os.path.join(out_dir, f"bench_{ts}.csv")

    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for r in results:
            writer.writerow({col: getattr(r, col) for col in CSV_COLUMNS})

    print(f"\nResults written to {out_path}")

    # Print summary table
    print(f"\n{'='*80}")
    print(
        f"  {'Backend':<12} {'Algorithm':<17} {'Conc':>5} {'Ops/s':>12}"
        f" {'p50(µs)':>10} {'p99(µs)':>10} {'p99.9(µs)':>10} {'Memory':>10}"
    )
    print(
        f"  {'-'*12} {'-'*17} {'-'*5} {'-'*12}" f" {'-'*10} {'-'*10} {'-'*10} {'-'*10}"
    )
    for r in results:
        print(
            f"  {r.backend:<12} {r.algorithm:<17} {r.concurrency:>5}"
            f" {r.throughput_ops:>12,.0f}"
            f" {r.p50_us:>10,.1f}"
            f" {r.p99_us:>10,.1f}"
            f" {r.p999_us:>10,.1f}"
            f" {_fmt_bytes(r.memory_bytes):>10s}"
        )
    print(f"{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(main())
