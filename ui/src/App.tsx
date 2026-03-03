import { useCallback, useEffect, useState } from "react";
import { ExternalLink, LogOut, Settings } from "lucide-react";
import { Logo } from "@/components/logo";
import { api } from "@/lib/api";
import type { AuthResponse } from "@/lib/api";
import { usePoll } from "@/lib/use-poll";
import { VPNStatus } from "@/components/vpn-status";
import { HealthCard } from "@/components/health-card";
import { QBTStatus } from "@/components/qbt-status";
import { SystemInfo } from "@/components/system-info";
import { SetupWizard } from "@/components/setup-wizard";
import { Login } from "@/components/login";
import { SettingsPanel } from "@/components/settings-panel";

const POLL_INTERVAL = 10_000; // 10s

export default function App() {
  const [authState, setAuthState] = useState<AuthResponse | null>(null);
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    api.checkAuth().then((r) => {
      setAuthState(r);
      setAuthChecked(true);
    });
  }, []);

  if (!authChecked) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-amber-500/30 border-t-amber-500" />
      </div>
    );
  }

  if (authState?.login_required && !authState?.authenticated) {
    return <Login onSuccess={() => api.checkAuth().then(setAuthState)} />;
  }

  return <Dashboard authState={authState} />;
}

function Dashboard({ authState }: { authState: AuthResponse | null }) {
  const [setupComplete, setSetupComplete] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
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
          <Logo className="h-6 w-6" />
          <h1 className="text-lg font-bold tracking-wide text-text-primary">
            TunnelVision
          </h1>
          {system.data && (
            <span className="font-mono text-xs text-text-muted">
              v{system.data.version}
            </span>
          )}
          {vpn.data && (
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium tracking-wide ${
              vpn.data.provider === "gluetun"
                ? "bg-cyan-500/15 text-cyan-400"
                : "bg-amber-500/15 text-amber-400"
            }`}>
              {vpn.data.provider === "gluetun" ? "SIDECAR" : "STANDALONE"}
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
          <button
            onClick={() => setShowSettings(true)}
            className="flex items-center gap-1.5 rounded-lg border border-surface-border px-3 py-1.5 text-xs text-text-secondary transition-colors hover:border-amber-500/30 hover:text-amber-400"
            title="Settings"
          >
            <Settings className="h-3 w-3" />
          </button>
          {authState?.login_required && (
            <button
              onClick={() => api.logout().then(() => window.location.reload())}
              className="flex items-center gap-1.5 rounded-lg border border-surface-border px-3 py-1.5 text-xs text-text-secondary transition-colors hover:border-status-down/30 hover:text-status-down"
              title="Sign out"
            >
              <LogOut className="h-3 w-3" />
            </button>
          )}
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
          {vpn.data && (
            <div className="sm:col-span-2">
              <VPNStatus data={vpn.data} />
            </div>
          )}

          {health.data && <HealthCard data={health.data} />}
          {qbt.data && <QBTStatus data={qbt.data} />}

          {system.data && (
            <div className="sm:col-span-2">
              <SystemInfo data={system.data} />
            </div>
          )}
        </div>
      )}

      <footer className="mt-6 text-center text-xs text-text-muted">
        See through the tunnel
      </footer>

      {showSettings && (
        <SettingsPanel onClose={() => setShowSettings(false)} />
      )}
    </div>
  );
}
