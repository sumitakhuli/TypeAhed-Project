"""
Tests for the Type-Ahead Search suggestion API.

Run with:
    cd backend
    pytest test_api.py -v
"""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# We need to set up the trie *before* importing the app so the lifespan
# loader doesn't look for a real CSV.  We'll build a small fixture instead.

from trie import Trie

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_DATA = [
    ("python programming", 5000),
    ("python tutorial", 4500),
    ("python snake", 3000),
    ("pytorch", 2800),
    ("pandas dataframe", 2500),
    ("javascript", 8000),
    ("java", 7500),
    ("java virtual machine", 2000),
    ("machine learning", 6000),
    ("mars", 1500),
    ("united states", 9000),
    ("united kingdom", 8500),
]


@pytest.fixture(scope="module")
def csv_path(tmp_path_factory) -> Path:
    """Write sample data to a temporary CSV file."""
    path = tmp_path_factory.mktemp("data") / "queries.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["query", "count"])
        for query, count in SAMPLE_DATA:
            writer.writerow([query, count])
    return path


@pytest.fixture(scope="module")
def client(csv_path) -> TestClient:
    """Create a TestClient with the trie loaded from sample data."""
    # Import here so the module-level trie object is the one we populate
    import main

    # Reset and reload with our fixture data
    main.trie = Trie()
    main.load_trie(csv_path)
    return TestClient(main.app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSuggestEndpoint:
    """Tests for GET /suggest?q=<prefix>."""

    def test_known_prefix_with_matches(self, client: TestClient) -> None:
        """A known prefix should return matching suggestions sorted by count."""
        resp = client.get("/suggest", params={"q": "python"})
        assert resp.status_code == 200
        data = resp.json()
        suggestions = data["suggestions"]
        assert len(suggestions) > 0
        # All results should start with "python"
        for s in suggestions:
            assert s["query"].startswith("python")
        # Should be sorted by count descending
        counts = [s["count"] for s in suggestions]
        assert counts == sorted(counts, reverse=True)

    def test_prefix_returns_top_10_max(self, client: TestClient) -> None:
        """Even if there are more matches, at most 10 should be returned."""
        # "python" has 3 matches in our sample — all should appear
        resp = client.get("/suggest", params={"q": "py"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["suggestions"]) <= 10

    def test_prefix_no_matches(self, client: TestClient) -> None:
        """A prefix with no matches should return an empty list, not an error."""
        resp = client.get("/suggest", params={"q": "zzzznoexist"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["suggestions"] == []

    def test_empty_input(self, client: TestClient) -> None:
        """Empty query string should return an empty list."""
        resp = client.get("/suggest", params={"q": ""})
        assert resp.status_code == 200
        assert resp.json()["suggestions"] == []

    def test_missing_input(self, client: TestClient) -> None:
        """Missing 'q' parameter should return an empty list (not a 500/422)."""
        resp = client.get("/suggest")
        assert resp.status_code == 200
        assert resp.json()["suggestions"] == []

    def test_whitespace_only_input(self, client: TestClient) -> None:
        """Whitespace-only input should be treated as empty."""
        resp = client.get("/suggest", params={"q": "   "})
        assert resp.status_code == 200
        assert resp.json()["suggestions"] == []

    def test_case_insensitivity(self, client: TestClient) -> None:
        """Search should be case-insensitive."""
        lower = client.get("/suggest", params={"q": "python"}).json()
        upper = client.get("/suggest", params={"q": "PYTHON"}).json()
        mixed = client.get("/suggest", params={"q": "PyThOn"}).json()

        assert lower["suggestions"] == upper["suggestions"]
        assert lower["suggestions"] == mixed["suggestions"]

    def test_partial_prefix(self, client: TestClient) -> None:
        """Short prefixes should match all queries starting with those chars."""
        resp = client.get("/suggest", params={"q": "un"})
        assert resp.status_code == 200
        suggestions = resp.json()["suggestions"]
        assert len(suggestions) == 2  # "united states" and "united kingdom"
        # Higher count first
        assert suggestions[0]["query"] == "united states"
        assert suggestions[1]["query"] == "united kingdom"

    def test_response_shape(self, client: TestClient) -> None:
        """Each suggestion should have 'query' (str) and 'count' (int) fields."""
        resp = client.get("/suggest", params={"q": "java"})
        assert resp.status_code == 200
        for s in resp.json()["suggestions"]:
            assert isinstance(s["query"], str)
            assert isinstance(s["count"], int)


# ---------------------------------------------------------------------------
# POST /search tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def search_client(tmp_path) -> TestClient:
    """Create an isolated TestClient for /search tests so trie mutations
    don't leak into the /suggest test class."""
    import main
    from cache import SuggestCache

    csv_file = tmp_path / "queries.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["query", "count"])
        for query, count in SAMPLE_DATA:
            writer.writerow([query, count])

    main.trie = Trie()
    main.load_trie(csv_file)
    main.suggest_cache = SuggestCache()

    # Monkey-patch _data_csv_path so persist_csv writes to our temp file
    original = main._data_csv_path
    main._data_csv_path = lambda: csv_file
    client = TestClient(main.app)
    yield client
    main._data_csv_path = original


class TestSearchEndpoint:
    """Tests for POST /search."""

    def test_search_increments_existing_query(self, search_client: TestClient) -> None:
        """Searching an existing query should increment its count by 1."""
        # Get original count
        resp = search_client.get("/suggest", params={"q": "python programming"})
        original_count = resp.json()["suggestions"][0]["count"]

        import main
        # Submit search
        resp = search_client.post("/search", json={"query": "python programming"})
        main.flush_buffer()
        assert resp.status_code == 200
        assert resp.json()["message"] == "Searched"

        # Verify count incremented
        resp = search_client.get("/suggest", params={"q": "python programming"})
        new_count = resp.json()["suggestions"][0]["count"]
        assert new_count == original_count + 1

    def test_search_inserts_new_query(self, search_client: TestClient) -> None:
        """Searching a brand-new query should insert it with count = 1."""
        import main
        resp = search_client.post("/search", json={"query": "quantum computing"})
        main.flush_buffer()
        assert resp.status_code == 200
        assert resp.json()["message"] == "Searched"

        # The new query should now appear in suggestions
        resp = search_client.get("/suggest", params={"q": "quantum computing"})
        suggestions = resp.json()["suggestions"]
        assert len(suggestions) == 1
        assert suggestions[0]["query"] == "quantum computing"
        assert suggestions[0]["count"] == 1

    def test_search_empty_query(self, search_client: TestClient) -> None:
        """Empty or whitespace-only query should return Searched without error."""
        resp = search_client.post("/search", json={"query": "   "})
        assert resp.status_code == 200
        assert resp.json()["message"] == "Searched"

    def test_search_normalizes_case(self, search_client: TestClient) -> None:
        """Search should normalize to lowercase, matching the trie."""
        import main
        resp = search_client.post("/search", json={"query": "PYTHON Programming"})
        main.flush_buffer()
        assert resp.status_code == 200

        resp = search_client.get("/suggest", params={"q": "python programming"})
        found = resp.json()["suggestions"][0]
        assert found["query"] == "python programming"
        # Count should be original (5000) + 1
        assert found["count"] == 5001

    def test_search_updates_visible_in_suggest(self, search_client: TestClient) -> None:
        """After searching, the next /suggest call should reflect the new count."""
        import main
        # Search for "mars" twice
        search_client.post("/search", json={"query": "mars"})
        search_client.post("/search", json={"query": "mars"})
        main.flush_buffer()

        resp = search_client.get("/suggest", params={"q": "mars"})
        mars = resp.json()["suggestions"][0]
        assert mars["query"] == "mars"
        # Original was 1500, +2 = 1502
        assert mars["count"] == 1502


# ---------------------------------------------------------------------------
# Cache layer tests
# ---------------------------------------------------------------------------


class TestCacheLayer:
    """Tests for the suggest cache (cache-aside + invalidation)."""

    def test_second_suggest_is_cache_hit(self, search_client: TestClient) -> None:
        """First call is a miss, second identical call should be a cache hit."""
        import main

        initial_hits = main.suggest_cache.hits
        initial_misses = main.suggest_cache.misses

        # First call — cache miss
        search_client.get("/suggest", params={"q": "python"})
        assert main.suggest_cache.misses == initial_misses + 1

        # Second call — cache hit
        search_client.get("/suggest", params={"q": "python"})
        assert main.suggest_cache.hits == initial_hits + 1

    def test_search_invalidates_cache(self, search_client: TestClient) -> None:
        """POST /search should invalidate cached prefixes so the next
        /suggest call returns the updated count."""
        import main

        # Warm the cache
        resp = search_client.get("/suggest", params={"q": "mars"})
        original = resp.json()["suggestions"][0]["count"]

        # The prefix should now be cached
        assert main.suggest_cache.contains("trending:mars")

        # Search (should invalidate)
        search_client.post("/search", json={"query": "mars"})
        main.flush_buffer()

        # Cache should be invalidated
        assert not main.suggest_cache.contains("trending:mars")

        # Next suggest call should return updated count
        resp = search_client.get("/suggest", params={"q": "mars"})
        assert resp.json()["suggestions"][0]["count"] == original + 1

    def test_invalidation_covers_all_prefixes(self, search_client: TestClient) -> None:
        """Invalidation should clear 'j', 'ja', 'jav', 'java' when searching 'java'."""
        import main

        # Warm cache for multiple prefixes
        for prefix in ["j", "ja", "jav", "java"]:
            search_client.get("/suggest", params={"q": prefix})
            assert main.suggest_cache.contains(f"trending:{prefix}")

        # Search for "java" should invalidate all its prefixes
        search_client.post("/search", json={"query": "java"})
        main.flush_buffer()

        for prefix in ["j", "ja", "jav", "java"]:
            assert not main.suggest_cache.contains(f"trending:{prefix}")

    def test_cache_results_match_trie(self, search_client: TestClient) -> None:
        """Cached results should be identical to fresh trie results."""
        # First call (miss — from trie)
        resp1 = search_client.get("/suggest", params={"q": "united"})
        # Second call (hit — from cache)
        resp2 = search_client.get("/suggest", params={"q": "united"})
        assert resp1.json() == resp2.json()

    def test_empty_query_not_cached(self, search_client: TestClient) -> None:
        """Empty queries should not be stored in the cache."""
        import main

        initial_misses = main.suggest_cache.misses
        search_client.get("/suggest", params={"q": ""})
        # Should not have incremented miss (never went to cache)
        assert main.suggest_cache.misses == initial_misses


# ---------------------------------------------------------------------------
# GET /cache/debug tests
# ---------------------------------------------------------------------------


class TestCacheDebugEndpoint:
    """Tests for GET /cache/debug?prefix=<prefix>."""

    def test_debug_miss_before_suggest(self, search_client: TestClient) -> None:
        """Before any /suggest call, the cache should show a miss."""
        resp = search_client.get("/cache/debug", params={"prefix": "python"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["prefix"] == "python"
        assert data["status"] == "miss"
        assert data["owner_node"].startswith("node-")

    def test_debug_hit_after_suggest(self, search_client: TestClient) -> None:
        """After a /suggest call, the debug endpoint should show a hit."""
        search_client.get("/suggest", params={"q": "java"})

        resp = search_client.get("/cache/debug", params={"prefix": "java"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["prefix"] == "java"
        assert data["status"] == "hit"
        assert data["owner_node"].startswith("node-")

    def test_debug_empty_prefix(self, search_client: TestClient) -> None:
        """Empty prefix should return miss with empty fields."""
        resp = search_client.get("/cache/debug", params={"prefix": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert data["prefix"] == ""
        assert data["status"] == "miss"


# ---------------------------------------------------------------------------
# GET /admin/batch-stats tests
# ---------------------------------------------------------------------------


class TestAdminBatchStatsEndpoint:
    """Tests for GET /admin/batch-stats."""

    def test_batch_stats_after_search(self, search_client: TestClient) -> None:
        """The batch stats endpoint should return updated counts after searches and flushes."""
        import main
        
        # Initial stats
        resp1 = search_client.get("/admin/batch-stats")
        assert resp1.status_code == 200
        initial_events = resp1.json()["total_search_events"]
        initial_writes = resp1.json()["total_store_writes"]
        
        # Submit 3 searches for the same query
        search_client.post("/search", json={"query": "test query"})
        search_client.post("/search", json={"query": "test query"})
        search_client.post("/search", json={"query": "test query"})
        
        # Buffer should have 3 events
        resp2 = search_client.get("/admin/batch-stats")
        assert resp2.json()["current_buffer_size"] == 3
        assert resp2.json()["total_search_events"] == initial_events + 3
        
        # Flush the buffer (should collapse 3 events into 1 store write)
        main.flush_buffer()
        
        # Check stats again
        resp3 = search_client.get("/admin/batch-stats")
        data3 = resp3.json()
        assert data3["current_buffer_size"] == 0
        assert data3["total_search_events"] == initial_events + 3
        assert data3["total_store_writes"] == initial_writes + 1
