"""
Load test script to measure Type-Ahead Search API latency and cache performance.

Usage:
    cd docs
    python load_test.py
"""

import csv
import random
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("Please install requests: pip install requests")
    sys.exit(1)

API_BASE_URL = "http://localhost:8000"
NUM_REQUESTS = 500

def get_sample_prefixes():
    """Extract a list of realistic prefixes from queries.csv."""
    data_path = Path(__file__).resolve().parent.parent / "data" / "queries.csv"
    if not data_path.exists():
        print(f"Warning: {data_path} not found. Using fallback prefixes.")
        return ["pyt", "java", "uni", "mar", "app", "mac", "mic", "goo", "lin"]

    prefixes = []
    with open(data_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i > 1000:
                break
            query = row["query"]
            # Take a random prefix length between 2 and len(query)
            if len(query) >= 2:
                length = random.randint(2, len(query))
                prefixes.append(query[:length])
                
    # If file was empty
    if not prefixes:
         return ["pyt", "java", "uni", "mar"]
    return list(set(prefixes))

def main():
    prefixes = get_sample_prefixes()
    
    print(f"Loaded {len(prefixes)} unique prefixes. Firing {NUM_REQUESTS} /suggest requests...")
    
    start_time = time.time()
    for i in range(NUM_REQUESTS):
        prefix = random.choice(prefixes)
        # Randomly choose basic or trending mode to exercise cache key variances
        mode = random.choice(["basic", "trending"])
        try:
            requests.get(f"{API_BASE_URL}/suggest", params={"q": prefix, "mode": mode}, timeout=2)
        except requests.RequestException as e:
            print(f"Request failed: {e}")
            break
            
        if (i + 1) % 100 == 0:
            print(f"  Sent {i + 1} requests...")
            
    elapsed = time.time() - start_time
    print(f"Finished sending requests in {elapsed:.2f} seconds.\n")
    
    print("Fetching performance stats...")
    try:
        resp = requests.get(f"{API_BASE_URL}/admin/perf-stats", timeout=2)
        resp.raise_for_status()
        stats = resp.json()
    except requests.RequestException as e:
        print(f"Failed to fetch stats: {e}")
        sys.exit(1)
        
    output = [
        "Load Test Performance Report",
        "=" * 40,
        f"Total Requests Fired : {NUM_REQUESTS}",
        f"Total Time           : {elapsed:.2f} seconds",
        f"Requests/sec         : {NUM_REQUESTS / elapsed:.1f}",
        "",
        "Latency Percentiles (ms):",
        f"  p50 (Median) : {stats['p50_latency_ms']:.2f} ms",
        f"  p95          : {stats['p95_latency_ms']:.2f} ms",
        f"  p99          : {stats['p99_latency_ms']:.2f} ms",
        "",
        "Cache & Storage:",
        f"  Cache Hit Rate     : {stats['cache_hit_rate_percent']:.1f}%",
        f"  Total Store Reads  : {stats['total_store_reads']}",
        f"  Total Store Writes : {stats['total_store_writes']}"
    ]
    
    report_str = "\n".join(output) + "\n"
    print(report_str)
    
    out_path = Path(__file__).resolve().parent / "perf_report.txt"
    out_path.write_text(report_str, encoding="utf-8")
    print(f"Saved report to {out_path}")

if __name__ == "__main__":
    main()
