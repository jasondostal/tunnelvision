import { Cpu, Clock } from "lucide-react";
import type { SystemResponse } from "@/lib/types";
import { humanDuration } from "@/lib/utils";

export function SystemInfo({ data }: { data: SystemResponse }) {
  const rows = [
    { label: "Container", value: humanDuration(data.container_uptime) },
    {
      label: "VPN",
      value: data.vpn_uptime ? humanDuration(data.vpn_uptime) : "—",
    },
  ];

  const versions = [
    data.alpine_version && { label: "Alpine", value: data.alpine_version },
    data.qbittorrent_version && {
      label: "qBittorrent",
      value: data.qbittorrent_version,
    },
    data.wireguard_version && {
      label: "WireGuard",
      value: data.wireguard_version,
    },
    { label: "API", value: `v${data.version}` },
    data.python_version && { label: "Python", value: data.python_version },
  ].filter(Boolean) as { label: string; value: string }[];

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-5">
      <div className="mb-4 flex items-center gap-2.5">
        <Cpu className="h-5 w-5 text-text-muted" />
        <h2 className="text-sm font-semibold tracking-wide text-text-primary">
          System
        </h2>
      </div>

      {/* Uptimes */}
      <div className="mb-3 space-y-2">
        {rows.map((r) => (
          <div key={r.label} className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Clock className="h-3.5 w-3.5 text-text-muted" />
              <span className="text-xs text-text-muted">{r.label} uptime</span>
            </div>
            <span className="font-mono text-sm text-text-secondary">
              {r.value}
            </span>
          </div>
        ))}
      </div>

      {/* Versions */}
      <div className="space-y-1.5 border-t border-surface-border pt-3">
        {versions.map((v) => (
          <div key={v.label} className="flex items-center justify-between">
            <span className="text-xs text-text-muted">{v.label}</span>
            <span className="font-mono text-xs text-text-secondary">
              {v.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
