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
import time
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
    mode: str


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
    now = time.time()
    with open(csv_path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            query = row["query"]
            count = int(row["count"])
            last_searched_at = float(row.get("last_searched_at", now))
            trie.insert(query, count, last_searched_at)
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
    entries: list[tuple[str, int, float]] = []

    def _walk(node) -> None:
        if node.is_end and node.query is not None:
            entries.append((node.query, node.count, node.last_searched_at))
        for child in node.children.values():
            _walk(child)

    _walk(trie.root)

    # Sort by count desc for human readability
    entries.sort(key=lambda e: -e[1])

    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["query", "count", "last_searched_at"])
        for query, count, last_searched_at in entries:
            writer.writerow([query, count, last_searched_at])


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
async def suggest(
    q: str = Query(default=""),
    mode: str = Query(default="trending")
) -> SuggestResponse:
    """Return up to 10 autocomplete suggestions for the given prefix *q*.

    Uses cache-aside: check the consistent-hash-ring cache first, compute
    from the trie on a miss, and store the result with a 60-second TTL.
    """
    if mode not in ("basic", "trending"):
        mode = "trending"

    prefix = q.strip().lower()
    if not prefix:
        return SuggestResponse(suggestions=[])

    cache_key = f"{mode}:{prefix}"

    # --- Cache lookup ---
    cached = suggest_cache.get(cache_key)
    if cached is not None:
        return SuggestResponse(suggestions=[Suggestion(**r) for r in cached])

    # --- Cache miss: compute from trie ---
    results = trie.search(prefix, top_k=10, mode=mode)
    suggest_cache.put(cache_key, results)

    return SuggestResponse(
        suggestions=[Suggestion(**r) for r in results],
    )


@app.get("/trending", response_model=SuggestResponse)
async def trending(limit: int = Query(default=10)) -> SuggestResponse:
    """Return top N queries overall by recency-aware score."""
    cache_key = f"global_trending:{limit}"

    cached = suggest_cache.get(cache_key)
    if cached is not None:
        return SuggestResponse(suggestions=[Suggestion(**r) for r in cached])

    results = trie.get_trending(limit=limit)
    suggest_cache.put(cache_key, results)

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

    # Invalidate every prefix of this query from the cache (both modes)
    suggest_cache.invalidate_all_prefixes(normalized)
    # Also invalidate the global trending caches
    suggest_cache.delete("global_trending:10")

    return SearchResponse(message="Searched")


@app.get("/cache/debug", response_model=CacheDebugResponse)
async def cache_debug(
    prefix: str = Query(default=""),
    mode: str = Query(default="trending")
) -> CacheDebugResponse:
    """Return cache state for a given prefix without computing a new value.

    Useful for debugging: shows which node owns the key and whether
    it's currently cached (hit) or not (miss).
    """
    if mode not in ("basic", "trending"):
        mode = "trending"

    normalized = prefix.strip().lower()
    if not normalized:
        return CacheDebugResponse(
            prefix="",
            owner_node="",
            status="miss",
            mode=mode,
        )

    cache_key = f"{mode}:{normalized}"
    owner = suggest_cache.owner_of(cache_key)
    is_cached = suggest_cache.contains(cache_key)

    return CacheDebugResponse(
        prefix=normalized,
        owner_node=owner,
        status="hit" if is_cached else "miss",
        mode=mode,
    )
