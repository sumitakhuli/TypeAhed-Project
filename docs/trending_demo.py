"""
Demo: Compare 'basic' (raw count) vs 'trending' (recency-aware score) rankings.

Usage:
    cd docs
    python trending_demo.py
"""

import sys
import time
from pathlib import Path

# Add backend to path so we can import trie
sys.path.append(str(Path(__file__).resolve().parent.parent / "backend"))

from trie import Trie

def main():
    trie = Trie()
    now = time.time()
    
    # Insert queries with backdated timestamps
    # 1. A historically very popular query, but not searched recently (10 days ago)
    trie.insert("python programming", count=10000, last_searched_at=now - 10 * 24 * 3600)
    
    # 2. Another older query (7 days ago)
    trie.insert("python snake", count=8000, last_searched_at=now - 7 * 24 * 3600)
    
    # 3. A moderately popular query, searched 2 days ago
    trie.insert("python tutorial", count=5000, last_searched_at=now - 2 * 24 * 3600)
    
    # 4. A new, trending query, searched just now
    trie.insert("python 3.12 release", count=1500, last_searched_at=now)

    # Get rankings for the prefix 'python'
    basic_results = trie.search("python", top_k=10, mode="basic")
    trending_results = trie.search("python", top_k=10, mode="trending")
    
    lines = [
        "Trending vs Basic Ranking Demo",
        "=" * 65,
        "DECAY_RATE = 0.01",
        "",
        "Queries inserted:",
        "1. 'python programming'  - Count: 10000, Age: 10 days",
        "2. 'python snake'        - Count: 8000,  Age: 7 days",
        "3. 'python tutorial'     - Count: 5000,  Age: 2 days",
        "4. 'python 3.12 release' - Count: 1500,  Age: 0 days (Now)",
        "",
        f"{'BASIC MODE (Raw Count)':<30} | {'TRENDING MODE (Recency Score)':<30}",
        "-" * 65
    ]
    
    for i in range(max(len(basic_results), len(trending_results))):
        b = f"{basic_results[i]['query']} ({basic_results[i]['count']})" if i < len(basic_results) else ""
        t = f"{trending_results[i]['query']} ({trending_results[i]['count']})" if i < len(trending_results) else ""
        lines.append(f"{b:<30} | {t:<30}")
        
    output = "\n".join(lines) + "\n"
    print(output)
    
    output_path = Path(__file__).resolve().parent / "trending_demo_output.txt"
    output_path.write_text(output, encoding="utf-8")
    print(f"\nSaved output to {output_path}")

if __name__ == "__main__":
    main()
