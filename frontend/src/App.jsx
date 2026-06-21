import { useState, useCallback, useEffect } from "react";
import SearchBox from "./components/SearchBox";
import { API_BASE_URL } from "./config";
import "./App.css";

function App() {
  const [toast, setToast] = useState(null); // { type: "success" | "error", text: string }
  const [trending, setTrending] = useState([]);

  // Fetch trending searches on mount
  const fetchTrending = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/trending?limit=10`);
      if (res.ok) {
        const data = await res.json();
        setTrending(data.suggestions || []);
      }
    } catch (err) {
      console.error("Failed to fetch trending:", err);
    }
  }, []);

  useEffect(() => {
    fetchTrending();
  }, [fetchTrending]);

  const handleSubmit = useCallback(async (query) => {
    setToast(null);
    try {
      const res = await fetch(`${API_BASE_URL}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });
      if (!res.ok) throw new Error(`Server error (${res.status})`);
      const data = await res.json();
      setToast({ type: "success", text: data.message || "Searched" });
    } catch {
      setToast({ type: "error", text: "Couldn't submit search" });
    }

    // Auto-dismiss toast after 2.5 seconds
    setTimeout(() => setToast(null), 2500);

    // Refresh trending searches to reflect the new search
    fetchTrending();
  }, [fetchTrending]);

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-logo" aria-hidden="true">⚡</div>
        <h1 className="app-title">Type-Ahead Search</h1>
        <p className="app-subtitle">
          Instant suggestions powered by Wikipedia pageview data
        </p>
      </header>

      <main className="app-search">
        <SearchBox onSubmit={handleSubmit} />

        {toast && (
          <div
            className={`toast toast--${toast.type}`}
            role="status"
            aria-live="polite"
          >
            {toast.type === "success" ? (
              <svg className="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            ) : (
              <svg className="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
            )}
            {toast.text}
          </div>
        )}

        {trending.length > 0 && (
          <div className="trending-section">
            <h2 className="trending-title">Trending searches</h2>
            <div className="trending-list">
              {trending.map((item, index) => (
                <button
                  key={index}
                  className="trending-item"
                  onClick={() => handleSubmit(item.query)}
                >
                  <svg className="trending-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                    <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
                    <polyline points="17 6 23 6 23 12" />
                  </svg>
                  {item.query}
                </button>
              ))}
            </div>
          </div>
        )}
      </main>

      <div className="app-hint">
        <kbd className="kbd">↑</kbd>
        <kbd className="kbd">↓</kbd>
        to navigate
        <kbd className="kbd">↵</kbd>
        to search
        <kbd className="kbd">esc</kbd>
        to close
      </div>
    </div>
  );
}

export default App;
