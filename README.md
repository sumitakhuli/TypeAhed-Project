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

### 1. Build the Dataset

The application is powered by a CSV dataset. We provide a script to download real Wikipedia pageview dumps and compile them into `queries.csv`.

```bash
cd data
python build_dataset.py          # downloads default ~3 hourly dumps
# or specify the number of hours to fetch:
python build_dataset.py --hours 5  
```

This creates `data/queries.csv` with columns `query` and `count`.

### 2. Run the Backend

The backend is a Python FastAPI server running an in-memory Trie and caching layer.

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

### 3. Run the Frontend

The frontend is a React application built with Vite that connects to the backend. Open a new terminal window:

```bash
cd frontend
npm install
npm run dev
```

The app will be available at `http://localhost:5173/`.

## Running Tests

To run the backend test suite:

```bash
cd backend
pytest test_api.py -v
```

## Documentation

- [Architecture Guide](docs/architecture.md): Details on the read/write paths, consistent hash ring, and recency scoring logic.
- [API Reference](docs/api.md): Endpoints, parameters, and example requests/responses.
- [Demo Checklist](docs/demo_checklist.md): A step-by-step guide to demonstrating the features.

## Requirements

- Python 3.10+
- Node.js & npm (for the frontend)
- Internet connection (for dataset download)
