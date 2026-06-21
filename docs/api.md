# Type-Ahead Search API

This document details the HTTP endpoints exposed by the Type-Ahead Search backend.

## 1. `GET /suggest`
Returns up to 10 autocomplete suggestions for the given prefix. Backed by the cache-aside pattern.

**Query Parameters:**
- `q` (string): The prefix to search for.
- `mode` (string, optional): `"trending"` (default) or `"basic"`. 
  - `trending`: Results sorted by recency-aware score.
  - `basic`: Results sorted by raw all-time occurrences.

**Example Request:**
```http
GET /suggest?q=pyth&mode=trending
```

**Example Response (200 OK):**
```json
{
  "suggestions": [
    {
      "query": "python (programming language)",
      "count": 4231
    },
    {
      "query": "python",
      "count": 3892
    }
  ]
}
```

---

## 2. `POST /search`
Records a search event. Events are queued in memory and batched in the background.

**JSON Body:**
- `query` (string): The search query to record.

**Example Request:**
```http
POST /search
Content-Type: application/json

{
  "query": "python"
}
```

**Example Response (200 OK):**
```json
{
  "message": "Searched"
}
```

---

## 3. `GET /trending`
Returns the top 10 most popular queries overall, based on recency-aware scoring.

**Query Parameters:**
- `limit` (integer, optional): Number of results to return. Default is 10.

**Example Request:**
```http
GET /trending?limit=5
```

**Example Response (200 OK):**
```json
{
  "suggestions": [
    {
      "query": "main page",
      "count": 9200
    },
    {
      "query": "wikipedia",
      "count": 8100
    }
  ]
}
```

---

## 4. `GET /cache/debug`
Returns the cache state for a given prefix without computing or caching a new value. Useful for inspecting the hash ring.

**Query Parameters:**
- `prefix` (string): The search prefix.
- `mode` (string, optional): `"trending"` (default) or `"basic"`.

**Example Request:**
```http
GET /cache/debug?prefix=pyth&mode=trending
```

**Example Response (200 OK):**
```json
{
  "prefix": "pyth",
  "owner_node": "node-2",
  "status": "hit",
  "mode": "trending"
}
```

---

## 5. `GET /admin/batch-stats`
Returns running totals of the asynchronous batch processing engine.

**Example Request:**
```http
GET /admin/batch-stats
```

**Example Response (200 OK):**
```json
{
  "total_search_events": 452,
  "total_store_writes": 18,
  "current_buffer_size": 4
}
```

---

## 6. `GET /admin/perf-stats`
Returns performance statistics, latency percentiles, and cache hit rates over a rolling window of 500 requests.

**Example Request:**
```http
GET /admin/perf-stats
```

**Example Response (200 OK):**
```json
{
  "p50_latency_ms": 1.25,
  "p95_latency_ms": 4.10,
  "p99_latency_ms": 8.30,
  "cache_hit_rate_percent": 82.5,
  "total_store_reads": 79,
  "total_store_writes": 18
}
```
