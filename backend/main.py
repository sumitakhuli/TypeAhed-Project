"""
Type-Ahead Search — FastAPI backend.

On startup the server loads ``/data/queries.csv`` into a Trie.
The ``GET /suggest`` endpoint returns the top-10 matches for a prefix.
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
    allow_methods=["GET"],
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
