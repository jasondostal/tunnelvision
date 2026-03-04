import { RefreshCw, Radio } from "lucide-react";
import type { ProviderHealthResponse } from "@/lib/types";

interface Props {
  data: ProviderHealthResponse;
  onRefresh: () => void;
  refreshing?: boolean;
}

export function ProviderHealthCard({ data, onRefresh, refreshing }: Props) {
  const checkedAgo = Math.round(
    (Date.now() - new Date(data.checked_at).getTime()) / 1000
  );

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-5">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <Radio className="h-5 w-5 text-cyan-500" />
          <h2 className="text-sm font-semibold tracking-wide text-text-primary">
            Provider Health
          </h2>
        </div>
        <ReachabilityBadge reachable={data.api_reachable} />
      </div>

      <div className="space-y-3">
        {/* Provider name + latency */}
        <div className="flex items-baseline justify-between">
          <span className="text-sm font-medium text-text-primary">
            {data.provider_name}
          </span>
          {data.api_latency_ms !== null && (
            <span className={`font-mono text-xs ${latencyColor(data.api_latency_ms)}`}>
              {data.api_latency_ms}ms
            </span>
          )}
        </div>

        {/* Server count + cache freshness */}
        <div className="flex items-center gap-4 border-t border-surface-border pt-3">
          <div className="flex-1">
            <div className="text-xs text-text-muted">Servers</div>
            <div className="font-mono text-sm text-text-primary">
              {data.server_count !== null ? data.server_count.toLocaleString() : "—"}
            </div>
          </div>
          <div className="flex-1">
            <div className="text-xs text-text-muted">Cache</div>
            <div className="flex items-center gap-1.5">
              <span className="font-mono text-sm text-text-primary">
                {data.cache_age_seconds !== null
                  ? humanCacheAge(data.cache_age_seconds)
                  : "—"}
              </span>
              {data.cache_fresh !== null && (
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    data.cache_fresh ? "bg-status-up" : "bg-amber-500"
                  }`}
                />
              )}
            </div>
          </div>
          {data.cache_fresh === false && (
            <div className="text-xs text-amber-500">stale</div>
          )}
        </div>

        {/* Account expiry */}
        {data.supports_account_check && (
          <div className="border-t border-surface-border pt-3">
            {data.account.available && data.account.days_remaining !== undefined ? (
              <>
                <div className="mb-1.5 flex items-center justify-between">
                  <span className="text-xs text-text-muted">Account</span>
                  <span className={`font-mono text-xs ${expiryColor(data.account.days_remaining)}`}>
                    {data.account.days_remaining}d remaining
                    {data.account.expires_at && (
                      <span className="ml-2 text-text-muted">
                        · {new Date(data.account.expires_at).toLocaleDateString()}
                      </span>
                    )}
                  </span>
                </div>
                <ExpiryBar days={data.account.days_remaining} />
              </>
            ) : (
              <div className="flex items-center justify-between">
                <span className="text-xs text-text-muted">Account</span>
                <span className="text-xs text-text-muted">
                  {data.account.active === false ? "inactive" : "no data"}
                </span>
              </div>
            )}
          </div>
        )}

        {/* Footer: checked time + refresh */}
        <div className="flex items-center justify-between border-t border-surface-border pt-2.5">
          <span className="text-xs text-text-muted">
            Checked {checkedAgo < 60 ? `${checkedAgo}s` : `${Math.round(checkedAgo / 60)}m`} ago
          </span>
          <button
            onClick={onRefresh}
            disabled={refreshing}
            className="flex items-center gap-1 rounded px-2 py-1 text-xs text-text-muted transition-colors hover:text-cyan-400 disabled:opacity-40"
            title="Refresh"
          >
            <RefreshCw className={`h-3 w-3 ${refreshing ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>
    </div>
  );
}

function ReachabilityBadge({ reachable }: { reachable: boolean | null }) {
  if (reachable === null) {
    return (
      <span className="flex items-center gap-1.5 rounded-full bg-surface-border px-2.5 py-0.5 text-xs text-text-muted">
        <span className="h-1.5 w-1.5 rounded-full bg-text-muted" />
        N/A
      </span>
    );
  }
  return reachable ? (
    <span className="flex items-center gap-1.5 rounded-full bg-status-up/15 px-2.5 py-0.5 text-xs text-status-up">
      <span className="h-1.5 w-1.5 rounded-full bg-status-up" />
      REACHABLE
    </span>
  ) : (
    <span className="flex items-center gap-1.5 rounded-full bg-status-down/15 px-2.5 py-0.5 text-xs text-status-down">
      <span className="h-1.5 w-1.5 rounded-full bg-status-down" />
      UNREACHABLE
    </span>
  );
}

function ExpiryBar({ days }: { days: number }) {
  const max = 365;
  const pct = Math.min(100, Math.round((days / max) * 100));
  const color =
    days > 30 ? "bg-status-up" : days > 7 ? "bg-amber-500" : "bg-status-down";
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-border">
      <div
        className={`h-full rounded-full transition-all ${color}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function latencyColor(ms: number): string {
  if (ms < 100) return "text-status-up";
  if (ms < 500) return "text-amber-500";
  return "text-status-down";
}

function expiryColor(days: number): string {
  if (days > 30) return "text-status-up";
  if (days > 7) return "text-amber-500";
  return "text-status-down";
}

function humanCacheAge(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${Math.round(seconds / 3600)}h`;
}
