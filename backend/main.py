"""
Type-Ahead Search — FastAPI backend.

On startup the server loads ``/data/queries.csv`` into a Trie.
The ``GET /suggest`` endpoint returns the top-10 matches for a prefix,
backed by a consistent-hash-ring cache with 60-second TTL.
The ``POST /search`` endpoint records a search by incrementing the trie
count, invalidating affected cache prefixes, and persisting to CSV.
"""

from __future__ import annotations

import asyncio
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

# --- Batching State ---
FLUSH_INTERVAL_SECONDS = 5
MAX_BUFFER_SIZE = 50

search_buffer: list[tuple[str, float]] = []
total_search_events: int = 0
total_store_writes: int = 0

def flush_buffer() -> None:
    """Flush buffered search events into the trie and cache synchronously."""
    global total_store_writes

    if not search_buffer:
        return

    # Take the current items and clear the buffer
    batch = search_buffer[:]
    search_buffer.clear()

    # Group by query
    grouped: dict[str, dict[str, float]] = {}
    for query, ts in batch:
        if query not in grouped:
            grouped[query] = {"count": 0, "last_searched_at": ts}
        grouped[query]["count"] += 1
        grouped[query]["last_searched_at"] = max(grouped[query]["last_searched_at"], ts)

    writes = len(grouped)
    total_store_writes += writes

    for query, data in grouped.items():
        trie.upsert(query, delta=data["count"], last_searched_at=data["last_searched_at"])
        suggest_cache.invalidate_all_prefixes(query)

    persist_csv()
    suggest_cache.delete("global_trending:10")

    print(f"{len(batch)} search events -> {writes} store writes")

async def periodic_flush() -> None:
    """Background task to flush the buffer periodically."""
    while True:
        await asyncio.sleep(FLUSH_INTERVAL_SECONDS)
        if search_buffer:
            flush_buffer()


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
    """Load data on startup; start background flush task."""
    load_trie()
    flush_task = asyncio.create_task(periodic_flush())
    yield
    flush_task.cancel()
    # Flush any remaining items on graceful shutdown
    if search_buffer:
        flush_buffer()


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
    """Record a search: queues the query for batch processing.

    Returns immediately. A background task (or size threshold) will
    flush the buffer, update the trie, and invalidate the cache.
    """
    global total_search_events

    normalized = body.query.strip().lower()
    if not normalized:
        return SearchResponse(message="Searched")

    search_buffer.append((normalized, time.time()))
    total_search_events += 1

    if len(search_buffer) >= MAX_BUFFER_SIZE:
        flush_buffer()

    return SearchResponse(message="Searched")

class BatchStatsResponse(BaseModel):
    total_search_events: int
    total_store_writes: int
    current_buffer_size: int

@app.get("/admin/batch-stats", response_model=BatchStatsResponse)
async def batch_stats() -> BatchStatsResponse:
    """Return running totals of batch processing stats."""
    return BatchStatsResponse(
        total_search_events=total_search_events,
        total_store_writes=total_store_writes,
        current_buffer_size=len(search_buffer),
    )


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
