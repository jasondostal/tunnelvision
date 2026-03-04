import { useState, useCallback, useEffect, useMemo } from "react";
import { Logo } from "@/components/logo";
import {
  Shield,
  ChevronRight,
  Check,
  Loader2,
  AlertCircle,
  MapPin,
  FileText,
  Key,
  User,
  Globe,
  Search,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { ServerEntry } from "@/lib/types";

interface Provider {
  id: string;
  name: string;
  description: string;
  setup_type: string;
  logo?: string;
  supports_wireguard?: boolean;
  supports_openvpn?: boolean;
}

interface VerifyResult {
  success: boolean;
  public_ip: string;
  country: string;
  city: string;
  error: string;
}

type Step = "welcome" | "provider" | "credentials" | "config" | "server" | "verify" | "done";

const ALL_STEPS: Step[] = ["welcome", "provider", "credentials", "verify", "done"];

// Shared styles
const inputClass =
  "w-full rounded-xl border border-surface-border bg-surface-card p-2.5 pl-10 text-sm text-text-primary placeholder:text-text-muted/50 focus:border-amber-500/50 focus:outline-none";
const inputMonoClass = `${inputClass} font-mono`;
const backBtnClass =
  "rounded-xl border border-surface-border px-4 py-2.5 text-sm text-text-secondary transition-colors hover:border-amber-500/30";
const primaryBtnClass =
  "flex flex-1 items-center justify-center gap-2 rounded-xl bg-amber-500 px-4 py-2.5 font-medium text-black transition-colors hover:bg-amber-400 disabled:opacity-50";

function WizardError({ message }: { message: string }) {
  if (!message) return null;
  return (
    <div className="mt-3 flex items-center gap-2 text-sm text-status-down">
      <AlertCircle className="h-4 w-4 shrink-0" />
      {message}
    </div>
  );
}

/** Map provider ID to the step the user should return to on failure. */
function stepForProvider(provider: string): Step {
  if (provider === "custom" || provider === "proton") return "config";
  if (provider === "mullvad" || provider === "ivpn" || provider === "pia") return "server";
  return "credentials";
}

function stepIndex(step: Step): number {
  const map: Record<Step, number> = {
    welcome: 0,
    provider: 1,
    credentials: 2,
    config: 2,
    server: 2,
    verify: 3,
    done: 4,
  };
  return map[step];
}

export function SetupWizard({ onComplete }: { onComplete: () => void }) {
  const [step, setStep] = useState<Step>("welcome");
  const [providers, setProviders] = useState<Provider[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [verifyResult, setVerifyResult] = useState<VerifyResult | null>(null);

  // Config paste (custom/proton/openvpn providers)
  const [configText, setConfigText] = useState("");
  const [isOpenvpnProvider, setIsOpenvpnProvider] = useState(false);
  const [ovpnUser, setOvpnUser] = useState("");
  const [ovpnPass, setOvpnPass] = useState("");

  // WG credentials (mullvad/ivpn)
  const [privateKey, setPrivateKey] = useState("");
  const [addresses, setAddresses] = useState("");
  const [dns, setDns] = useState("");
  const [generatedPublicKey, setGeneratedPublicKey] = useState("");
  const [keyGenLoading, setKeyGenLoading] = useState(false);
  const [keyCopied, setKeyCopied] = useState(false);

  // PIA credentials
  const [piaUser, setPiaUser] = useState("");
  const [piaPass, setPiaPass] = useState("");
  const [portForward, setPortForward] = useState(false);

  // Gluetun
  const [gluetunUrl, setGluetunUrl] = useState("http://gluetun:8000");
  const [gluetunApiKey, setGluetunApiKey] = useState("");

  // Server picker
  const [servers, setServers] = useState<ServerEntry[]>([]);
  const [serverSearch, setServerSearch] = useState("");
  const [countryFilter, setCountryFilter] = useState("");
  const [serversLoading, setServersLoading] = useState(false);

  const loadProviders = useCallback(async () => {
    try {
      const resp = await fetch("/api/v1/setup/providers");
      const data = await resp.json();
      setProviders(data.providers);
      setStep("provider");
    } catch {
      setError("Failed to load providers");
    }
  }, []);

  const selectProvider = useCallback(async (id: string) => {
    setSelectedProvider(id);
    setError("");
    try {
      await fetch("/api/v1/setup/provider", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: id }),
      });
      const meta = providers.find((p) => p.id === id);
      const isOvpn = meta?.supports_wireguard === false && meta?.supports_openvpn === true;
      setIsOpenvpnProvider(isOvpn);
      if (id === "custom" || id === "proton" || isOvpn) {
        setStep("config");
      } else {
        setStep("credentials");
      }
    } catch {
      setError("Failed to select provider");
    }
  }, [providers]);

  const generateKeypair = useCallback(async () => {
    setKeyGenLoading(true);
    setError("");
    try {
      const resp = await fetch("/api/v1/setup/generate-keypair", { method: "POST" });
      const data = await resp.json();
      if (!data.success) {
        setError(data.error);
        return;
      }
      setPrivateKey(data.private_key);
      setGeneratedPublicKey(data.public_key);
      setKeyCopied(false);
    } finally {
      setKeyGenLoading(false);
    }
  }, []);

  const copyPublicKey = useCallback(() => {
    if (generatedPublicKey) {
      navigator.clipboard.writeText(generatedPublicKey);
      setKeyCopied(true);
      setTimeout(() => setKeyCopied(false), 2000);
    }
  }, [generatedPublicKey]);

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

  const doComplete = useCallback(async () => {
    setLoading(true);
    try {
      await fetch("/api/v1/setup/complete", { method: "POST" });
      setStep("done");
      setTimeout(onComplete, 2000);
    } finally {
      setLoading(false);
    }
  }, [onComplete]);

  const submitCredentials = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const body: Record<string, unknown> = { provider: selectedProvider };

      if (selectedProvider === "mullvad" || selectedProvider === "ivpn") {
        body.private_key = privateKey;
        body.addresses = addresses;
        if (dns) body.dns = dns;
      } else if (selectedProvider === "pia") {
        body.pia_user = piaUser;
        body.pia_pass = piaPass;
        body.port_forward = portForward;
      } else if (selectedProvider === "gluetun") {
        body.gluetun_url = gluetunUrl;
        if (gluetunApiKey) body.gluetun_api_key = gluetunApiKey;
      }

      const resp = await fetch("/api/v1/setup/credentials", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await resp.json();

      if (!data.success) {
        setError(data.error);
        return;
      }

      if (data.next === "server") {
        setStep("server");
      } else if (data.next === "done") {
        await doComplete();
      }
    } finally {
      setLoading(false);
    }
  }, [selectedProvider, privateKey, addresses, dns, piaUser, piaPass, portForward, gluetunUrl, gluetunApiKey, doComplete]);

  const submitConfig = useCallback(async () => {
    if (!configText.trim()) {
      setError(isOpenvpnProvider ? "Paste your OpenVPN configuration" : "Paste your WireGuard configuration");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const url = isOpenvpnProvider ? "/api/v1/setup/openvpn" : "/api/v1/setup/wireguard";
      const body = isOpenvpnProvider
        ? { config: configText, username: ovpnUser, password: ovpnPass }
        : { config: configText };
      const resp = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await resp.json();
      if (!data.success) {
        setError(data.error);
        return;
      }
      setStep("verify");
      await doVerify();
    } finally {
      setLoading(false);
    }
  }, [configText, isOpenvpnProvider, ovpnUser, ovpnPass, doVerify]);

  // Load servers when entering server step
  useEffect(() => {
    if (step !== "server") return;
    setServersLoading(true);
    fetch("/api/v1/vpn/servers")
      .then((r) => r.json())
      .then((data) => setServers(data.servers || []))
      .catch(() => setError("Failed to load server list"))
      .finally(() => setServersLoading(false));
  }, [step]);

  const countries = useMemo(() => {
    const set = new Set(servers.map((s) => s.country));
    return Array.from(set).sort();
  }, [servers]);

  const filteredServers = useMemo(() => {
    let list = servers;
    if (countryFilter) {
      list = list.filter((s) => s.country === countryFilter);
    }
    if (serverSearch) {
      const q = serverSearch.toLowerCase();
      list = list.filter(
        (s) =>
          s.hostname.toLowerCase().includes(q) ||
          s.city.toLowerCase().includes(q) ||
          s.country.toLowerCase().includes(q)
      );
    }
    return list;
  }, [servers, countryFilter, serverSearch]);

  const selectServer = useCallback(async (hostname: string) => {
    setLoading(true);
    setError("");
    try {
      const resp = await fetch("/api/v1/setup/server", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ hostname }),
      });
      const data = await resp.json();
      if (!data.success) {
        setError(data.error);
        return;
      }
      setStep("verify");
      await doVerify();
    } finally {
      setLoading(false);
    }
  }, [doVerify]);

  const goBackToProvider = useCallback(() => {
    setError("");
    setStep("provider");
  }, []);

  const goBackToCredentials = useCallback(() => {
    setError("");
    setStep("credentials");
  }, []);

  const currentStepIdx = stepIndex(step);

  return (
    <div className="mx-auto min-h-screen max-w-xl px-4 py-12">
      {/* Progress */}
      <div className="mb-8 flex items-center justify-center gap-2">
        {ALL_STEPS.map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <div
              className={cn(
                "h-2 w-2 rounded-full transition-colors",
                currentStepIdx === i
                  ? "bg-amber-500"
                  : currentStepIdx > i
                    ? "bg-amber-500/50"
                    : "bg-surface-border"
              )}
            />
            {i < ALL_STEPS.length - 1 && (
              <div className="h-px w-6 bg-surface-border" />
            )}
          </div>
        ))}
      </div>

      {/* Welcome */}
      {step === "welcome" && (
        <div className="text-center">
          <Logo className="mx-auto mb-6 h-16 w-16" />
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
          <WizardError message={error} />
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
          <WizardError message={error} />
        </div>
      )}

      {/* Credentials — Mullvad/IVPN */}
      {step === "credentials" && (selectedProvider === "mullvad" || selectedProvider === "ivpn") && (
        <div>
          <h2 className="mb-2 text-xl font-bold text-text-primary">
            WireGuard credentials
          </h2>
          <p className="mb-1 text-sm text-text-secondary">
            {selectedProvider === "mullvad"
              ? "Get these from mullvad.net/account → WireGuard configuration"
              : "Get these from ivpn.net/account → WireGuard Keys"}
          </p>
          <p className="mb-4 text-xs text-text-muted">
            Your private key stays on this device — never sent anywhere except your VPN provider.
          </p>

          <div className="space-y-3">
            <div>
              <div className="mb-1 flex items-center justify-between">
                <label className="text-sm font-medium text-text-secondary">
                  Private Key
                </label>
                <button
                  type="button"
                  onClick={generateKeypair}
                  disabled={keyGenLoading}
                  className="flex items-center gap-1.5 rounded-lg border border-amber-500/30 px-2.5 py-1 text-xs font-medium text-amber-500 transition-colors hover:bg-amber-500/10 disabled:opacity-50"
                >
                  {keyGenLoading ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Key className="h-3 w-3" />
                  )}
                  Generate Key
                </button>
              </div>
              <div className="relative">
                <Key className="absolute left-3 top-2.5 h-4 w-4 text-text-muted" />
                <input
                  type="password"
                  value={privateKey}
                  onChange={(e) => { setPrivateKey(e.target.value); setGeneratedPublicKey(""); }}
                  placeholder="Base64 private key (44 characters)"
                  className={inputMonoClass}
                />
              </div>
            </div>

            {generatedPublicKey && (
              <div className="rounded-xl border border-amber-500/20 bg-amber-500/8 p-3">
                <div className="mb-1.5 flex items-center justify-between">
                  <span className="text-xs font-medium text-amber-500">Your public key</span>
                  <button
                    type="button"
                    onClick={copyPublicKey}
                    className="flex items-center gap-1 text-xs text-amber-500/70 hover:text-amber-500 transition-colors"
                  >
                    {keyCopied ? <Check className="h-3 w-3" /> : <Globe className="h-3 w-3" />}
                    {keyCopied ? "Copied!" : "Copy"}
                  </button>
                </div>
                <p className="mb-2 break-all font-mono text-xs text-amber-400/80">
                  {generatedPublicKey}
                </p>
                <p className="text-xs text-text-muted">
                  {selectedProvider === "mullvad"
                    ? "Add this at mullvad.net → Account → WireGuard Keys, then enter your assigned address below."
                    : "Add this at ivpn.net → Account → WireGuard Keys, then enter your assigned address below."}
                </p>
              </div>
            )}

            <div>
              <label className="mb-1 block text-sm font-medium text-text-secondary">
                Address
              </label>
              <div className="relative">
                <Globe className="absolute left-3 top-2.5 h-4 w-4 text-text-muted" />
                <input
                  type="text"
                  value={addresses}
                  onChange={(e) => setAddresses(e.target.value)}
                  placeholder="e.g. 10.66.0.1/32"
                  className={inputMonoClass}
                />
              </div>
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-text-secondary">
                DNS <span className="text-text-muted">(optional)</span>
              </label>
              <input
                type="text"
                value={dns}
                onChange={(e) => setDns(e.target.value)}
                placeholder={selectedProvider === "mullvad" ? "10.64.0.1" : "172.16.0.1"}
                className="w-full rounded-xl border border-surface-border bg-surface-card p-2.5 font-mono text-sm text-text-primary placeholder:text-text-muted/50 focus:border-amber-500/50 focus:outline-none"
              />
            </div>
          </div>

          <WizardError message={error} />

          <div className="mt-4 flex gap-3">
            <button onClick={goBackToProvider} className={backBtnClass}>
              Back
            </button>
            <button onClick={submitCredentials} disabled={loading} className={primaryBtnClass}>
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  Pick Server
                  <ChevronRight className="h-4 w-4" />
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Credentials — PIA */}
      {step === "credentials" && selectedProvider === "pia" && (
        <div>
          <h2 className="mb-2 text-xl font-bold text-text-primary">
            PIA credentials
          </h2>
          <p className="mb-4 text-sm text-text-secondary">
            Your PIA username and password. TunnelVision auto-negotiates WireGuard keys with PIA's API.
          </p>

          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-text-secondary">
                Username
              </label>
              <div className="relative">
                <User className="absolute left-3 top-2.5 h-4 w-4 text-text-muted" />
                <input
                  type="text"
                  value={piaUser}
                  onChange={(e) => setPiaUser(e.target.value)}
                  placeholder="p1234567"
                  className={inputClass}
                />
              </div>
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-text-secondary">
                Password
              </label>
              <div className="relative">
                <Key className="absolute left-3 top-2.5 h-4 w-4 text-text-muted" />
                <input
                  type="password"
                  value={piaPass}
                  onChange={(e) => setPiaPass(e.target.value)}
                  placeholder="Your PIA password"
                  className={inputClass}
                />
              </div>
            </div>

            <label className="flex items-center gap-3 rounded-xl border border-surface-border bg-surface-card p-3 cursor-pointer hover:border-amber-500/30">
              <input
                type="checkbox"
                checked={portForward}
                onChange={(e) => setPortForward(e.target.checked)}
                className="h-4 w-4 rounded border-surface-border accent-amber-500"
              />
              <div>
                <div className="text-sm font-medium text-text-primary">Enable port forwarding</div>
                <div className="text-xs text-text-muted">Required for seeding. Only available on select servers.</div>
              </div>
            </label>
          </div>

          <WizardError message={error} />

          <div className="mt-4 flex gap-3">
            <button onClick={goBackToProvider} className={backBtnClass}>
              Back
            </button>
            <button onClick={submitCredentials} disabled={loading} className={primaryBtnClass}>
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  Verify & Pick Server
                  <ChevronRight className="h-4 w-4" />
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Credentials — Gluetun */}
      {step === "credentials" && selectedProvider === "gluetun" && (
        <div>
          <h2 className="mb-2 text-xl font-bold text-text-primary">
            Connect to Gluetun
          </h2>
          <p className="mb-4 text-sm text-text-secondary">
            Point TunnelVision at your running gluetun container. VPN management stays with gluetun — TunnelVision adds the dashboard.
          </p>

          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-text-secondary">
                Gluetun URL
              </label>
              <div className="relative">
                <Globe className="absolute left-3 top-2.5 h-4 w-4 text-text-muted" />
                <input
                  type="text"
                  value={gluetunUrl}
                  onChange={(e) => setGluetunUrl(e.target.value)}
                  placeholder="http://gluetun:8000"
                  className={inputMonoClass}
                />
              </div>
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-text-secondary">
                API Key <span className="text-text-muted">(optional)</span>
              </label>
              <div className="relative">
                <Key className="absolute left-3 top-2.5 h-4 w-4 text-text-muted" />
                <input
                  type="password"
                  value={gluetunApiKey}
                  onChange={(e) => setGluetunApiKey(e.target.value)}
                  placeholder="If gluetun has auth enabled"
                  className={inputClass}
                />
              </div>
            </div>
          </div>

          <WizardError message={error} />

          <div className="mt-4 flex gap-3">
            <button onClick={goBackToProvider} className={backBtnClass}>
              Back
            </button>
            <button onClick={submitCredentials} disabled={loading} className={primaryBtnClass}>
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  Connect
                  <Check className="h-4 w-4" />
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Config Input (WireGuard — custom/proton) */}
      {step === "config" && !isOpenvpnProvider && (
        <div>
          <h2 className="mb-2 text-xl font-bold text-text-primary">
            Paste your WireGuard config
          </h2>
          <p className="mb-1 text-sm text-text-secondary">
            {selectedProvider === "proton"
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

          <WizardError message={error} />

          <div className="mt-4 flex gap-3">
            <button onClick={goBackToProvider} className={backBtnClass}>
              Back
            </button>
            <button onClick={submitConfig} disabled={loading} className={primaryBtnClass}>
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

      {/* Config Input (OpenVPN — providers without WireGuard support) */}
      {step === "config" && isOpenvpnProvider && (
        <div>
          <h2 className="mb-2 text-xl font-bold text-text-primary">
            Paste your OpenVPN config
          </h2>
          <p className="mb-1 text-sm text-text-secondary">
            Download an <span className="font-medium">.ovpn</span> file from your provider's account page and paste it below.
          </p>
          <p className="mb-4 text-xs text-text-muted">
            Your config stays on this device — never sent anywhere except your VPN provider.
          </p>

          <div className="relative">
            <FileText className="absolute left-3 top-3 h-4 w-4 text-text-muted" />
            <textarea
              value={configText}
              onChange={(e) => setConfigText(e.target.value)}
              placeholder={`client\ndev tun\nproto udp\nremote your-server.example.com 1194\n...`}
              className="w-full rounded-xl border border-surface-border bg-surface-card p-3 pl-10 font-mono text-sm text-text-primary placeholder:text-text-muted/50 focus:border-amber-500/50 focus:outline-none"
              rows={8}
            />
          </div>

          <div className="mt-3 space-y-2">
            <p className="text-xs text-text-muted">
              Credentials <span className="text-text-muted/60">(optional — only if your .ovpn requires a username and password)</span>
            </p>
            <div className="relative">
              <User className="absolute left-3 top-2.5 h-4 w-4 text-text-muted" />
              <input
                type="text"
                value={ovpnUser}
                onChange={(e) => setOvpnUser(e.target.value)}
                placeholder="Username"
                className={inputClass}
              />
            </div>
            <div className="relative">
              <Key className="absolute left-3 top-2.5 h-4 w-4 text-text-muted" />
              <input
                type="password"
                value={ovpnPass}
                onChange={(e) => setOvpnPass(e.target.value)}
                placeholder="Password"
                className={inputClass}
              />
            </div>
          </div>

          <WizardError message={error} />

          <div className="mt-4 flex gap-3">
            <button onClick={goBackToProvider} className={backBtnClass}>
              Back
            </button>
            <button onClick={submitConfig} disabled={loading} className={primaryBtnClass}>
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

      {/* Server Picker (mullvad/ivpn/pia) */}
      {step === "server" && (
        <div>
          <h2 className="mb-2 text-xl font-bold text-text-primary">
            Pick a server
          </h2>
          <p className="mb-4 text-sm text-text-secondary">
            Select a server to connect through. You can change this later.
          </p>

          {/* Filters */}
          <div className="mb-3 flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-text-muted" />
              <input
                type="text"
                value={serverSearch}
                onChange={(e) => setServerSearch(e.target.value)}
                placeholder="Search servers..."
                className={inputClass}
              />
            </div>
            <select
              value={countryFilter}
              onChange={(e) => setCountryFilter(e.target.value)}
              className="rounded-xl border border-surface-border bg-surface-card px-3 py-2.5 text-sm text-text-primary focus:border-amber-500/50 focus:outline-none"
            >
              <option value="">All countries</option>
              {countries.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>

          {/* Server list */}
          <div className="max-h-72 overflow-y-auto rounded-xl border border-surface-border">
            {serversLoading ? (
              <div className="flex items-center justify-center p-8">
                <Loader2 className="h-6 w-6 animate-spin text-amber-500" />
              </div>
            ) : filteredServers.length === 0 ? (
              <div className="p-6 text-center text-sm text-text-muted">
                No servers found
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-surface-border bg-surface-card text-left text-xs text-text-muted">
                    <th className="px-3 py-2">Server</th>
                    <th className="px-3 py-2">Location</th>
                    <th className="px-3 py-2 text-right">Speed</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredServers.map((s) => (
                    <tr
                      key={s.hostname}
                      onClick={() => !loading && selectServer(s.hostname)}
                      className="cursor-pointer border-b border-surface-border last:border-0 hover:bg-surface-card-hover transition-colors"
                    >
                      <td className="px-3 py-2">
                        <span className="font-mono text-text-primary">{s.hostname}</span>
                        {s.owned && (
                          <span className="ml-1.5 inline-block rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-medium text-amber-500">
                            Owned
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-text-secondary">
                        {s.city}, {s.country}
                      </td>
                      <td className="px-3 py-2 text-right text-text-muted">
                        {s.speed_gbps > 0 ? `${s.speed_gbps} Gbps` : "\u2014"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <WizardError message={error} />

          {loading && (
            <div className="mt-3 flex items-center justify-center gap-2 text-sm text-text-secondary">
              <Loader2 className="h-4 w-4 animate-spin" />
              Connecting to server...
            </div>
          )}

          <div className="mt-4">
            <button onClick={goBackToCredentials} className={backBtnClass}>
              Back
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
                Bringing up the VPN tunnel and verifying your IP
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
                onClick={doComplete}
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
                  onClick={() => {
                    setError("");
                    setStep(stepForProvider(selectedProvider));
                  }}
                  className={backBtnClass}
                >
                  Go Back
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
            <Logo className="h-8 w-8" />
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
