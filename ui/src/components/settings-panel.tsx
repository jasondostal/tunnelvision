import { useEffect, useMemo, useState } from "react";
import { X, Save, RotateCcw, Zap, RefreshCw } from "lucide-react";

interface FieldMeta {
  secret: boolean;
  env: string;
}

interface SettingsData {
  settings: Record<string, string>;
  fields: Record<string, FieldMeta>;
}

interface SettingsPanelProps {
  onClose: () => void;
}

const FIELD_GROUPS: { label: string; fields: string[] }[] = [
  {
    label: "Authentication",
    fields: ["admin_user", "admin_pass", "auth_proxy_header", "api_key"],
  },
  {
    label: "VPN",
    fields: ["vpn_provider", "vpn_country", "vpn_city", "vpn_dns", "killswitch_enabled", "auto_reconnect"],
  },
  {
    label: "WireGuard",
    fields: ["wireguard_private_key", "wireguard_addresses"],
  },
  {
    label: "Gluetun (Sidecar)",
    fields: ["gluetun_url", "gluetun_api_key"],
  },
  {
    label: "PIA",
    fields: ["pia_user", "pia_pass", "port_forward_enabled"],
  },
  {
    label: "MQTT",
    fields: ["mqtt_enabled", "mqtt_broker", "mqtt_port", "mqtt_user", "mqtt_pass"],
  },
  {
    label: "Notifications",
    fields: ["notify_webhook_url", "notify_gotify_url", "notify_gotify_token"],
  },
  {
    label: "Firewall",
    fields: ["firewall_vpn_input_ports", "firewall_outbound_subnets", "firewall_custom_rules_file"],
  },
  {
    label: "DNS",
    fields: [
      "dns_enabled", "dns_upstream", "dns_dot_enabled", "dns_cache_enabled",
      "dns_block_ads", "dns_block_malware", "dns_block_surveillance", "dns_custom_blocklist_url",
    ],
  },
  {
    label: "ProtonVPN",
    fields: ["proton_user", "proton_pass"],
  },
  {
    label: "HTTP Proxy",
    fields: ["http_proxy_enabled", "http_proxy_port", "http_proxy_user", "http_proxy_pass"],
  },
  {
    label: "SOCKS5 Proxy",
    fields: [
      "socks_proxy_enabled", "socks_proxy_port", "socks_proxy_user", "socks_proxy_pass",
      "shadowsocks_enabled", "shadowsocks_password", "shadowsocks_cipher",
    ],
  },
  {
    label: "General",
    fields: ["health_check_interval", "ui_enabled"],
  },
];

const FIELD_LABELS: Record<string, string> = {
  admin_user: "Admin Username",
  admin_pass: "Admin Password",
  auth_proxy_header: "Proxy Auth Header",
  api_key: "API Key",
  vpn_provider: "VPN Provider",
  auto_reconnect: "Auto-Reconnect",
  wireguard_private_key: "WireGuard Private Key",
  wireguard_addresses: "WireGuard Addresses",
  pia_user: "PIA Username",
  pia_pass: "PIA Password",
  port_forward_enabled: "Port Forwarding",
  notify_webhook_url: "Webhook URL",
  notify_gotify_url: "Gotify URL",
  notify_gotify_token: "Gotify Token",
  vpn_country: "VPN Country",
  vpn_city: "VPN City",
  vpn_dns: "DNS Server",
  killswitch_enabled: "Killswitch",
  mqtt_enabled: "MQTT Enabled",
  mqtt_broker: "MQTT Broker",
  mqtt_port: "MQTT Port",
  mqtt_user: "MQTT User",
  mqtt_pass: "MQTT Password",
  health_check_interval: "Health Check Interval (s)",
  ui_enabled: "Dashboard UI",
  // Firewall
  firewall_vpn_input_ports: "VPN Input Ports",
  firewall_outbound_subnets: "Outbound Subnets (bypass VPN)",
  firewall_custom_rules_file: "Custom Rules File",
  // DNS
  dns_enabled: "DNS Server",
  dns_upstream: "Upstream DNS",
  dns_dot_enabled: "DNS-over-TLS",
  dns_cache_enabled: "DNS Cache",
  dns_block_ads: "Block Ads",
  dns_block_malware: "Block Malware",
  dns_block_surveillance: "Block Surveillance",
  dns_custom_blocklist_url: "Custom Blocklist URL",
  // ProtonVPN
  proton_user: "Proton Username",
  proton_pass: "Proton Password",
  // HTTP Proxy
  http_proxy_enabled: "HTTP Proxy",
  http_proxy_port: "HTTP Proxy Port",
  http_proxy_user: "HTTP Proxy User",
  http_proxy_pass: "HTTP Proxy Password",
  // SOCKS5
  socks_proxy_enabled: "SOCKS5 Proxy",
  socks_proxy_port: "SOCKS5 Port",
  socks_proxy_user: "SOCKS5 User",
  socks_proxy_pass: "SOCKS5 Password",
  shadowsocks_enabled: "Shadowsocks",
  shadowsocks_password: "Shadowsocks Password",
  shadowsocks_cipher: "Shadowsocks Cipher",
};

const FIELD_HINTS: Record<string, string> = {
  admin_user: "Leave blank to disable login",
  auth_proxy_header: "e.g. Remote-User, X-Forwarded-User",
  api_key: "For Homepage, HACS, Prometheus",
  vpn_provider: "custom, mullvad, ivpn, pia, or gluetun",
  auto_reconnect: "true or false",
  wireguard_private_key: "Base64 private key for Mullvad/IVPN",
  wireguard_addresses: "e.g. 10.66.0.1/32",
  pia_user: "PIA username (p1234567)",
  pia_pass: "PIA password",
  port_forward_enabled: "true or false (PIA only)",
  gluetun_url: "e.g. http://gluetun:8000",
  gluetun_api_key: "Gluetun API key (if auth enabled)",
  notify_webhook_url: "Discord, Slack, or generic webhook URL",
  notify_gotify_url: "e.g. http://gotify:8080",
  notify_gotify_token: "Gotify app token",
  vpn_country: "e.g. ch, us, de",
  vpn_city: "e.g. zurich, new-york",
  vpn_dns: "Override DNS (default: provider DNS)",
  killswitch_enabled: "true or false",
  mqtt_enabled: "true or false",
  ui_enabled: "true or false",
  // Firewall
  firewall_vpn_input_ports: "Comma-separated ports (e.g. 51413,6881)",
  firewall_outbound_subnets: "CIDRs that bypass VPN (e.g. 192.168.1.0/24)",
  firewall_custom_rules_file: "Path to nftables rules file",
  // DNS
  dns_enabled: "true or false",
  dns_upstream: "Comma-separated IPs (e.g. 1.1.1.1,1.0.0.1)",
  dns_dot_enabled: "true or false",
  dns_cache_enabled: "true or false",
  dns_block_ads: "true or false (StevenBlack hosts)",
  dns_block_malware: "true or false (URLhaus)",
  dns_block_surveillance: "true or false",
  dns_custom_blocklist_url: "URL to hosts-format blocklist",
  // ProtonVPN
  proton_user: "ProtonVPN username",
  proton_pass: "ProtonVPN password",
  // HTTP Proxy
  http_proxy_enabled: "true or false",
  http_proxy_port: "Default: 8888",
  http_proxy_user: "Leave blank for no auth",
  http_proxy_pass: "Leave blank for no auth",
  // SOCKS5
  socks_proxy_enabled: "true or false",
  socks_proxy_port: "Default: 1080",
  socks_proxy_user: "Leave blank for no auth",
  socks_proxy_pass: "Leave blank for no auth",
  shadowsocks_enabled: "true or false",
  shadowsocks_password: "Encryption password",
  shadowsocks_cipher: "aes-256-gcm or chacha20-ietf-poly1305",
};

/** Fields that take effect immediately without container restart. */
const HOT_RELOAD_FIELDS = new Set([
  "auto_reconnect",
  "health_check_interval",
  "vpn_country",
  "vpn_city",
  "notify_webhook_url",
  "notify_gotify_url",
  "notify_gotify_token",
  "dns_block_ads",
  "dns_block_malware",
  "dns_block_surveillance",
]);

export function SettingsPanel({ onClose }: SettingsPanelProps) {
  const [data, setData] = useState<SettingsData | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [savedForm, setSavedForm] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [needsRestart, setNeedsRestart] = useState(false);

  /** Which fields have been edited since last save/load. */
  const dirtyFields = useMemo(() => {
    const dirty = new Set<string>();
    for (const key of Object.keys(form)) {
      if ((form[key] || "") !== (savedForm[key] || "")) {
        dirty.add(key);
      }
    }
    return dirty;
  }, [form, savedForm]);

  const isDirty = dirtyFields.size > 0;

  useEffect(() => {
    fetch("/api/v1/settings")
      .then((r) => r.json())
      .then((d: SettingsData) => {
        setData(d);
        setForm(d.settings);
        setSavedForm(d.settings);
      });
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setMessage("");
    const r = await fetch("/api/v1/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form),
    });
    const result = await r.json();
    setSaving(false);
    setNeedsRestart(result.needs_restart);
    setMessage(
      result.needs_restart
        ? "Saved — restart container for some changes to take effect"
        : "Saved to /config/tunnelvision.yml"
    );
    if (result.settings) {
      setForm(result.settings);
      setSavedForm(result.settings);
    }
  };

  if (!data) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-amber-500/30 border-t-amber-500" />
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-4 pt-12">
      <div className="w-full max-w-lg rounded-xl border border-surface-border bg-surface-bg shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-surface-border px-5 py-4">
          <div className="flex items-center gap-2.5">
            <h2 className="text-base font-bold text-text-primary">Settings</h2>
            {isDirty && (
              <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium text-amber-400">
                unsaved
              </span>
            )}
          </div>
          <button
            onClick={() => {
              if (isDirty && !confirm("You have unsaved changes. Discard?")) return;
              onClose();
            }}
            className="rounded-lg p-1.5 text-text-muted transition-colors hover:bg-surface-card hover:text-text-primary"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="max-h-[70vh] overflow-y-auto px-5 py-4">
          <p className="mb-4 text-xs text-text-muted">
            Saved to <code className="rounded bg-surface-card px-1.5 py-0.5">/config/tunnelvision.yml</code>.
            Env vars are used as defaults when a field isn't set here.
          </p>

          {FIELD_GROUPS.map((group) => (
            <div key={group.label} className="mb-5">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-muted">
                {group.label}
              </h3>
              <div className="space-y-2.5">
                {group.fields.map((key) => {
                  const meta = data.fields[key];
                  if (!meta) return null;
                  const fieldDirty = dirtyFields.has(key);
                  const isHotReload = HOT_RELOAD_FIELDS.has(key);
                  return (
                    <div key={key}>
                      <div className="mb-1 flex items-center gap-1.5">
                        <label className="text-xs text-text-secondary">
                          {FIELD_LABELS[key] || key}
                          <span className="ml-2 font-mono text-text-muted">
                            ${meta.env}
                          </span>
                        </label>
                        {fieldDirty && (
                          <span
                            className="flex items-center gap-0.5 text-[10px]"
                            title={
                              isHotReload
                                ? "Takes effect immediately"
                                : "Requires container restart"
                            }
                          >
                            {isHotReload ? (
                              <Zap className="h-2.5 w-2.5 text-status-up" />
                            ) : (
                              <RefreshCw className="h-2.5 w-2.5 text-amber-400" />
                            )}
                          </span>
                        )}
                      </div>
                      <input
                        type={meta.secret ? "password" : "text"}
                        value={form[key] || ""}
                        onChange={(e) =>
                          setForm({ ...form, [key]: e.target.value })
                        }
                        placeholder={FIELD_HINTS[key] || ""}
                        className={`w-full rounded-lg border bg-surface-card px-3 py-2 text-sm text-text-primary placeholder-text-muted outline-none transition-colors focus:border-amber-500/50 ${
                          fieldDirty
                            ? "border-amber-500/50"
                            : "border-surface-border"
                        }`}
                      />
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-surface-border px-5 py-3">
          <div className="text-xs">
            {message ? (
              <span
                className={
                  needsRestart ? "text-amber-400" : "text-status-up"
                }
              >
                {message}
              </span>
            ) : isDirty ? (
              <span className="flex items-center gap-2 text-text-muted">
                <span className="flex items-center gap-1">
                  <Zap className="h-2.5 w-2.5 text-status-up" />
                  instant
                </span>
                <span className="flex items-center gap-1">
                  <RefreshCw className="h-2.5 w-2.5 text-amber-400" />
                  needs restart
                </span>
              </span>
            ) : null}
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => {
                if (isDirty && !confirm("You have unsaved changes. Discard?")) return;
                onClose();
              }}
              className="rounded-lg border border-surface-border px-3 py-1.5 text-xs text-text-secondary transition-colors hover:bg-surface-card"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving || !isDirty}
              className="flex items-center gap-1.5 rounded-lg bg-amber-500 px-3 py-1.5 text-xs font-medium text-black transition-colors hover:bg-amber-400 disabled:opacity-50"
            >
              {saving ? (
                <RotateCcw className="h-3 w-3 animate-spin" />
              ) : (
                <Save className="h-3 w-3" />
              )}
              Save
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
