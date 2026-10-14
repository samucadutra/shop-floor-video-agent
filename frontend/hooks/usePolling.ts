"use client";

import { useEffect, useRef } from "react";

/**
 * Call `fn` every `intervalMs` while `enabled`. The next call waits for the previous one to
 * finish. Stops when `enabled` turns false and on unmount.
 */
export function usePolling(
  fn: () => Promise<unknown> | void,
  { intervalMs = 3000, enabled }: { intervalMs?: number; enabled: boolean },
): void {
  const fnRef = useRef(fn);

  useEffect(() => {
    fnRef.current = fn;
  }, [fn]);

  useEffect(() => {
    if (!enabled) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;

    const tick = async () => {
      try {
        await fnRef.current();
      } finally {
        if (!stopped) timer = setTimeout(tick, intervalMs);
      }
    };
    timer = setTimeout(tick, intervalMs);

    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [enabled, intervalMs]);
}
