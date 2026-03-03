import { useState, useCallback } from "react";
import {
  Eye,
  Shield,
  ChevronRight,
  Check,
  Loader2,
  AlertCircle,
  MapPin,
  FileText,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface Provider {
  id: string;
  name: string;
  description: string;
  setup_type: string;
  logo?: string;
}

interface VerifyResult {
  success: boolean;
  public_ip: string;
  country: string;
  city: string;
  error: string;
}

type Step = "welcome" | "provider" | "config" | "verify" | "done";

export function SetupWizard({ onComplete }: { onComplete: () => void }) {
  const [step, setStep] = useState<Step>("welcome");
  const [providers, setProviders] = useState<Provider[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>("");
  const [configText, setConfigText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [verifyResult, setVerifyResult] = useState<VerifyResult | null>(null);

  const loadProviders = useCallback(async () => {
    const resp = await fetch("/api/v1/setup/providers");
    const data = await resp.json();
    setProviders(data.providers);
    setStep("provider");
  }, []);

  const selectProvider = useCallback(async (id: string) => {
    setSelectedProvider(id);
    setError("");
    await fetch("/api/v1/setup/provider", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: id }),
    });
    setStep("config");
  }, []);

  const submitConfig = useCallback(async () => {
    if (!configText.trim()) {
      setError("Paste your WireGuard configuration");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const resp = await fetch("/api/v1/setup/wireguard", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ config: configText }),
      });
      const data = await resp.json();
      if (!data.success) {
        setError(data.error);
        return;
      }
      setStep("verify");
      // Auto-verify
      await doVerify();
    } finally {
      setLoading(false);
    }
  }, [configText]);

  const doVerify = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const resp = await fetch("/api/v1/setup/verify", { method: "POST" });
      const data: VerifyResult = await resp.json();
      setVerifyResult(data);
      if (!data.success) {
        setError(data.error);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const completeSetup = useCallback(async () => {
    setLoading(true);
    try {
      await fetch("/api/v1/setup/complete", { method: "POST" });
      setStep("done");
      setTimeout(onComplete, 2000);
    } finally {
      setLoading(false);
    }
  }, [onComplete]);

  return (
    <div className="mx-auto min-h-screen max-w-xl px-4 py-12">
      {/* Progress */}
      <div className="mb-8 flex items-center justify-center gap-2">
        {(["welcome", "provider", "config", "verify", "done"] as Step[]).map(
          (s, i) => (
            <div key={s} className="flex items-center gap-2">
              <div
                className={cn(
                  "h-2 w-2 rounded-full transition-colors",
                  step === s
                    ? "bg-amber-500"
                    : (["welcome", "provider", "config", "verify", "done"].indexOf(step) > i)
                      ? "bg-amber-500/50"
                      : "bg-surface-border"
                )}
              />
              {i < 4 && (
                <div className="h-px w-6 bg-surface-border" />
              )}
            </div>
          )
        )}
      </div>

      {/* Welcome */}
      {step === "welcome" && (
        <div className="text-center">
          <Eye className="mx-auto mb-6 h-16 w-16 text-amber-500" />
          <h1 className="mb-3 text-2xl font-bold text-text-primary">
            Welcome to TunnelVision
          </h1>
          <p className="mb-8 text-text-secondary">
            Let's set up your VPN tunnel. This takes about a minute.
          </p>
          <button
            onClick={loadProviders}
            className="inline-flex items-center gap-2 rounded-xl bg-amber-500 px-6 py-3 font-medium text-black transition-colors hover:bg-amber-400"
          >
            Get Started
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Provider Selection */}
      {step === "provider" && (
        <div>
          <h2 className="mb-2 text-xl font-bold text-text-primary">
            Choose your VPN provider
          </h2>
          <p className="mb-6 text-sm text-text-secondary">
            TunnelVision works with any WireGuard-compatible VPN.
          </p>
          <div className="grid gap-3">
            {providers.map((p) => (
              <button
                key={p.id}
                onClick={() => selectProvider(p.id)}
                className="flex items-start gap-4 rounded-xl border border-surface-border bg-surface-card p-4 text-left transition-colors hover:border-amber-500/30 hover:bg-surface-card-hover"
              >
                <Shield className="mt-0.5 h-5 w-5 shrink-0 text-amber-500" />
                <div>
                  <div className="font-medium text-text-primary">{p.name}</div>
                  <div className="mt-0.5 text-sm text-text-secondary">
                    {p.description}
                  </div>
                </div>
                <ChevronRight className="ml-auto mt-0.5 h-4 w-4 shrink-0 text-text-muted" />
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Config Input */}
      {step === "config" && (
        <div>
          <h2 className="mb-2 text-xl font-bold text-text-primary">
            Paste your WireGuard config
          </h2>
          <p className="mb-1 text-sm text-text-secondary">
            {selectedProvider === "mullvad"
              ? "Get this from mullvad.net/account → WireGuard configuration"
              : selectedProvider === "proton"
                ? "Download from account.protonvpn.com → WireGuard"
                : "Paste the contents of your wg0.conf file"}
          </p>
          <p className="mb-4 text-xs text-text-muted">
            Your private key stays on this device — never sent anywhere except your VPN provider.
          </p>

          <div className="relative">
            <FileText className="absolute left-3 top-3 h-4 w-4 text-text-muted" />
            <textarea
              value={configText}
              onChange={(e) => setConfigText(e.target.value)}
              placeholder={`[Interface]\nPrivateKey = ...\nAddress = 10.x.x.x/32\nDNS = ...\n\n[Peer]\nPublicKey = ...\nEndpoint = ...\nAllowedIPs = 0.0.0.0/0`}
              className="w-full rounded-xl border border-surface-border bg-surface-card p-3 pl-10 font-mono text-sm text-text-primary placeholder:text-text-muted/50 focus:border-amber-500/50 focus:outline-none"
              rows={10}
            />
          </div>

          {error && (
            <div className="mt-3 flex items-center gap-2 text-sm text-status-down">
              <AlertCircle className="h-4 w-4 shrink-0" />
              {error}
            </div>
          )}

          <div className="mt-4 flex gap-3">
            <button
              onClick={() => setStep("provider")}
              className="rounded-xl border border-surface-border px-4 py-2.5 text-sm text-text-secondary transition-colors hover:border-amber-500/30"
            >
              Back
            </button>
            <button
              onClick={submitConfig}
              disabled={loading}
              className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-amber-500 px-4 py-2.5 font-medium text-black transition-colors hover:bg-amber-400 disabled:opacity-50"
            >
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  Verify Connection
                  <ChevronRight className="h-4 w-4" />
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Verify */}
      {step === "verify" && (
        <div className="text-center">
          {loading && (
            <>
              <Loader2 className="mx-auto mb-4 h-12 w-12 animate-spin text-amber-500" />
              <h2 className="mb-2 text-xl font-bold text-text-primary">
                Testing your connection...
              </h2>
              <p className="text-sm text-text-secondary">
                Bringing up WireGuard and verifying your IP
              </p>
            </>
          )}

          {!loading && verifyResult?.success && (
            <>
              <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-status-up/15">
                <Check className="h-8 w-8 text-status-up" />
              </div>
              <h2 className="mb-4 text-xl font-bold text-text-primary">
                Connection verified!
              </h2>
              <div className="mb-6 rounded-xl border border-status-up/20 bg-status-up/8 p-4">
                <div className="flex items-center justify-center gap-2 text-lg font-medium text-status-up">
                  <MapPin className="h-5 w-5" />
                  {verifyResult.city && verifyResult.country
                    ? `${verifyResult.city}, ${verifyResult.country}`
                    : verifyResult.country || "Connected"}
                </div>
                <div className="mt-1 font-mono text-sm text-status-up/70">
                  {verifyResult.public_ip}
                </div>
              </div>
              <button
                onClick={completeSetup}
                disabled={loading}
                className="inline-flex items-center gap-2 rounded-xl bg-amber-500 px-6 py-3 font-medium text-black transition-colors hover:bg-amber-400"
              >
                Complete Setup
                <Check className="h-4 w-4" />
              </button>
            </>
          )}

          {!loading && verifyResult && !verifyResult.success && (
            <>
              <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-status-down/15">
                <AlertCircle className="h-8 w-8 text-status-down" />
              </div>
              <h2 className="mb-2 text-xl font-bold text-text-primary">
                Connection failed
              </h2>
              <p className="mb-6 text-sm text-status-down">{error}</p>
              <div className="flex justify-center gap-3">
                <button
                  onClick={() => setStep("config")}
                  className="rounded-xl border border-surface-border px-4 py-2.5 text-sm text-text-secondary transition-colors hover:border-amber-500/30"
                >
                  Edit Config
                </button>
                <button
                  onClick={doVerify}
                  className="rounded-xl bg-amber-500 px-4 py-2.5 font-medium text-black transition-colors hover:bg-amber-400"
                >
                  Retry
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* Done */}
      {step === "done" && (
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-amber-500/15">
            <Eye className="h-8 w-8 text-amber-500" />
          </div>
          <h2 className="mb-2 text-xl font-bold text-text-primary">
            You're connected!
          </h2>
          <p className="text-sm text-text-secondary">
            Restarting services — loading dashboard...
          </p>
          <Loader2 className="mx-auto mt-4 h-6 w-6 animate-spin text-amber-500/50" />
        </div>
      )}
    </div>
  );
}
