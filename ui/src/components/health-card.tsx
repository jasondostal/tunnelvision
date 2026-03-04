import { HeartPulse } from "lucide-react";
import type { HealthResponse } from "@/lib/types";
import { humanDuration } from "@/lib/utils";
import { StatusBadge } from "./status-badge";

export function HealthCard({ data }: { data: HealthResponse }) {
  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-5">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <HeartPulse className="h-5 w-5 text-red-500" />
          <h2 className="text-sm font-semibold tracking-wide text-text-primary">
            Health
          </h2>
        </div>
        <StatusBadge value={data.healthy ? "healthy" : "unhealthy"} />
      </div>

      <div className="space-y-2.5">
        <Row label="VPN" value={data.vpn} />
        <Row label="Killswitch" value={data.killswitch} />
        {data.qbittorrent !== "disabled" && (
          <Row label="qBittorrent" value={data.qbittorrent} />
        )}
        <Row label="API" value={data.api} />
        <div className="flex items-center justify-between border-t border-surface-border pt-2.5">
          <span className="text-xs text-text-muted">Uptime</span>
          <span className="font-mono text-sm text-text-secondary">
            {humanDuration(data.uptime_seconds)}
          </span>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-text-muted">{label}</span>
      <StatusBadge value={value} />
    </div>
  );
}
