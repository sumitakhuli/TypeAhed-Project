"""
Trie data structure for prefix-based autocomplete suggestions.

Each node in the trie represents a single character. Terminal nodes
(where is_end == True) store the full query string and its view count.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

# Decay rate for trending score.
# Score = count * exp(-DECAY_RATE * hours_since_last_searched)
DECAY_RATE = 0.01


@dataclass
class TrieNode:
    """A single node in the Trie."""

    children: dict[str, TrieNode] = field(default_factory=dict)
    is_end: bool = False
    query: str | None = None
    count: int = 0
    last_searched_at: float = 0.0


class Trie:
    """Character-level trie that supports prefix search with ranked results."""

    def __init__(self) -> None:
        self.root = TrieNode()

    def insert(self, query: str, count: int, last_searched_at: float = 0.0) -> None:
        """Insert a query with its associated view count into the trie."""
        node = self.root
        for char in query:
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]
        node.is_end = True
        node.query = query
        node.count = count
        node.last_searched_at = last_searched_at

    def upsert(self, query: str, delta: int = 1, last_searched_at: float | None = None) -> int:
        """Increment the count for *query* by *delta*, inserting if new.

        Returns the updated count.
        """
        node = self.root
        for char in query:
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]
        node.is_end = True
        node.query = query
        node.count += delta
        node.last_searched_at = last_searched_at if last_searched_at is not None else time.time()
        return node.count

    def _find_node(self, prefix: str) -> TrieNode | None:
        """Walk the trie to the node matching the last character of *prefix*.

        Returns ``None`` if the prefix path does not exist.
        """
        node = self.root
        for char in prefix:
            if char not in node.children:
                return None
            node = node.children[char]
        return node

    def _collect(self, node: TrieNode, results: list[TrieNode]) -> None:
        """Recursively collect all terminal nodes under *node*."""
        if node.is_end and node.query is not None:
            results.append(node)
        for child in node.children.values():
            self._collect(child, results)

    def search(self, prefix: str, top_k: int = 10, mode: str = "trending") -> list[dict[str, object]]:
        """Return up to *top_k* suggestions for the given prefix.

        If mode is "basic", results are sorted by count descending.
        If mode is "trending", results are sorted by recency-aware score.
        Returns an empty list when the prefix has no matches.
        """
        node = self._find_node(prefix)
        if node is None:
            return []

        results: list[TrieNode] = []
        self._collect(node, results)

        now = time.time()

        def _get_score(n: TrieNode) -> float:
            if mode == "basic":
                return float(n.count)
            hours_since = max(0.0, (now - n.last_searched_at) / 3600.0)
            return n.count * math.exp(-DECAY_RATE * hours_since)

        # Sort by score descending, then alphabetically for determinism
        results.sort(key=lambda n: (-_get_score(n), n.query))

        return [
            {"query": n.query, "count": n.count}
            for n in results[:top_k]
        ]

    def get_trending(self, limit: int = 10) -> list[dict[str, object]]:
        """Return top queries overall, sorted by recency-aware score."""
        results: list[TrieNode] = []
        self._collect(self.root, results)

        now = time.time()

        def _get_score(n: TrieNode) -> float:
            hours_since = max(0.0, (now - n.last_searched_at) / 3600.0)
            return n.count * math.exp(-DECAY_RATE * hours_since)

        results.sort(key=lambda n: (-_get_score(n), n.query))

        return [
            {"query": n.query, "count": n.count}
            for n in results[:limit]
        ]
