import { useState, useRef, useEffect, useCallback } from "react";
import { useSuggestions } from "../hooks/useSuggestions";
import "./SearchBox.css";

/**
 * Autocomplete search box with keyboard navigation and dropdown suggestions.
 *
 * Props:
 *   onSubmit(query: string) — called when the user submits a search
 */
export default function SearchBox({ onSubmit }) {
  const [query, setQuery] = useState("");
  const [highlightIndex, setHighlightIndex] = useState(-1);
  const [isOpen, setIsOpen] = useState(false);

  const { suggestions, isLoading, error } = useSuggestions(query);
  const inputRef = useRef(null);
  const listRef = useRef(null);

  // Open dropdown whenever we have something to show
  const hasContent =
    isLoading || error || (suggestions.length > 0) || (query.trim() && suggestions.length === 0 && !isLoading && !error);

  useEffect(() => {
    setIsOpen(hasContent && query.trim().length > 0);
    setHighlightIndex(-1);
  }, [suggestions, isLoading, error, query, hasContent]);

  // Scroll highlighted item into view
  useEffect(() => {
    if (highlightIndex < 0 || !listRef.current) return;
    const items = listRef.current.querySelectorAll("[data-suggestion-item]");
    if (items[highlightIndex]) {
      items[highlightIndex].scrollIntoView({ block: "nearest" });
    }
  }, [highlightIndex]);

  const submitQuery = useCallback(
    (text) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      setIsOpen(false);
      setHighlightIndex(-1);
      if (onSubmit) onSubmit(trimmed);
    },
    [onSubmit]
  );

  const selectSuggestion = useCallback(
    (suggestion) => {
      setQuery(suggestion.query);
      setIsOpen(false);
      setHighlightIndex(-1);
      inputRef.current?.focus();
    },
    []
  );

  const handleKeyDown = (e) => {
    if (!isOpen) return;

    const maxIndex = suggestions.length - 1;

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setHighlightIndex((prev) =>
          prev < maxIndex ? prev + 1 : 0
        );
        break;
      case "ArrowUp":
        e.preventDefault();
        setHighlightIndex((prev) =>
          prev > 0 ? prev - 1 : maxIndex
        );
        break;
      case "Enter":
        e.preventDefault();
        if (highlightIndex >= 0 && suggestions[highlightIndex]) {
          selectSuggestion(suggestions[highlightIndex]);
        } else {
          submitQuery(query);
        }
        break;
      case "Escape":
        setIsOpen(false);
        setHighlightIndex(-1);
        break;
      default:
        break;
    }
  };

  const handleInputChange = (e) => {
    setQuery(e.target.value);
  };

  const handleFormSubmit = (e) => {
    e.preventDefault();
    if (highlightIndex >= 0 && suggestions[highlightIndex]) {
      selectSuggestion(suggestions[highlightIndex]);
    } else {
      submitQuery(query);
    }
  };

  // Close dropdown when clicking outside
  const containerRef = useRef(null);
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Determine what to show in the dropdown body
  const showNoMatches =
    !isLoading && !error && query.trim() && suggestions.length === 0;

  return (
    <div className="search-container" ref={containerRef}>
      <form className="search-form" onSubmit={handleFormSubmit} role="search">
        <div className="search-input-wrapper">
          <svg
            className="search-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            ref={inputRef}
            id="search-input"
            className="search-input"
            type="text"
            value={query}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            onFocus={() => hasContent && query.trim() && setIsOpen(true)}
            placeholder="Search Wikipedia topics…"
            autoComplete="off"
            autoCorrect="off"
            spellCheck="false"
            role="combobox"
            aria-expanded={isOpen}
            aria-controls="suggestions-list"
            aria-activedescendant={
              highlightIndex >= 0
                ? `suggestion-${highlightIndex}`
                : undefined
            }
          />
          {isLoading && (
            <div className="search-spinner" aria-label="Loading suggestions">
              <div className="spinner" />
            </div>
          )}
        </div>
      </form>

      {isOpen && (
        <ul
          id="suggestions-list"
          className="suggestions-dropdown"
          ref={listRef}
          role="listbox"
        >
          {error && (
            <li className="suggestion-status suggestion-error" role="option" aria-selected="false">
              <svg className="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              {error}
            </li>
          )}

          {showNoMatches && (
            <li className="suggestion-status suggestion-empty" role="option" aria-selected="false">
              No matches found
            </li>
          )}

          {suggestions.map((s, i) => (
            <li
              key={s.query}
              id={`suggestion-${i}`}
              className={`suggestion-item${
                i === highlightIndex ? " suggestion-item--highlighted" : ""
              }`}
              role="option"
              aria-selected={i === highlightIndex}
              data-suggestion-item
              onMouseEnter={() => setHighlightIndex(i)}
              onMouseDown={(e) => {
                e.preventDefault(); // prevent blur before click fires
                selectSuggestion(s);
              }}
            >
              <span className="suggestion-query">{s.query}</span>
              <span className="suggestion-count">
                {s.count.toLocaleString()} views
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
