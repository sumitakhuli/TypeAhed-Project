"""
Consistent hash ring for distributing cache keys across logical nodes.

Uses MD5-based hashing (deterministic across processes) with 100 virtual
nodes per physical node to ensure even distribution.
"""

from __future__ import annotations

import bisect
import hashlib


def _hash(key: str) -> int:
    """Return a deterministic integer hash of *key* using MD5.

    We take the first 8 bytes of the MD5 digest and interpret them as a
    big-endian unsigned integer.  This gives us a 64-bit hash space —
    more than enough for ring placement.
    """
    return int.from_bytes(
        hashlib.md5(key.encode("utf-8")).digest()[:8],
        byteorder="big",
    )


VIRTUAL_NODES_PER_PHYSICAL = 100


class ConsistentHashRing:
    """A consistent hash ring mapping keys to physical node IDs.

    Each physical node is represented by ``VIRTUAL_NODES_PER_PHYSICAL``
    virtual nodes placed on a sorted ring.
    """

    def __init__(self, nodes: list[str] | None = None) -> None:
        # Sorted list of (hash_value, node_id)
        self._ring: list[tuple[int, str]] = []
        # Just the hash values, kept in sync for fast bisect lookups
        self._keys: list[int] = []
        # Track which physical nodes are on the ring
        self._nodes: set[str] = set()

        for node_id in (nodes or []):
            self.add_node(node_id)

    @property
    def nodes(self) -> set[str]:
        """The set of physical node IDs currently on the ring."""
        return set(self._nodes)

    def add_node(self, node_id: str) -> None:
        """Add a physical node (with its virtual nodes) to the ring."""
        if node_id in self._nodes:
            return
        self._nodes.add(node_id)
        for i in range(VIRTUAL_NODES_PER_PHYSICAL):
            h = _hash(f"{node_id}#{i}")
            idx = bisect.bisect_left(self._keys, h)
            self._keys.insert(idx, h)
            self._ring.insert(idx, (h, node_id))

    def remove_node(self, node_id: str) -> None:
        """Remove a physical node (and all its virtual nodes) from the ring."""
        if node_id not in self._nodes:
            return
        self._nodes.discard(node_id)
        # Rebuild without the removed node's entries
        new_ring = [(h, nid) for h, nid in self._ring if nid != node_id]
        self._ring = new_ring
        self._keys = [h for h, _ in new_ring]

    def get_node(self, key: str) -> str:
        """Return the physical node that owns *key*.

        Hashes *key*, then walks clockwise on the ring to find the next
        virtual node.  Raises ``RuntimeError`` if the ring is empty.
        """
        if not self._ring:
            raise RuntimeError("Hash ring is empty — no nodes available.")

        h = _hash(key)
        idx = bisect.bisect_right(self._keys, h)
        # Wrap around to the beginning of the ring
        if idx >= len(self._keys):
            idx = 0
        return self._ring[idx][1]
