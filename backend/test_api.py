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
