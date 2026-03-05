/** Subscribe to TunnelVision SSE stream — calls onEvent on every state change. */

import { useEffect, useRef } from "react";

// All event types that should trigger a UI refresh
const SSE_REFRESH_EVENTS = [
  "vpn_status",
  "vpn_state",
  "watchdog_recovered",
  "watchdog_reconnecting",
  "watchdog_failover",
  "watchdog_degraded",
  "watchdog_cooldown",
];

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

      for (const event of SSE_REFRESH_EVENTS) {
        es.addEventListener(event, () => {
          onEventRef.current();
        });
      }

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
