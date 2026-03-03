import { useCallback, useState } from "react";
import { Eye, ExternalLink } from "lucide-react";
import { api } from "@/lib/api";
import { usePoll } from "@/lib/use-poll";
import { VPNStatus } from "@/components/vpn-status";
import { HealthCard } from "@/components/health-card";
import { QBTStatus } from "@/components/qbt-status";
import { SystemInfo } from "@/components/system-info";
import { SetupWizard } from "@/components/setup-wizard";

const POLL_INTERVAL = 10_000; // 10s

export default function App() {
  const [setupComplete, setSetupComplete] = useState(false);
  const health = usePoll(useCallback(() => api.health(), []), POLL_INTERVAL);
  const vpn = usePoll(useCallback(() => api.vpnStatus(), []), POLL_INTERVAL);
  const qbt = usePoll(useCallback(() => api.qbtStatus(), []), POLL_INTERVAL);
  const system = usePoll(useCallback(() => api.system(), []), 30_000);

  const loading = health.loading || vpn.loading;
  const error = health.error || vpn.error;

  // Setup mode — show wizard instead of dashboard
  const needsSetup = health.data?.setup_required && !setupComplete;
  if (needsSetup) {
    return (
      <SetupWizard
        onComplete={() => {
          setSetupComplete(true);
          // Force reload to pick up new state
          setTimeout(() => window.location.reload(), 1000);
        }}
      />
    );
  }

  return (
    <div className="mx-auto min-h-screen max-w-3xl px-4 py-6">
      {/* Header */}
      <header className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Eye className="h-6 w-6 text-amber-500" />
          <h1 className="text-lg font-bold tracking-wide text-text-primary">
            TunnelVision
          </h1>
          {system.data && (
            <span className="font-mono text-xs text-text-muted">
              v{system.data.version}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {vpn.data && (
            <a
              href={`http://${window.location.hostname}:8080`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 rounded-lg border border-surface-border px-3 py-1.5 text-xs text-text-secondary transition-colors hover:border-amber-500/30 hover:text-amber-400"
            >
              qBit WebUI
              <ExternalLink className="h-3 w-3" />
            </a>
          )}
          <a
            href="/api/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 rounded-lg border border-surface-border px-3 py-1.5 text-xs text-text-secondary transition-colors hover:border-cyan-500/30 hover:text-cyan-400"
          >
            API Docs
            <ExternalLink className="h-3 w-3" />
          </a>
        </div>
      </header>

      {/* Error state */}
      {error && !loading && (
        <div className="mb-4 rounded-xl border border-status-down/30 bg-status-down/10 px-4 py-3 text-sm text-status-down">
          API unreachable: {error}
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div className="flex items-center justify-center py-20">
          <div className="flex items-center gap-3 text-text-muted">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-amber-500/30 border-t-amber-500" />
            <span className="text-sm">Connecting...</span>
          </div>
        </div>
      )}

      {/* Dashboard grid */}
      {!loading && (
        <div className="grid gap-4 sm:grid-cols-2">
          {/* VPN status — full width hero */}
          {vpn.data && (
            <div className="sm:col-span-2">
              <VPNStatus data={vpn.data} />
            </div>
          )}

          {/* Health + qBit side by side */}
          {health.data && <HealthCard data={health.data} />}
          {qbt.data && <QBTStatus data={qbt.data} />}

          {/* System info — full width bottom */}
          {system.data && (
            <div className="sm:col-span-2">
              <SystemInfo data={system.data} />
            </div>
          )}
        </div>
      )}

      {/* Footer */}
      <footer className="mt-6 text-center text-xs text-text-muted">
        See through the tunnel
      </footer>
    </div>
  );
}
