"""
Type-Ahead Search — FastAPI backend.

On startup the server loads ``/data/queries.csv`` into a Trie.
The ``GET /suggest`` endpoint returns the top-10 matches for a prefix.
The ``POST /search`` endpoint records a search by incrementing the trie
count and persisting the change back to ``queries.csv``.
"""

from __future__ import annotations

import csv
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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


# ---------------------------------------------------------------------------
# Application lifespan — build the Trie once at startup
# ---------------------------------------------------------------------------

trie = Trie()


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

    - Empty or whitespace-only input → empty list (HTTP 200).
    - Unknown prefix → empty list (HTTP 200).
    - Results sorted by ``count`` descending.
    """
    prefix = q.strip().lower()
    if not prefix:
        return SuggestResponse(suggestions=[])

    results = trie.search(prefix, top_k=10)
    return SuggestResponse(
        suggestions=[Suggestion(**r) for r in results],
    )


@app.post("/search", response_model=SearchResponse)
async def search(body: SearchRequest) -> SearchResponse:
    """Record a search: increment the query's count by 1 and persist.

    - Normalizes the query the same way as ``/suggest``.
    - If the query exists in the trie its count is incremented.
    - If it doesn't exist it is inserted with count = 1.
    - The updated trie is written back to ``queries.csv``.
    """
    normalized = body.query.strip().lower()
    if not normalized:
        return SearchResponse(message="Searched")

    trie.upsert(normalized, delta=1)
    persist_csv()

    return SearchResponse(message="Searched")
