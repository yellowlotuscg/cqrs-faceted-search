#!/usr/bin/env python3
import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from catalog.db import Database
from catalog.read_model import SQLiteFTS5ReadAdapter


def percentile(values, p):
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, round((p / 100) * len(ordered)) - 1))]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=100)
    args = parser.parse_args()
    read = SQLiteFTS5ReadAdapter(Database())
    queries = ["safety", "installation", "maintenance", "alarm", "specification"]
    timings = []
    for i in range(args.iterations):
        started = time.perf_counter()
        read.search(q=queries[i % len(queries)], page=1)
        timings.append((time.perf_counter() - started) * 1000)
    print("| corpus | queries | p50 (ms) | p95 (ms) |")
    print("|---|---:|---:|---:|")
    p50 = percentile(timings, 50)
    p95 = percentile(timings, 95)
    print(f"| local SQLite FTS5 | {args.iterations} | {p50:.2f} | {p95:.2f} |")
    print(f"mean={statistics.mean(timings):.2f}ms")


if __name__ == "__main__":
    main()
