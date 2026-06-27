#!/usr/bin/env python3
"""Generate benchmark charts from CSV results.

Usage::

    python -m benchmarks.plot benchmarks/results/bench_20260627_120000.csv

Produces two PNGs next to the CSV:
  - *_throughput.png  — throughput vs concurrency, one line per (backend, algo)
  - *_latency.png     — p50/p90/p99 grouped bars per (backend, algo) at highest concurrency
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict
from dataclasses import dataclass

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
except ImportError:
    print(
        "matplotlib and numpy are required for plotting: pip install matplotlib numpy"
    )
    sys.exit(1)


@dataclass
class Row:
    backend: str
    algorithm: str
    concurrency: int
    throughput_ops: float
    p50_us: float
    p90_us: float
    p99_us: float
    p999_us: float


def load_csv(path: str) -> list[Row]:
    rows: list[Row] = []
    with open(path) as f:
        for r in csv.DictReader(f):
            rows.append(
                Row(
                    backend=r["backend"],
                    algorithm=r["algorithm"],
                    concurrency=int(r["concurrency"]),
                    throughput_ops=float(r["throughput_ops"]),
                    p50_us=float(r["p50_us"]),
                    p90_us=float(r["p90_us"]),
                    p99_us=float(r["p99_us"]),
                    p999_us=float(r["p999_us"]),
                )
            )
    return rows


def _fmt_ops(v: float) -> str:
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v / 1_000:.0f}k"
    return f"{v:.0f}"


def _fmt_us(v: float) -> str:
    if v >= 1_000:
        return f"{v / 1_000:.1f}ms"
    return f"{v:.0f}µs"


def plot_throughput(rows: list[Row], out_path: str) -> None:
    series: dict[str, dict[int, float]] = defaultdict(dict)
    for r in rows:
        key = f"{r.backend} / {r.algorithm}"
        series[key][r.concurrency] = r.throughput_ops

    fig, ax = plt.subplots(figsize=(12, 7))
    for label, conc_map in sorted(series.items()):
        xs = sorted(conc_map)
        ys = [conc_map[x] for x in xs]
        (line,) = ax.plot(xs, ys, marker="o", linewidth=2, markersize=7, label=label)
        color = line.get_color()

        for xv, yv in zip(xs, ys):
            ax.annotate(
                _fmt_ops(yv),
                (xv, yv),
                textcoords="offset points",
                xytext=(0, 10),
                ha="center",
                fontsize=7,
                fontweight="bold",
                color=color,
            )

    ax.set_xlabel("Concurrency (coroutines)", fontsize=11)
    ax.set_ylabel("Throughput (ops/s)", fontsize=11)
    ax.set_title(
        "Rate-Limiter Throughput vs Concurrency", fontsize=13, fontweight="bold"
    )
    ax.legend(fontsize=8, loc="center right")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Throughput chart → {out_path}")


def plot_latency(rows: list[Row], out_path: str) -> None:
    max_conc = max(r.concurrency for r in rows)
    peak_rows = [r for r in rows if r.concurrency == max_conc]

    if not peak_rows:
        print("  No rows at peak concurrency — skipping latency chart.")
        return

    labels = [f"{r.backend}\n{r.algorithm}" for r in peak_rows]
    p50s = [r.p50_us for r in peak_rows]
    p90s = [r.p90_us for r in peak_rows]
    p99s = [r.p99_us for r in peak_rows]

    x = np.arange(len(labels))
    width = 0.25

    fig, ax = plt.subplots(figsize=(12, 7))
    bars_p50 = ax.bar(x - width, p50s, width, label="p50", zorder=3)
    bars_p90 = ax.bar(x, p90s, width, label="p90", zorder=3)
    bars_p99 = ax.bar(x + width, p99s, width, label="p99", zorder=3)

    for bars in (bars_p50, bars_p90, bars_p99):
        for bar in bars:
            height = bar.get_height()
            if height < 1:
                continue
            ax.annotate(
                _fmt_us(height),
                (bar.get_x() + bar.get_width() / 2, height),
                textcoords="offset points",
                xytext=(0, 4),
                ha="center",
                fontsize=7,
                fontweight="bold",
            )

    ax.set_xlabel("Backend / Algorithm", fontsize=11)
    ax.set_ylabel("Latency (µs)", fontsize=11)
    ax.set_title(
        f"Latency Percentiles @ Concurrency={max_conc}",
        fontsize=13,
        fontweight="bold",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, axis="y", zorder=0)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Latency chart  → {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot benchmark results")
    parser.add_argument("csv_path", help="Path to the benchmark CSV file")
    args = parser.parse_args()

    rows = load_csv(args.csv_path)
    base = os.path.splitext(args.csv_path)[0]

    plot_throughput(rows, f"{base}_throughput.png")
    plot_latency(rows, f"{base}_latency.png")


if __name__ == "__main__":
    main()
