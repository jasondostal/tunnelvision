import { useEffect, useMemo, useState } from "react";
import { X, Search, Globe, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import type { ServerEntry } from "@/lib/types";

interface ServerBrowserProps {
  onClose: () => void;
}

export function ServerBrowser({ onClose }: ServerBrowserProps) {
  const [servers, setServers] = useState<ServerEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [country, setCountry] = useState("");
  const [search, setSearch] = useState("");
  const [connecting, setConnecting] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError("");
    api
      .servers(country || undefined)
      .then((r) => setServers(r.servers))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load servers"))
      .finally(() => setLoading(false));
  }, [country]);

  const countries = useMemo(() => {
    const set = new Set(servers.map((s) => s.country));
    return Array.from(set).sort();
  }, [servers]);

  // Derive country list from unfiltered fetch (only on initial load)
  const [allCountries, setAllCountries] = useState<string[]>([]);
  useEffect(() => {
    if (!country && countries.length) {
      setAllCountries(countries);
    }
  }, [country, countries]);
  const countryOptions = allCountries.length ? allCountries : countries;

  const filtered = useMemo(() => {
    if (!search) return servers;
    const q = search.toLowerCase();
    return servers.filter(
      (s) =>
        s.hostname.toLowerCase().includes(q) ||
        s.city.toLowerCase().includes(q) ||
        s.country.toLowerCase().includes(q),
    );
  }, [servers, search]);

  const handleConnect = async (hostname: string) => {
    setConnecting(hostname);
    try {
      await fetch("/api/v1/vpn/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ hostname }),
      });
      onClose();
    } catch {
      setConnecting(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-4 pt-12">
      <div className="w-full max-w-2xl rounded-xl border border-surface-border bg-surface-bg shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-surface-border px-5 py-4">
          <div className="flex items-center gap-2.5">
            <Globe className="h-5 w-5 text-cyan-500" />
            <h2 className="text-base font-bold text-text-primary">
              Server Browser
            </h2>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-text-muted transition-colors hover:bg-surface-card hover:text-text-primary"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Filters */}
        <div className="flex gap-3 border-b border-surface-border px-5 py-3">
          <select
            value={country}
            onChange={(e) => setCountry(e.target.value)}
            className="rounded-lg border border-surface-border bg-surface-card px-3 py-1.5 text-xs text-text-primary outline-none focus:border-amber-500/50"
          >
            <option value="">All countries</option>
            {countryOptions.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>

          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-text-muted" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search hostname or city..."
              className="w-full rounded-lg border border-surface-border bg-surface-card py-1.5 pl-8 pr-3 text-xs text-text-primary placeholder-text-muted outline-none focus:border-amber-500/50"
            />
          </div>
        </div>

        {/* Content */}
        <div className="max-h-[60vh] overflow-y-auto">
          {loading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-5 w-5 animate-spin text-amber-500" />
            </div>
          )}

          {error && (
            <div className="px-5 py-8 text-center text-sm text-status-down">
              {error}
            </div>
          )}

          {!loading && !error && !filtered.length && (
            <div className="px-5 py-8 text-center text-sm text-text-muted">
              No servers available — server browser requires Mullvad, IVPN, or
              PIA provider
            </div>
          )}

          {!loading && !error && filtered.length > 0 && (
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-surface-border text-left text-text-muted">
                  <th className="px-5 py-2 font-medium">Hostname</th>
                  <th className="px-3 py-2 font-medium">Country</th>
                  <th className="px-3 py-2 font-medium">City</th>
                  <th className="px-3 py-2 font-medium text-right">Gbps</th>
                  <th className="px-3 py-2 font-medium">Owned</th>
                  <th className="px-5 py-2" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((s) => (
                  <tr
                    key={s.hostname}
                    className="border-b border-surface-border/50 transition-colors hover:bg-surface-card/50"
                  >
                    <td className="px-5 py-2 font-mono text-text-primary">
                      {s.hostname}
                    </td>
                    <td className="px-3 py-2 text-text-secondary">
                      {s.country}
                    </td>
                    <td className="px-3 py-2 text-text-secondary">{s.city}</td>
                    <td className="px-3 py-2 text-right font-mono text-text-secondary">
                      {s.speed_gbps}
                    </td>
                    <td className="px-3 py-2">
                      {s.owned && (
                        <span className="rounded bg-status-up/15 px-1.5 py-0.5 text-[10px] text-status-up">
                          owned
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-2 text-right">
                      <button
                        onClick={() => handleConnect(s.hostname)}
                        disabled={!!connecting}
                        className="rounded-md border border-amber-500/30 px-2.5 py-1 text-[11px] font-medium text-amber-400 transition-colors hover:bg-amber-500/10 disabled:opacity-50"
                      >
                        {connecting === s.hostname ? (
                          <Loader2 className="inline h-3 w-3 animate-spin" />
                        ) : (
                          "Connect"
                        )}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-surface-border px-5 py-3">
          <span className="text-xs text-text-muted">
            {filtered.length} server{filtered.length !== 1 ? "s" : ""}
          </span>
          <button
            onClick={onClose}
            className="rounded-lg border border-surface-border px-3 py-1.5 text-xs text-text-secondary transition-colors hover:bg-surface-card"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
