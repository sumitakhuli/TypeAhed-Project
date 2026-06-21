"""
Demo: consistent hash ring key redistribution when a 5th node is added.

Shows that only ~1/5 of keys change owner (not all of them), which is the
key property of consistent hashing.

Usage:
    cd backend
    python demo_consistent_hashing.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from hash_ring import ConsistentHashRing

SAMPLE_SIZE = 1000
INITIAL_NODES = ["node-0", "node-1", "node-2", "node-3"]
NEW_NODE = "node-4"
OUTPUT_FILE = Path(__file__).resolve().parent.parent / "docs" / "consistent_hashing_demo.txt"


def main() -> None:
    # Build the initial ring
    ring = ConsistentHashRing(INITIAL_NODES)

    # Generate sample keys and record their owners
    keys = [f"prefix-{i}" for i in range(SAMPLE_SIZE)]
    before = {k: ring.get_node(k) for k in keys}

    # Count distribution before
    dist_before: dict[str, int] = {}
    for node in before.values():
        dist_before[node] = dist_before.get(node, 0) + 1

    # Add the 5th node
    ring.add_node(NEW_NODE)
    after = {k: ring.get_node(k) for k in keys}

    # Count distribution after
    dist_after: dict[str, int] = {}
    for node in after.values():
        dist_after[node] = dist_after.get(node, 0) + 1

    # Calculate how many keys changed owner
    changed = sum(1 for k in keys if before[k] != after[k])
    fraction = changed / SAMPLE_SIZE

    # Format output
    lines = [
        "Consistent Hashing Demo",
        "=" * 50,
        "",
        f"Sample size: {SAMPLE_SIZE} keys",
        f"Initial nodes: {INITIAL_NODES}",
        f"Added node: {NEW_NODE}",
        "",
        "Distribution BEFORE adding node-4:",
    ]
    for nid in sorted(dist_before):
        lines.append(f"  {nid}: {dist_before[nid]} keys ({dist_before[nid]/SAMPLE_SIZE:.1%})")

    lines.append("")
    lines.append("Distribution AFTER adding node-4:")
    for nid in sorted(dist_after):
        lines.append(f"  {nid}: {dist_after[nid]} keys ({dist_after[nid]/SAMPLE_SIZE:.1%})")

    lines.append("")
    lines.append(f"Keys that changed owner: {changed}/{SAMPLE_SIZE} ({fraction:.1%})")
    lines.append(f"Expected (ideal): ~{SAMPLE_SIZE // 5}/{SAMPLE_SIZE} (~{1/5:.1%})")
    lines.append("")
    if fraction < 0.35:
        lines.append("PASS: Only a fraction of keys were remapped -- consistent hashing works!")
    else:
        lines.append("FAIL: Too many keys remapped -- something may be wrong.")

    output = "\n".join(lines) + "\n"

    # Print to console
    print(output)

    # Save to file
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(output, encoding="utf-8")
    print(f"Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
