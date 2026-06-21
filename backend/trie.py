"""
Trie data structure for prefix-based autocomplete suggestions.

Each node in the trie represents a single character. Terminal nodes
(where is_end == True) store the full query string and its view count.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TrieNode:
    """A single node in the Trie."""

    children: dict[str, TrieNode] = field(default_factory=dict)
    is_end: bool = False
    query: str | None = None
    count: int = 0


class Trie:
    """Character-level trie that supports prefix search with ranked results."""

    def __init__(self) -> None:
        self.root = TrieNode()

    def insert(self, query: str, count: int) -> None:
        """Insert a query with its associated view count into the trie."""
        node = self.root
        for char in query:
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]
        node.is_end = True
        node.query = query
        node.count = count

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

    def _collect(self, node: TrieNode, results: list[tuple[str, int]]) -> None:
        """Recursively collect all terminal (query, count) pairs under *node*."""
        if node.is_end and node.query is not None:
            results.append((node.query, node.count))
        for child in node.children.values():
            self._collect(child, results)

    def search(self, prefix: str, top_k: int = 10) -> list[dict[str, object]]:
        """Return up to *top_k* suggestions for the given prefix.

        Results are sorted by count descending.  Returns an empty list when
        the prefix has no matches.
        """
        node = self._find_node(prefix)
        if node is None:
            return []

        results: list[tuple[str, int]] = []
        self._collect(node, results)

        # Sort by count descending, then alphabetically for determinism
        results.sort(key=lambda item: (-item[1], item[0]))

        return [
            {"query": query, "count": count}
            for query, count in results[:top_k]
        ]
