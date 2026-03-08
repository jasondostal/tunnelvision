import { useState } from "react";
import {
  Eye,
  Shield,
  Globe,
  MapPin,
  Clock,
  ArrowDownToLine,
  ArrowUpFromLine,
  RotateCw,
  Power,
  Shuffle,
  Loader2,
  Check,
  X,
  AlertCircle,
} from "lucide-react";
import type { VPNStatusResponse } from "@/lib/types";
import { api } from "@/lib/api";
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
  disabled = false,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  onClick: () => Promise<unknown>;
  variant?: "default" | "danger";
  disabled?: boolean;
}) {
  const [loading, setLoading] = useState(false);
  const [feedback, setFeedback] = useState<"success" | "error" | null>(null);

  const handleClick = async () => {
    setLoading(true);
    setFeedback(null);
    try {
      await onClick();
      setFeedback("success");
    } catch {
      setFeedback("error");
    } finally {
      setLoading(false);
      setTimeout(() => setFeedback(null), 2000);
    }
  };

  return (
    <button
      onClick={handleClick}
      disabled={loading || disabled}
      className={cn(
        "flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs transition-colors disabled:opacity-50",
        variant === "danger"
          ? "border-status-down/20 text-status-down hover:bg-status-down/10"
          : "border-surface-border text-text-secondary hover:border-amber-500/30 hover:text-amber-400"
      )}
    >
      {loading ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      ) : feedback === "success" ? (
        <Check className="h-3.5 w-3.5 text-status-up" />
      ) : feedback === "error" ? (
        <X className="h-3.5 w-3.5 text-status-down" />
      ) : (
        <Icon className="h-3.5 w-3.5" />
      )}
      {label}
    </button>
  );
}

function formatProvider(id: string): string {
  const names: Record<string, string> = {
    pia: "PIA",
    ivpn: "IVPN",
    nordvpn: "NordVPN",
    expressvpn: "ExpressVPN",
    airvpn: "AirVPN",
    cyberghost: "CyberGhost",
    hidemyass: "HideMyAss",
    purevpn: "PureVPN",
    vpnsecure: "VPNSecure",
    vpnunlimited: "VPN Unlimited",
    vyprvpn: "VyprVPN",
    surfshark: "Surfshark",
    windscribe: "Windscribe",
    torguard: "TorGuard",
    perfectprivacy: "Perfect Privacy",
    privatevpn: "PrivateVPN",
    ipvanish: "IPVanish",
    fastestvpn: "FastestVPN",
    slickvpn: "SlickVPN",
    giganews: "Giganews",
    proton: "Proton VPN",
    mullvad: "Mullvad",
    privado: "Privado",
  };
  return names[id] || id.charAt(0).toUpperCase() + id.slice(1);
}

export function VPNStatus({ data }: { data: VPNStatusResponse }) {
  const [busy, setBusy] = useState(false);
  // Optimistic location override — set from ConnectResponse before poll catches up
  const [pendingLocation, setPendingLocation] = useState<string | null>(null);
  // Error message — shown inline below controls, auto-dismissed after 8s
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Clear optimistic override when poll data changes (real data arrived)
  const locationKey = data.location;
  const prevLocation = useState(locationKey)[0];
  if (locationKey !== prevLocation && pendingLocation) {
    setPendingLocation(null);
  }

  const uptime = data.connected_since
    ? humanDuration(
        (Date.now() - new Date(data.connected_since).getTime()) / 1000
      )
    : "—";

  const wrapAction = <T,>(fn: () => Promise<T>): (() => Promise<T>) => {
    return async () => {
      setBusy(true);
      setErrorMessage(null);
      try {
        return await fn();
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Operation failed";
        setErrorMessage(msg);
        setTimeout(() => setErrorMessage(null), 8000);
        throw e;
      } finally {
        setBusy(false);
      }
    };
  };

  const displayLocation = pendingLocation || data.location;

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
      {displayLocation && (
        <div className={cn(
          "mb-4 rounded-lg bg-amber-500/8 border border-amber-500/15 px-4 py-3 transition-opacity duration-300",
          busy && "opacity-60",
        )}>
          <div className="flex items-center gap-2">
            <MapPin className="h-4 w-4 text-amber-400" />
            <span className="text-lg font-medium text-amber-200">
              {busy ? "Connecting…" : displayLocation}
            </span>
          </div>
          <div className="mt-1 font-mono text-sm text-amber-400/70">
            {busy ? "—" : data.public_ip}
          </div>
        </div>
      )}

      {/* Stats grid */}
      <div className="mb-4 grid grid-cols-2 gap-x-6 gap-y-3">
        {!displayLocation && (
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
          <Stat icon={Globe} label="Provider" value={formatProvider(data.provider)} />
        )}
      </div>

      {/* Controls */}
      <div className="flex flex-wrap gap-2 border-t border-surface-border pt-3">
        <ActionButton
          icon={RotateCw}
          label="Restart VPN"
          onClick={wrapAction(() => api.restart())}
          disabled={busy}
        />
        <ActionButton
          icon={Shuffle}
          label="Rotate Server"
          onClick={wrapAction(async () => {
            const r = await api.rotate();
            if (r.city && r.country) {
              setPendingLocation(`${r.city}, ${r.country}`);
            }
            return r;
          })}
          disabled={busy}
        />
        {data.state === "up" && (
          <ActionButton
            icon={Power}
            label="Disconnect"
            onClick={wrapAction(() => api.disconnect())}
            variant="danger"
            disabled={busy}
          />
        )}
        {data.state === "down" && (
          <ActionButton
            icon={Power}
            label="Reconnect"
            onClick={wrapAction(() => api.reconnectVpn())}
            disabled={busy}
          />
        )}
      </div>

      {/* Error message — shown on action failure */}
      {errorMessage && (
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-status-down/20 bg-status-down/5 px-3 py-2">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-status-down" />
          <span className="text-xs text-status-down">{errorMessage}</span>
          <button
            onClick={() => setErrorMessage(null)}
            className="ml-auto shrink-0 text-status-down/60 hover:text-status-down"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      )}
    </div>
  );
}
