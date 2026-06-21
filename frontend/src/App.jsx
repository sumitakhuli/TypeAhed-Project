import SearchBox from "./components/SearchBox";
import "./App.css";

function App() {
  /**
   * Stub: log the submitted query for now.
   * Will be wired to a real search/results endpoint later.
   */
  const handleSubmit = (query) => {
    console.log("Search submitted:", query);
  };

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
      </main>

      <div className="app-hint">
        <kbd className="kbd">↑</kbd>
        <kbd className="kbd">↓</kbd>
        to navigate
        <kbd className="kbd">↵</kbd>
        to select
        <kbd className="kbd">esc</kbd>
        to close
      </div>
    </div>
  );
}

export default App;
