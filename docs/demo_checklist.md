# Type-Ahead Search Demo Checklist

Use this script to record a comprehensive demonstration of the Type-Ahead Search engine's features.

### 1. Basic Type-Ahead & Caching
- [ ] Open the frontend application (`http://localhost:5173/`).
- [ ] Open a new browser tab or terminal and check the cache state for a prefix (e.g., `pyth`):
  - `GET http://localhost:8000/cache/debug?prefix=pyth`
  - *Observe that the `status` is `"miss"`.*
- [ ] Return to the frontend and slowly type `p`, `y`, `t`, `h`.
  - *Observe the instant suggestions powered by the backend.*
- [ ] Check the cache state again for `pyth`:
  - `GET http://localhost:8000/cache/debug?prefix=pyth`
  - *Observe that the `status` is now `"hit"` and it shows the responsible cache node.*

### 2. Search Submission & Recency Ranking
- [ ] Look at the suggestions currently displayed for `pyth` (e.g., "python programming").
- [ ] Submit a brand new, unique search query that starts with `pyth`, for example: `python type ahead demo`.
  - *Press Enter to submit.*
  - *Observe the green "Searched" success toast in the UI.*
- [ ] Clear the search box and type `pyth` again.
  - *Observe that "python type ahead demo" now appears at or near the top of the suggestions due to the recency-aware scoring algorithm!*

### 3. Global Trending Searches
- [ ] Clear the search box.
- [ ] Look at the **Trending Searches** section below the search box.
  - *Observe that "python type ahead demo" is now listed as a trending search.*
- [ ] Click on any trending search pill.
  - *Observe that the search box is populated and a new search is automatically submitted.*

### 4. Background Batching
- [ ] Rapidly submit a search query 10 times in a row (e.g., type "test query" and hit Enter repeatedly).
- [ ] Quickly open a terminal and check the batching statistics:
  - `GET http://localhost:8000/admin/batch-stats`
  - *Observe `current_buffer_size` is > 0 as events are queued.*
- [ ] Wait 5 seconds and check `/admin/batch-stats` again.
  - *Observe `current_buffer_size` is 0, and `total_store_writes` only incremented by 1 despite firing 10 queries.*

### 5. Performance Metrics
- [ ] Run the load testing script in the terminal:
  - `cd docs && python load_test.py`
  - *Observe ~500 requests being fired rapidly.*
- [ ] Check the rolling performance metrics:
  - `GET http://localhost:8000/admin/perf-stats`
  - *Observe the `p50`, `p95`, and `p99` latency metrics (likely under a few milliseconds), alongside the overall cache hit rate.*
