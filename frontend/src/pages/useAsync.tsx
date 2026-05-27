import { useEffect, useState } from 'react';

export function useAsync<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    load()
      .then((next) => {
        if (!cancelled) {
          setData(next);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Request failed');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, deps);

  return { data, error, loading };
}

export function StateBlock({ loading, error, empty }: { loading: boolean; error: string | null; empty?: boolean }) {
  if (loading) return <div className="state-block">Loading</div>;
  if (error) return <div className="state-block error">{error}</div>;
  if (empty) return <div className="state-block">No records found</div>;
  return null;
}

