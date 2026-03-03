/** Visibility-aware polling — pauses when tab is hidden. */

import { useState, useEffect, useCallback, useRef } from "react";

export function usePoll<T>(
  fetcher: () => Promise<T>,
  intervalMs: number = 10_000
): { data: T | null; error: string | null; loading: boolean } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const tick = useCallback(async () => {
    try {
      const result = await fetcher();
      setData(result);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fetch failed");
    } finally {
      setLoading(false);
    }
  }, [fetcher]);

  useEffect(() => {
    let active = true;

    const schedule = () => {
      if (!active) return;
      timerRef.current = setTimeout(async () => {
        if (document.visibilityState === "visible") {
          await tick();
        }
        schedule();
      }, intervalMs);
    };

    // Initial fetch
    tick().then(schedule);

    // Fetch immediately when tab becomes visible
    const onVisibility = () => {
      if (document.visibilityState === "visible") tick();
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      active = false;
      clearTimeout(timerRef.current);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [tick, intervalMs]);

  return { data, error, loading };
}
