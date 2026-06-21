"""
Type-Ahead Search — FastAPI backend.

On startup the server loads ``/data/queries.csv`` into a Trie.
The ``GET /suggest`` endpoint returns the top-10 matches for a prefix,
backed by a consistent-hash-ring cache with 60-second TTL.
The ``POST /search`` endpoint records a search by incrementing the trie
count, invalidating affected cache prefixes, and persisting to CSV.
"""

from __future__ import annotations

import csv
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from cache import SuggestCache
from trie import Trie

# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class Suggestion(BaseModel):
    query: str
    count: int


class SuggestResponse(BaseModel):
    suggestions: list[Suggestion]


class SearchRequest(BaseModel):
    query: str


class SearchResponse(BaseModel):
    message: str


class CacheDebugResponse(BaseModel):
    prefix: str
    owner_node: str
    status: str  # "hit" | "miss"


# ---------------------------------------------------------------------------
# Application state — Trie + Cache
# ---------------------------------------------------------------------------

trie = Trie()
suggest_cache = SuggestCache()


def _data_csv_path() -> Path:
    """Resolve the path to ``queries.csv`` relative to the project root."""
    # backend/ lives one level under the project root
    return Path(__file__).resolve().parent.parent / "data" / "queries.csv"


def load_trie(csv_path: Path | None = None) -> None:
    """Read *csv_path* and insert every row into the global :pydata:`trie`."""
    if csv_path is None:
        csv_path = _data_csv_path()

    if not csv_path.exists():
        print(f"WARNING: {csv_path} not found — trie will be empty.")
        return

    loaded = 0
    with open(csv_path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            query = row["query"]
            count = int(row["count"])
            trie.insert(query, count)
            loaded += 1

    print(f"Loaded {loaded:,} queries into the trie.")


def persist_csv(csv_path: Path | None = None) -> None:
    """Rewrite *csv_path* from the current trie contents.

    This is the simplest persistence strategy: a full CSV rewrite.
    Adequate for the current synchronous, single-process setup.
    """
    if csv_path is None:
        csv_path = _data_csv_path()

    # Collect every terminal node
    entries: list[tuple[str, int]] = []

    def _walk(node) -> None:
        if node.is_end and node.query is not None:
            entries.append((node.query, node.count))
        for child in node.children.values():
            _walk(child)

    _walk(trie.root)

    # Sort by count desc for human readability
    entries.sort(key=lambda e: -e[1])

    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["query", "count"])
        for query, count in entries:
            writer.writerow([query, count])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load data on startup; nothing special on shutdown."""
    load_trie()
    yield


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Type-Ahead Search API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/suggest", response_model=SuggestResponse)
async def suggest(q: str = Query(default="")) -> SuggestResponse:
    """Return up to 10 autocomplete suggestions for the given prefix *q*.

    Uses cache-aside: check the consistent-hash-ring cache first, compute
    from the trie on a miss, and store the result with a 60-second TTL.
    """
    prefix = q.strip().lower()
    if not prefix:
        return SuggestResponse(suggestions=[])

    # --- Cache lookup ---
    cached = suggest_cache.get(prefix)
    if cached is not None:
        return SuggestResponse(suggestions=[Suggestion(**r) for r in cached])

    # --- Cache miss: compute from trie ---
    results = trie.search(prefix, top_k=10)
    suggest_cache.put(prefix, results)

    return SuggestResponse(
        suggestions=[Suggestion(**r) for r in results],
    )


@app.post("/search", response_model=SearchResponse)
async def search(body: SearchRequest) -> SearchResponse:
    """Record a search: increment the query's count by 1 and persist.

    After updating the trie, invalidates all prefixes of the query in the
    cache so subsequent /suggest calls reflect the new count.
    """
    normalized = body.query.strip().lower()
    if not normalized:
        return SearchResponse(message="Searched")

    trie.upsert(normalized, delta=1)
    persist_csv()

    # Invalidate every prefix of this query from the cache
    suggest_cache.invalidate_all_prefixes(normalized)

    return SearchResponse(message="Searched")


@app.get("/cache/debug", response_model=CacheDebugResponse)
async def cache_debug(prefix: str = Query(default="")) -> CacheDebugResponse:
    """Return cache state for a given prefix without computing a new value.

    Useful for debugging: shows which node owns the key and whether
    it's currently cached (hit) or not (miss).
    """
    normalized = prefix.strip().lower()
    if not normalized:
        return CacheDebugResponse(
            prefix="",
            owner_node="",
            status="miss",
        )

    owner = suggest_cache.owner_of(normalized)
    is_cached = suggest_cache.contains(normalized)

    return CacheDebugResponse(
        prefix=normalized,
        owner_node=owner,
        status="hit" if is_cached else "miss",
    )
