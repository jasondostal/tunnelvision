import { useState } from "react";
import {
  Shield,
  Globe,
  MapPin,
  Clock,
  ArrowDownToLine,
  ArrowUpFromLine,
  Eye,
  RotateCw,
  Power,
  Shuffle,
  Loader2,
} from "lucide-react";
import type { VPNStatusResponse } from "@/lib/types";
import { humanBytes, humanDuration, cn } from "@/lib/utils";
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

function ActionButton({
  icon: Icon,
  label,
  onClick,
  variant = "default",
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  onClick: () => void;
  variant?: "default" | "danger";
}) {
  const [loading, setLoading] = useState(false);

  const handleClick = async () => {
    setLoading(true);
    try {
      await onClick();
    } finally {
      setTimeout(() => setLoading(false), 1500);
    }
  };

  return (
    <button
      onClick={handleClick}
      disabled={loading}
      className={cn(
        "flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs transition-colors disabled:opacity-50",
        variant === "danger"
          ? "border-status-down/20 text-status-down hover:bg-status-down/10"
          : "border-surface-border text-text-secondary hover:border-amber-500/30 hover:text-amber-400"
      )}
    >
      {loading ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      ) : (
        <Icon className="h-3.5 w-3.5" />
      )}
      {label}
    </button>
  );
}

async function apiPost(path: string) {
  await fetch(path, { method: "POST" });
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
      <div className="mb-4 grid grid-cols-2 gap-x-6 gap-y-3">
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

      {/* Controls */}
      <div className="flex flex-wrap gap-2 border-t border-surface-border pt-3">
        <ActionButton
          icon={RotateCw}
          label="Restart VPN"
          onClick={() => apiPost("/api/v1/vpn/restart")}
        />
        <ActionButton
          icon={Shuffle}
          label="Rotate Server"
          onClick={() => apiPost("/api/v1/vpn/rotate")}
        />
        {data.state === "up" && (
          <ActionButton
            icon={Power}
            label="Disconnect"
            onClick={() => apiPost("/api/v1/vpn/disconnect")}
            variant="danger"
          />
        )}
        {data.state === "down" && (
          <ActionButton
            icon={Power}
            label="Reconnect"
            onClick={() => apiPost("/api/v1/vpn/reconnect")}
          />
        )}
      </div>
    </div>
  );
}
