import { useState, useEffect } from "react";
import { API_BASE_URL } from "../config";
import { useDebounce } from "./useDebounce";

/**
 * Fetch autocomplete suggestions for `query` from the backend.
 *
 * Returns { suggestions, isLoading, error }
 * - suggestions: array of { query, count } objects (max 10)
 * - isLoading: true while fetching
 * - error: string message on failure, null otherwise
 *
 * The API call is debounced by 300ms.
 */
export function useSuggestions(query) {
  const debouncedQuery = useDebounce(query, 300);
  const [suggestions, setSuggestions] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    const trimmed = debouncedQuery.trim();

    // Empty query → clear immediately, no fetch
    if (!trimmed) {
      setSuggestions([]);
      setIsLoading(false);
      setError(null);
      return;
    }

    const controller = new AbortController();
    setIsLoading(true);
    setError(null);

    const url = `${API_BASE_URL}/suggest?q=${encodeURIComponent(trimmed)}`;

    fetch(url, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error(`Server error (${res.status})`);
        return res.json();
      })
      .then((data) => {
        setSuggestions(data.suggestions || []);
        setIsLoading(false);
      })
      .catch((err) => {
        if (err.name === "AbortError") return; // cancelled — ignore
        setError("Couldn't load suggestions");
        setSuggestions([]);
        setIsLoading(false);
      });

    return () => controller.abort();
  }, [debouncedQuery]);

  return { suggestions, isLoading, error };
}
