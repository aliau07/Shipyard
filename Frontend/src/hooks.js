import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from './api';

export const PAGE_SIZE = 20;

export function useApi(path) {
  const [state, setState] = useState({ data: null, error: null, loading: Boolean(path) });
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (!path) return undefined;
    let cancelled = false;
    setState(previous => ({ ...previous, loading: true, error: null }));
    apiFetch(path)
      .then(data => { if (!cancelled) setState({ data, error: null, loading: false }); })
      .catch(error => { if (!cancelled) setState({ data: null, error, loading: false }); });
    return () => { cancelled = true; };
  }, [path, version]);

  const reload = useCallback(() => setVersion(v => v + 1), []);
  return { ...state, reload };
}

export function usePaginatedList(path) {
  const [pageState, setPageState] = useState({ path, page: 1 });
  const page = pageState.path === path ? pageState.page : 1;
  const setPage = useCallback(next => setPageState({ path, page: next }), [path]);

  const separator = path.includes('?') ? '&' : '?';
  const result = useApi(`${path}${separator}page=${page}`);
  return {
    ...result,
    rows: result.data?.results ?? [],
    count: result.data?.count ?? 0,
    page,
    setPage,
  };
}

export function buildQuery(params) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, value]) => value !== '' && value !== null && value !== undefined && value !== false),
  ).toString();
  return query ? `?${query}` : '';
}

export function useDebouncedValue(value, delay = 300) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export function usePolling(callback, interval = 30000) {
  useEffect(() => {
    callback();
    const timer = setInterval(() => {
      if (document.visibilityState !== 'hidden') callback();
    }, interval);
    return () => clearInterval(timer);
  }, [callback, interval]);
}
