/** Subscribe to TunnelVision SSE stream — calls onEvent on every state change. */

import { useEffect, useRef } from "react";

export function useSSE(onEvent: () => void) {
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    let es: EventSource | null = null;
    let retryTimeout: ReturnType<typeof setTimeout>;
    let retryDelay = 2000;

    function connect() {
      es = new EventSource("/api/v1/events");

      es.onopen = () => {
        retryDelay = 2000; // Reset on successful connect
      };

      es.addEventListener("vpn_status", () => {
        onEventRef.current();
      });

      es.addEventListener("vpn_state", () => {
        onEventRef.current();
      });

      es.onerror = () => {
        es?.close();
        // Reconnect with backoff
        retryTimeout = setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 30000);
      };
    }

    connect();

    return () => {
      es?.close();
      clearTimeout(retryTimeout);
    };
  }, []);
}
