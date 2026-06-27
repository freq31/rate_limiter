# Benchmarks

Microbenchmark suite for the rate-limiter library. Measures **throughput**, **latency percentiles** (p50/p90/p99/p99.9), and **memory footprint** across all backends and algorithms.

## Prerequisites

```bash
pip install matplotlib numpy
```

A running Redis instance is needed for Redis benchmarks. If Redis is unavailable, those cells are skipped automatically.

## Commands

### Run benchmarks

```bash
python -m benchmarks.run [OPTIONS]
```

Executes the benchmark matrix and writes results to a timestamped CSV in `benchmarks/results/`.

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--backend` | `all` | `in_memory`, `redis`, or `all` |
| `--algorithm` | `all` | `fixed_window`, `sliding_window`, `token_bucket`, or `all` |
| `--concurrency` | `1,10,50,100` | Comma-separated concurrency levels (number of async coroutines) |
| `--ops` | `10000` | Operations per benchmark cell |
| `--warmup` | `1000` | Warmup operations (discarded, primes caches and connection pools) |
| `--clients` | `1` | Distinct client keys. `1` = hot-key contention (all requests hit the same key). `>1` = spread across N keys |
| `--redis-host` | `localhost` | Redis host (also reads `REDIS_HOST` env var) |
| `--redis-port` | `6379` | Redis port (also reads `REDIS_PORT` env var) |
| `--output` | auto | Output CSV path. Defaults to `benchmarks/results/bench_<timestamp>.csv` |

**Examples:**

```bash
# Full matrix — all backends, all algorithms, default concurrency levels
python -m benchmarks.run

# In-memory only (no Redis needed)
python -m benchmarks.run --backend in_memory

# Single algorithm, custom concurrency, higher ops count
python -m benchmarks.run --backend redis --algorithm token_bucket \
    --concurrency 1,50,200 --ops 50000

# Multi-client (simulates many distinct users instead of one hot key)
python -m benchmarks.run --clients 100
```

**Output:** a summary table printed to stdout and a CSV file with columns: `backend`, `algorithm`, `concurrency`, `num_clients`, `total_ops`, `wall_time_s`, `throughput_ops`, `p50_us`, `p90_us`, `p99_us`, `p999_us`, `min_us`, `max_us`, `errors`, `memory_bytes`.

### Generate charts

```bash
python -m benchmarks.plot <csv_path>
```

Reads a benchmark CSV and produces three PNG charts alongside it:

| Chart | Filename suffix | What it shows |
|---|---|---|
| **Throughput** | `_throughput.png` | Ops/s vs concurrency — one line per (backend, algorithm) combination. Data points labeled. |
| **Latency** | `_latency.png` | p50/p90/p99 grouped bars at the highest concurrency level. Values labeled on each bar. |
| **Memory** | `_memory.png` | Memory footprint bars at the highest concurrency level. In-memory = Python `tracemalloc` peak. Redis = sum of `MEMORY USAGE` across all rate-limiter keys. |

**Example:**

```bash
python -m benchmarks.plot benchmarks/results/bench_20260627_120648.csv
```

Produces:
- `bench_20260627_120648_throughput.png`
- `bench_20260627_120648_latency.png`
- `bench_20260627_120648_memory.png`

## How it works

1. **Warmup phase** — runs `--warmup` operations to prime connection pools, let Redis cache Lua scripts via `EVALSHA`, and warm OS buffers. Results are discarded.
2. **Timed run** — fires `--ops` operations with `asyncio.Semaphore(concurrency)` controlling parallelism. Every operation is timed with `time.perf_counter` (microsecond resolution).
3. **Memory measurement** — for in-memory backends, `tracemalloc` captures peak heap allocation during the timed run. For Redis, `MEMORY USAGE` is summed across all rate-limiter keys after the run.
4. **Statistics** — percentiles computed via `statistics.quantiles` over all raw samples. Throughput = total ops / wall-clock time.
5. **Per-cell isolation** — Redis keys are flushed between benchmark cells to prevent data from one cell affecting the next.

## Results

**Environment:**
- Python 3.14.2
- macOS 26.3.1, Apple Silicon (arm64)
- Redis 7 on localhost
- 50,000 ops/cell, 5,000 warmup, concurrency levels: 1, 10, 50, 100, 250

---

### Scenario 1: Hot key (1 client)

All requests target the same client key — worst-case contention. This is the standard stress test for lock contention (in-memory) and per-key data structure cost (Redis).

#### Throughput (ops/s)

| Backend | Algorithm | Conc=1 | Conc=10 | Conc=50 | Conc=100 | Conc=250 |
|---|---|---:|---:|---:|---:|---:|
| in_memory | fixed_window | 68,404 | 69,823 | 67,906 | 66,705 | 59,387 |
| in_memory | sliding_window | 57,341 | 59,153 | 60,474 | 60,604 | 58,528 |
| in_memory | token_bucket | 70,934 | 69,237 | 71,112 | 69,173 | 69,721 |
| redis | fixed_window | 8,533 | 25,317 | 29,456 | 27,889 | 27,315 |
| redis | sliding_window | 7,631 | 21,407 | 24,718 | 25,011 | 23,390 |
| redis | token_bucket | 7,721 | 23,101 | 26,864 | 27,676 | 25,393 |

#### Latency

| Backend | Algorithm | p50 (c=1) | p99 (c=1) | p50 (c=100) | p99 (c=100) | p50 (c=250) | p99 (c=250) |
|---|---|---:|---:|---:|---:|---:|---:|
| in_memory | fixed_window | 7.0 µs | 9.1 µs | 7.1 µs | 9.3 µs | 7.2 µs | 24.2 µs |
| in_memory | sliding_window | 8.9 µs | 13.6 µs | 8.8 µs | 10.9 µs | 8.8 µs | 9.4 µs |
| in_memory | token_bucket | 6.6 µs | 7.0 µs | 6.6 µs | 7.3 µs | 6.7 µs | 7.1 µs |
| redis | fixed_window | 96.5 µs | 124.8 µs | 2.6 ms | 6.7 ms | 6.7 ms | 25.0 ms |
| redis | sliding_window | 110.8 µs | 133.5 µs | 3.1 ms | 3.8 ms | 7.9 ms | 27.7 ms |
| redis | token_bucket | 111.2 µs | 131.4 µs | 2.7 ms | 3.3 ms | 7.2 ms | 28.1 ms |

#### Redis memory (per client key)

| Algorithm | Memory | Data structure |
|---|---|---|
| Fixed window | **64 B** | String (counter) — O(1) |
| Token bucket | **~140 B** | Hash (3 fields: tokens, last_refill, refill_rate) — O(1) |
| Sliding window | **6.4 MB** | Sorted set (1 member per request) — O(N), N = max_requests |

---

### Scenario 2: Multi-client (100 clients)

Requests are distributed across 100 distinct client keys via round-robin (`client_id = idx % 100`). This simulates realistic production traffic where many users share the limiter.

#### Throughput (ops/s)

| Backend | Algorithm | Conc=1 | Conc=10 | Conc=50 | Conc=100 | Conc=250 |
|---|---|---:|---:|---:|---:|---:|
| in_memory | fixed_window | 67,828 | 69,446 | 67,383 | 68,184 | 68,041 |
| in_memory | sliding_window | 61,157 | 59,663 | 61,258 | 60,746 | 59,324 |
| in_memory | token_bucket | 69,794 | 68,136 | 69,885 | 69,103 | 69,224 |
| redis | fixed_window | 8,588 | 25,050 | 28,810 | 29,372 | 27,126 |
| redis | sliding_window | 7,582 | 21,316 | 24,768 | 24,672 | 23,269 |
| redis | token_bucket | 7,695 | 23,477 | 27,045 | 27,244 | 25,293 |

#### Redis memory (100 client keys)

| Algorithm | Memory (100 clients) | Per-key equivalent | Growth pattern |
|---|---|---|---|
| Fixed window | **6.4 KB** | 64 B | Linear in client count, O(1) per key |
| Token bucket | **14.3 KB** | 143 B | Linear in client count, O(1) per key |
| Sliding window | **7.2 MB** | ~72 KB | Linear in client count × O(N) per key |

---

### Scenario comparison: hot key vs multi-client

#### In-memory: no significant difference

In-memory throughput is virtually identical across both scenarios (~60k–70k ops/s). This is expected — a single `asyncio.Lock` per algorithm instance serializes all requests regardless of how many distinct clients are involved. The lock is the bottleneck, not the data structure.

#### Redis: throughput is similar, memory differs

Redis throughput is also similar between scenarios because the bottleneck is the network round-trip and Redis's single-threaded command processing — not per-key data structure cost.

The memory story is different:
- **Fixed window and token bucket** — O(1) per key, so 100 clients = 100x the single-key cost. Still tiny (6.4 KB and 14.3 KB).
- **Sliding window** — O(N) per key where N is the number of requests tracked in each sorted set. With 100 clients, the total requests are distributed across 100 smaller sorted sets instead of one large one. Each sorted set has ~1/100th the members, but there are 100 of them, plus per-key overhead. Total is slightly higher (7.2 MB vs 6.4 MB) due to Redis sorted set bookkeeping per key.

---

## Interpretation guide

### Why is in-memory throughput flat across concurrency?

asyncio is single-threaded. All coroutines serialize through `asyncio.Lock` — only one executes the rate-limit logic at a time. Adding more coroutines doesn't create parallelism, just a longer queue behind the lock.

The slight increase from c=1 to c=10 (~3-5%) is a **pipeline fill effect**: at c=1, there are scheduling gaps between operations (event loop ticks between semaphore release and next task wake-up). At c=10+, the lock's internal wait queue always has a task ready, eliminating idle gaps.

### Why does Redis throughput scale with concurrency, then plateau?

Redis operations are I/O-bound (~100 µs network round-trip). At c=1, the CPU is idle during each round-trip. At c=10, coroutines overlap their I/O waits — while one waits for a response, others are sending. Throughput triples because idle time is eliminated.

It plateaus around c=50 because Redis is single-threaded — once its command queue is always full, more in-flight requests just increase queueing delay without improving throughput.

### Why does Redis latency degrade at high concurrency?

At c=1, each request finds Redis idle: p50 ≈ 100 µs. At c=250, requests queue behind ~250 others in Redis's command pipeline: p50 ≈ 7 ms. The per-request processing time hasn't changed — the request just spends more time **waiting in line**.

### Why do in-memory numbers show ~45 MB while Redis shows bytes/KB?

They measure different things. In-memory `tracemalloc` captures the **entire Python process peak**: interpreter, asyncio task objects (50,000 `Task` allocations), the benchmark harness's sample list, Pydantic model schemas, etc. The rate limiter's own data structures are a negligible fraction.

Redis `MEMORY USAGE` measures **only the rate-limiter keys inside Redis** — purely the data structure cost, not the Python process or connection overhead.

### Why is sliding window so memory-expensive in Redis?

Sliding window log stores **every individual request timestamp** as a sorted set member (`ZADD score=timestamp`). With `max_requests=50,000`, a single key contains up to 50,000 sorted set entries. Each entry is ~8 bytes (timestamp) plus ~40 bytes of skiplist pointers and bookkeeping. That's how one key reaches megabytes.

Fixed window stores one counter (64 B). Token bucket stores one hash with 3 fields (141 B). Neither grows with request volume.
