import {
  Shield,
  Globe,
  MapPin,
  Clock,
  ArrowDownToLine,
  ArrowUpFromLine,
  Eye,
} from "lucide-react";
import type { VPNStatusResponse } from "@/lib/types";
import { humanBytes, humanDuration } from "@/lib/utils";
import { StatusBadge } from "./status-badge";

function Stat({
  icon: Icon,
  label,
  value,
  mono = false,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-start gap-3">
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-text-muted" />
      <div className="min-w-0">
        <div className="text-xs text-text-muted">{label}</div>
        <div
          className={`text-sm text-text-primary truncate ${mono ? "font-mono" : ""}`}
        >
          {value || "—"}
        </div>
      </div>
    </div>
  );
}

export function VPNStatus({ data }: { data: VPNStatusResponse }) {
  const uptime = data.connected_since
    ? humanDuration(
        (Date.now() - new Date(data.connected_since).getTime()) / 1000
      )
    : "—";

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-5">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <Eye className="h-5 w-5 text-amber-500" />
          <h2 className="text-sm font-semibold tracking-wide text-text-primary">
            VPN Status
          </h2>
        </div>
        <StatusBadge value={data.state} />
      </div>

      {/* Location hero — the thing you glance at */}
      {data.location && (
        <div className="mb-4 rounded-lg bg-amber-500/8 border border-amber-500/15 px-4 py-3">
          <div className="flex items-center gap-2">
            <MapPin className="h-4 w-4 text-amber-400" />
            <span className="text-lg font-medium text-amber-200">
              {data.location}
            </span>
          </div>
          <div className="mt-1 font-mono text-sm text-amber-400/70">
            {data.public_ip}
          </div>
        </div>
      )}

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-x-6 gap-y-3">
        {!data.location && (
          <Stat icon={Globe} label="Public IP" value={data.public_ip} mono />
        )}
        <Stat icon={Shield} label="Killswitch" value={data.killswitch} />
        <Stat icon={Clock} label="Connected" value={uptime} />
        <Stat
          icon={ArrowDownToLine}
          label="Downloaded"
          value={humanBytes(data.transfer_rx)}
          mono
        />
        <Stat
          icon={ArrowUpFromLine}
          label="Uploaded"
          value={humanBytes(data.transfer_tx)}
          mono
        />
        {data.provider !== "custom" && (
          <Stat icon={Globe} label="Provider" value={data.provider} />
        )}
      </div>
    </div>
  );
}
