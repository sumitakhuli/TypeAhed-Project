# Type-Ahead Search

A fast autocomplete search engine powered by Wikipedia pageview data.
Suggestions are served from an in-memory **Trie** built from the most popular
English Wikipedia page titles.

## Project Structure

```
├── backend/          # FastAPI application
│   ├── main.py       # API entry-point
│   ├── trie.py       # Trie data structure
│   ├── test_api.py   # Pytest test suite
│   └── requirements.txt
├── frontend/         # React (Vite) app — coming soon
├── data/
│   ├── build_dataset.py   # Downloads & processes Wikipedia pageviews
│   └── queries.csv        # Generated dataset (not checked in)
└── docs/             # Documentation (placeholder)
```

## Quick Start

### 1. Build the dataset

```bash
cd data
python build_dataset.py          # downloads ~3 hourly dumps
python build_dataset.py --hours 5  # or more if you need 100k+ rows
```

This creates `data/queries.csv` with columns `query` and `count`.

### 2. Install backend dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 3. Run the API server

```bash
cd backend
python -m uvicorn main:app --reload --port 8000
```

### 4. Try a suggestion

```
GET http://localhost:8000/suggest?q=pyth
```

```json
{
  "suggestions": [
    { "query": "python (programming language)", "count": 4231 },
    { "query": "python", "count": 3892 }
  ]
}
```

## Background Search Batching

To improve throughput under high load, `POST /search` events are queued in an in-memory buffer rather than immediately written to the backing store. A background task periodically groups these buffered events by query, calculates aggregated increments, and flushes them to the Trie and persistent CSV store every 5 seconds or whenever the buffer reaches 50 items. 

**Trade-off Notice**: Because events are buffered in memory, there is a risk of data loss. If the backend process crashes or is forcefully terminated, any unflushed search events (up to 5 seconds or 50 queries worth) will be lost permanently. This prioritizes performance and scaling at the cost of strict durability guarantees.

## Running Tests

```bash
cd backend
pytest test_api.py -v
```

## Requirements

- Python 3.10+
- Internet connection (for dataset download)
