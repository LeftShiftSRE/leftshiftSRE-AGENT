#!/usr/bin/env python3
"""Burst test matrix for Day 1 gate."""

import asyncio
import random
import statistics
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server.splunk_client import SplunkClient


async def run_burst(semaphore_size: int, concurrent: int, queries: int):
    client = SplunkClient(semaphore_size=semaphore_size, use_mock=True)
    latencies: list[float] = []
    errors = 0

    async def one_query(_i: int):
        start = time.perf_counter()
        try:
            await client.search("| inputlookup risk_score_summary | head 1")
        except Exception:
            nonlocal errors
            errors += 1
        latencies.append(time.perf_counter() - start)

    for batch in range(0, queries, concurrent):
        batch_size = min(concurrent, queries - batch)
        tasks = [one_query(batch + i) for i in range(batch_size)]
        await asyncio.gather(*tasks)

    await client.close()

    p99 = statistics.quantiles(latencies, n=100)[98] if len(latencies) >= 100 else max(latencies) if latencies else 0
    p50 = statistics.median(latencies) if latencies else 0
    rejection_rate = (errors / queries * 100) if queries > 0 else 0

    return {
        "semaphore": semaphore_size,
        "p50": p50,
        "p99": p99,
        "rejection_pct": rejection_rate,
    }


async def main():
    concurrent = 50
    queries = 200

    results = []
    for n in [2, 4, 8]:
        print(f"Testing semaphore={n}...")
        r = await run_burst(n, concurrent, queries)
        results.append(r)
        print(f"  p50={r['p50']:.3f}s p99={r['p99']:.3f}s rejection={r['rejection_pct']:.1f}%")

    print("\n## Burst Test Results")
    print("| Semaphore | p50 (s) | p99 (s) | Rejection % |")
    print("|-----------|---------|---------|-------------|")
    for r in results:
        print(f"| {r['semaphore']} | {r['p50']:.3f} | {r['p99']:.3f} | {r['rejection_pct']:.1f}% |")


if __name__ == "__main__":
    asyncio.run(main())
