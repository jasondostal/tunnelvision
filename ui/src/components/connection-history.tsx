import { useState } from "react";
import { History, ChevronDown, ChevronUp } from "lucide-react";
import type { HistoryResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

const EVENT_COLORS: Record<string, string> = {
  reconnect: "bg-status-up/15 text-status-up border-status-up/30",
  watchdog_recovered: "bg-status-up/15 text-status-up border-status-up/30",
  reconnect_failed: "bg-status-down/15 text-status-down border-status-down/30",
  watchdog_failover: "bg-status-down/15 text-status-down border-status-down/30",
  watchdog_cooldown: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  watchdog_reconnect_attempt: "bg-amber-500/15 text-amber-400 border-amber-500/30",
};

const DEFAULT_COLOR = "bg-status-disabled/15 text-status-disabled border-status-disabled/30";

function relativeTime(ts: string): string {
  const diff = (Date.now() - new Date(ts).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function EventBadge({ event }: { event: string }) {
  const style = EVENT_COLORS[event] ?? DEFAULT_COLOR;
  const label = event.replace(/_/g, " ");
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center rounded-md border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide",
        style,
      )}
    >
      {label}
    </span>
  );
}

function DetailChips({ entry }: { entry: Record<string, unknown> }) {
  const skip = new Set(["event", "timestamp"]);
  const details = Object.entries(entry).filter(([k]) => !skip.has(k));
  if (!details.length) return null;
  return (
    <span className="flex flex-wrap gap-1">
      {details.map(([k, v]) => (
        <span
          key={k}
          className="rounded bg-surface-bg px-1.5 py-0.5 font-mono text-[10px] text-text-muted"
        >
          {k}={String(v)}
        </span>
      ))}
    </span>
  );
}

const COLLAPSED_COUNT = 10;

export function ConnectionHistory({ data }: { data: HistoryResponse }) {
  const [expanded, setExpanded] = useState(false);

  if (!data.history.length) {
    return (
      <div className="rounded-xl border border-surface-border bg-surface-card p-5">
        <div className="flex items-center gap-2.5">
          <History className="h-5 w-5 text-cyan-500" />
          <h2 className="text-sm font-semibold tracking-wide text-text-primary">
            History
          </h2>
        </div>
        <p className="mt-3 text-xs text-text-muted">No events recorded yet.</p>
      </div>
    );
  }

  const visible = expanded
    ? data.history
    : data.history.slice(0, COLLAPSED_COUNT);
  const hasMore = data.history.length > COLLAPSED_COUNT;

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-5">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <History className="h-5 w-5 text-cyan-500" />
          <h2 className="text-sm font-semibold tracking-wide text-text-primary">
            History
          </h2>
        </div>
        <span className="font-mono text-xs text-text-muted">
          {data.history.length} events
        </span>
      </div>

      <div className="space-y-2">
        {visible.map((entry, i) => (
          <div
            key={`${entry.timestamp}-${i}`}
            className="flex items-start gap-3 rounded-lg border border-surface-border bg-surface-bg/50 px-3 py-2"
          >
            <EventBadge event={entry.event} />
            <div className="min-w-0 flex-1 space-y-0.5">
              <DetailChips entry={entry} />
            </div>
            <span className="shrink-0 text-[10px] text-text-muted">
              {relativeTime(entry.timestamp)}
            </span>
          </div>
        ))}
      </div>

      {hasMore && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-3 flex w-full items-center justify-center gap-1 text-xs text-text-muted transition-colors hover:text-text-secondary"
        >
          {expanded ? (
            <>
              Show less <ChevronUp className="h-3 w-3" />
            </>
          ) : (
            <>
              Show {data.history.length - COLLAPSED_COUNT} more{" "}
              <ChevronDown className="h-3 w-3" />
            </>
          )}
        </button>
      )}
    </div>
  );
}
