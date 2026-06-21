"""
In-process cache backed by a consistent hash ring.

Each logical node is a plain Python dict mapping
``key -> (value, expires_at)``.  The ring determines which node owns a key.
"""

from __future__ import annotations

import time
from typing import Any

from hash_ring import ConsistentHashRing

DEFAULT_TTL_SECONDS = 60
DEFAULT_NODES = ["node-0", "node-1", "node-2", "node-3"]


class SuggestCache:
    """Cache-aside layer for autocomplete suggestions.

    Attributes:
        hits:   Total cache-hit count since startup.
        misses: Total cache-miss count since startup.
    """

    def __init__(
        self,
        nodes: list[str] | None = None,
        ttl: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        self.ring = ConsistentHashRing(nodes or DEFAULT_NODES)
        self.ttl = ttl
        self.hits = 0
        self.misses = 0

        # One dict per physical node: node_id -> { key: (value, expires_at) }
        self._stores: dict[str, dict[str, tuple[Any, float]]] = {
            nid: {} for nid in self.ring.nodes
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str) -> Any | None:
        """Look up *key*.  Returns the cached value on a hit, ``None`` on a miss."""
        node_id = self.ring.get_node(key)
        store = self._stores[node_id]

        entry = store.get(key)
        if entry is None:
            self.misses += 1
            return None

        value, expires_at = entry
        if time.monotonic() > expires_at:
            # Expired — evict and count as a miss
            del store[key]
            self.misses += 1
            return None

        self.hits += 1
        return value

    def put(self, key: str, value: Any) -> None:
        """Store *value* under *key* with the default TTL."""
        node_id = self.ring.get_node(key)
        self._stores[node_id][key] = (value, time.monotonic() + self.ttl)

    def delete(self, key: str) -> None:
        """Remove *key* from whichever node owns it (no-op if absent)."""
        node_id = self.ring.get_node(key)
        self._stores[node_id].pop(key, None)

    def invalidate_all_prefixes(self, query: str) -> None:
        """Delete every prefix of *query* (length 1 → full length) from the cache.

        Each prefix may land on a different node — the ring is consulted
        per-prefix.
        """
        for length in range(1, len(query) + 1):
            prefix = query[:length]
            self.delete(prefix)

    def owner_of(self, key: str) -> str:
        """Return the node ID that owns *key* (for the debug endpoint)."""
        return self.ring.get_node(key)

    def contains(self, key: str) -> bool:
        """Return whether *key* is present and not expired (without altering counters)."""
        node_id = self.ring.get_node(key)
        store = self._stores[node_id]
        entry = store.get(key)
        if entry is None:
            return False
        _, expires_at = entry
        if time.monotonic() > expires_at:
            del store[key]
            return False
        return True
