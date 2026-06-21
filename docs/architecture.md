# Architecture

This document describes the internal workings of the Type-Ahead Search engine.

## 1. Read Path (Suggest)

When a user types a character in the frontend, it triggers the read path:

1. **Client Request**: `GET /suggest?q=<prefix>&mode=<mode>`
2. **Cache Ring**: The application computes a deterministic hash of the `mode:prefix` key and locates the responsible virtual node on a **Consistent Hash Ring**.
3. **Cache Lookup**: If the cache node has the result (and it is not expired), it returns it immediately.
4. **Trie Search**: On a cache miss, the backend traverses an in-memory **Trie**. It locates the node representing the prefix, recursively visits all child nodes to collect valid queries, and sorts them by score.
5. **Cache Store**: The computed result is stored in the assigned cache node with a 60-second Time-To-Live (TTL).
6. **Response**: The top 10 results are returned to the client.

## 2. Write Path (Search & Batching)

To ensure the engine can handle a high volume of search events without blocking reads, writes are decoupled via an asynchronous batching mechanism.

1. **Client Request**: `POST /search`
2. **Batch Buffer**: The query string and current timestamp are instantly appended to a global, in-memory queue (`search_buffer`). The server returns a 200 OK immediately.
3. **Background Flush**: An `asyncio` task wakes up every 5 seconds (or whenever the buffer reaches 50 items).
4. **Store Update**: The background task groups identical queries in the buffer to calculate total occurrences and the most recent timestamp. It applies a single `upsert` per unique query to the Trie.
5. **Persistence**: The Trie is saved to `queries.csv`.
6. **Cache Invalidation**: The cache removes the specific `trending:query` and `basic:query` keys, as well as all possible prefixes of the query, so subsequent reads will fetch fresh data. It also invalidates the `global_trending` cache.

### Crash Trade-Off

Because `POST /search` events are queued in an in-memory list instead of immediately hitting the disk, **up to 5 seconds of search data will be lost** if the Python process crashes or is forcefully terminated. This trade-off significantly increases API throughput while sacrificing strict durability.

## 3. Data Structures

### Trie
The core index is an n-ary tree (Prefix Tree). Each node contains:
- `children`: A dictionary mapping characters to child nodes.
- `is_end`: Boolean indicating if the node marks the end of a complete query.
- `count`: All-time occurrences.
- `last_searched_at`: Timestamp of the most recent search.

### Recency Scoring Formula
To keep the search results fresh and relevant, the system employs an exponential decay formula for "trending" mode:

```
score = count * exp(-0.01 * hours_since_last_searched)
```

**Why this avoids permanent over-ranking:** Without time-decay, a statically popular query (e.g., "Python") with 5000 views would indefinitely obscure a newer, highly relevant query (e.g., "Python 3.12 release") that only has 500 views. By decaying the score based on recency, newer queries with lower counts can temporarily surface to the top of the autocomplete suggestions, reflecting current trends.

## 4. Consistent Hash Ring

The `SuggestCache` is backed by a consistent hash ring with 4 physical nodes. Each physical node is assigned 100 virtual nodes using MD5 deterministic hashing.

When the cache needs to scale (e.g., adding a 5th node), only a small fraction of keys change owners, avoiding a complete cache stampede.

### Demo Output

*Running the consistent hashing demo verifies this behavior:*

```
Consistent Hashing Demo
==================================================

Sample size: 1000 keys
Initial nodes: ['node-0', 'node-1', 'node-2', 'node-3']
Added node: node-4

Distribution BEFORE adding node-4:
  node-0: 256 keys (25.6%)
  node-1: 262 keys (26.2%)
  node-2: 237 keys (23.7%)
  node-3: 245 keys (24.5%)

Distribution AFTER adding node-4:
  node-0: 212 keys (21.2%)
  node-1: 202 keys (20.2%)
  node-2: 183 keys (18.3%)
  node-3: 214 keys (21.4%)
  node-4: 189 keys (18.9%)

Keys that changed owner: 189/1000 (18.9%)
Expected (ideal): ~200/1000 (~20.0%)

PASS: Only a fraction of keys were remapped -- consistent hashing works!
```
