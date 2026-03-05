import { useEffect, useMemo, useState } from "react";
import { X, Save, RotateCcw, Zap, RefreshCw, ChevronDown } from "lucide-react";

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

const FIELD_GROUPS: { label: string; fields: string[]; defaultOpen?: boolean }[] = [
  {
    label: "VPN",
    fields: ["vpn_enabled", "vpn_type", "vpn_provider", "vpn_country", "vpn_city", "vpn_dns", "wireguard_dns", "killswitch_enabled", "auto_reconnect"],
    defaultOpen: true,
  },
  {
    label: "Authentication",
    fields: ["admin_user", "admin_pass", "auth_proxy_header", "api_key"],
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
    label: "ProtonVPN",
    fields: ["proton_user", "proton_pass"],
  },
  {
    label: "qBittorrent",
    fields: ["qbt_enabled", "webui_port"],
  },
  {
    label: "DNS",
    fields: [
      "dns_enabled", "dns_upstream", "dns_dot_enabled", "dns_cache_enabled",
      "dns_block_ads", "dns_block_malware", "dns_block_surveillance", "dns_custom_blocklist_url",
    ],
  },
  {
    label: "Firewall",
    fields: ["firewall_vpn_input_ports", "firewall_outbound_subnets", "firewall_custom_rules_file"],
  },
  {
    label: "HTTP Proxy",
    fields: ["http_proxy_enabled", "http_proxy_port", "http_proxy_user", "http_proxy_pass"],
  },
  {
    label: "SOCKS5 Proxy",
    fields: [
      "socks_proxy_enabled", "socks_proxy_port", "socks_proxy_user", "socks_proxy_pass",
    ],
  },
  {
    label: "Shadowsocks",
    fields: [
      "shadowsocks_enabled", "shadowsocks_port", "shadowsocks_password", "shadowsocks_cipher",
    ],
  },
  {
    label: "MQTT",
    fields: ["mqtt_enabled", "mqtt_broker", "mqtt_port", "mqtt_user", "mqtt_pass", "mqtt_topic_prefix", "mqtt_discovery_prefix"],
  },
  {
    label: "Notifications",
    fields: ["notify_webhook_url", "notify_gotify_url", "notify_gotify_token"],
  },
  {
    label: "Watchdog",
    fields: ["health_check_interval", "handshake_stale_seconds", "reconnect_threshold", "cooldown_seconds"],
  },
  {
    label: "General",
    fields: ["ui_enabled", "tz", "allowed_networks"],
  },
];

/** Fields rendered as toggle switches instead of text inputs. */
const BOOLEAN_FIELDS = new Set([
  "vpn_enabled", "killswitch_enabled", "auto_reconnect", "qbt_enabled",
  "mqtt_enabled", "ui_enabled", "port_forward_enabled", "server_list_auto_update",
  "dns_enabled", "dns_dot_enabled", "dns_cache_enabled",
  "dns_block_ads", "dns_block_malware", "dns_block_surveillance",
  "http_proxy_enabled", "socks_proxy_enabled", "shadowsocks_enabled",
]);

/** Fields rendered as number inputs. */
const NUMBER_FIELDS = new Set([
  "mqtt_port", "webui_port", "http_proxy_port", "socks_proxy_port", "shadowsocks_port",
  "health_check_interval", "handshake_stale_seconds", "reconnect_threshold", "cooldown_seconds",
  "port_forward_interval", "dns_blocklist_refresh_interval", "server_list_update_interval",
]);

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
  firewall_vpn_input_ports: "VPN Input Ports",
  firewall_outbound_subnets: "Outbound Subnets (bypass VPN)",
  firewall_custom_rules_file: "Custom Rules File",
  dns_enabled: "DNS Server",
  dns_upstream: "Upstream DNS",
  dns_dot_enabled: "DNS-over-TLS",
  dns_cache_enabled: "DNS Cache",
  dns_block_ads: "Block Ads",
  dns_block_malware: "Block Malware",
  dns_block_surveillance: "Block Surveillance",
  dns_custom_blocklist_url: "Custom Blocklist URL",
  proton_user: "Proton Username",
  proton_pass: "Proton Password",
  http_proxy_enabled: "HTTP Proxy",
  http_proxy_port: "HTTP Proxy Port",
  http_proxy_user: "HTTP Proxy User",
  http_proxy_pass: "HTTP Proxy Password",
  socks_proxy_enabled: "SOCKS5 Proxy",
  socks_proxy_port: "SOCKS5 Port",
  socks_proxy_user: "SOCKS5 User",
  socks_proxy_pass: "SOCKS5 Password",
  shadowsocks_enabled: "Shadowsocks",
  shadowsocks_port: "Shadowsocks Port",
  shadowsocks_password: "Shadowsocks Password",
  shadowsocks_cipher: "Shadowsocks Cipher",
  handshake_stale_seconds: "Handshake Stale Threshold (s)",
  reconnect_threshold: "Reconnect Threshold",
  cooldown_seconds: "Cooldown Duration (s)",
  vpn_enabled: "VPN Enabled",
  vpn_type: "VPN Protocol",
  wireguard_dns: "WireGuard DNS Override",
  qbt_enabled: "qBittorrent Enabled",
  webui_port: "qBittorrent WebUI Port",
  mqtt_topic_prefix: "MQTT Topic Prefix",
  mqtt_discovery_prefix: "HA Discovery Prefix",
  tz: "Timezone",
  allowed_networks: "Allowed Networks",
};

const FIELD_HINTS: Record<string, string> = {
  admin_user: "Leave blank to disable login",
  auth_proxy_header: "e.g. Remote-User, X-Forwarded-User",
  api_key: "For Homepage, HACS, Prometheus",
  vpn_provider: "custom, mullvad, ivpn, pia, or gluetun",
  wireguard_private_key: "Base64 private key for Mullvad/IVPN",
  wireguard_addresses: "e.g. 10.66.0.1/32",
  pia_user: "PIA username (p1234567)",
  pia_pass: "PIA password",
  gluetun_url: "e.g. http://gluetun:8000",
  gluetun_api_key: "Gluetun API key (if auth enabled)",
  notify_webhook_url: "Discord, Slack, or generic webhook URL",
  notify_gotify_url: "e.g. http://gotify:8080",
  notify_gotify_token: "Gotify app token",
  vpn_country: "e.g. ch, us, de",
  vpn_city: "e.g. zurich, new-york",
  vpn_dns: "Override DNS (default: provider DNS)",
  firewall_vpn_input_ports: "Comma-separated ports (e.g. 51413,6881)",
  firewall_outbound_subnets: "CIDRs that bypass VPN (e.g. 192.168.1.0/24)",
  firewall_custom_rules_file: "Path to nftables rules file",
  dns_upstream: "Comma-separated IPs (e.g. 1.1.1.1,1.0.0.1)",
  dns_custom_blocklist_url: "URL to hosts-format blocklist",
  proton_user: "ProtonVPN username",
  proton_pass: "ProtonVPN password",
  http_proxy_port: "Default: 8888",
  http_proxy_user: "Leave blank for no auth",
  http_proxy_pass: "Leave blank for no auth",
  socks_proxy_port: "Default: 1080",
  socks_proxy_user: "Leave blank for no auth",
  socks_proxy_pass: "Leave blank for no auth",
  shadowsocks_port: "Default: 8388",
  shadowsocks_password: "Encryption password",
  shadowsocks_cipher: "aes-256-gcm or chacha20-ietf-poly1305",
  handshake_stale_seconds: "Default: 180",
  reconnect_threshold: "Default: 3",
  cooldown_seconds: "Default: 300",
  vpn_type: "auto, wireguard, or openvpn",
  wireguard_dns: "Override WireGuard peer DNS (e.g. 10.64.0.1)",
  webui_port: "Default: 8080",
  mqtt_topic_prefix: "Default: tunnelvision",
  mqtt_discovery_prefix: "Default: homeassistant",
  tz: "e.g. America/New_York",
  allowed_networks: "CIDR allow-list (e.g. 192.168.1.0/24)",
};

/** Fields that take effect immediately without container restart. */
const HOT_RELOAD_FIELDS = new Set([
  "auto_reconnect",
  "health_check_interval",
  "handshake_stale_seconds",
  "reconnect_threshold",
  "cooldown_seconds",
  "vpn_country",
  "vpn_city",
  "notify_webhook_url",
  "notify_gotify_url",
  "notify_gotify_token",
  "dns_block_ads",
  "dns_block_malware",
  "dns_block_surveillance",
]);

function Toggle({ checked, onChange, dirty }: { checked: boolean; onChange: (v: boolean) => void; dirty: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full transition-colors ${
        checked ? "bg-amber-500" : "bg-surface-border"
      } ${dirty ? "ring-1 ring-amber-500/50" : ""}`}
    >
      <span
        className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform ${
          checked ? "translate-x-[18px]" : "translate-x-[3px]"
        }`}
      />
    </button>
  );
}

export function SettingsPanel({ onClose }: SettingsPanelProps) {
  const [data, setData] = useState<SettingsData | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [savedForm, setSavedForm] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [needsRestart, setNeedsRestart] = useState(false);
  // Track user overrides: true = explicitly opened, false = explicitly closed, absent = default
  const [sectionOverrides, setSectionOverrides] = useState<Record<string, boolean>>({});

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

  const isSectionOpen = (group: { label: string; fields: string[]; defaultOpen?: boolean }) => {
    // User override wins
    if (group.label in sectionOverrides) return sectionOverrides[group.label];
    // Auto-open if default or has dirty fields
    if (group.defaultOpen) return true;
    return group.fields.some((k) => dirtyFields.has(k));
  };

  const toggleSection = (label: string) => {
    setSectionOverrides((prev) => {
      const group = FIELD_GROUPS.find((g) => g.label === label)!;
      const currentlyOpen = isSectionOpen(group);
      return { ...prev, [label]: !currentlyOpen };
    });
  };

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

          {FIELD_GROUPS.map((group) => {
            const isOpen = isSectionOpen(group);
            const groupDirty = group.fields.some((k) => dirtyFields.has(k));
            return (
              <div key={group.label} className="mb-1">
                <button
                  type="button"
                  onClick={() => toggleSection(group.label)}
                  className="flex w-full items-center justify-between rounded-lg px-2 py-2 text-left transition-colors hover:bg-surface-card"
                >
                  <div className="flex items-center gap-2">
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
                      {group.label}
                    </h3>
                    {groupDirty && (
                      <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                    )}
                  </div>
                  <ChevronDown
                    className={`h-3.5 w-3.5 text-text-muted transition-transform ${
                      isOpen ? "rotate-0" : "-rotate-90"
                    }`}
                  />
                </button>
                {isOpen && (
                  <div className="space-y-2.5 px-2 pb-3 pt-1">
                    {group.fields.map((key) => {
                      const meta = data.fields[key];
                      if (!meta) return null;
                      const fieldDirty = dirtyFields.has(key);
                      const isHotReload = HOT_RELOAD_FIELDS.has(key);
                      const isBool = BOOLEAN_FIELDS.has(key);
                      const isNum = NUMBER_FIELDS.has(key);
                      const boolValue = (form[key] || "").toLowerCase() === "true";

                      return (
                        <div key={key}>
                          <div className="mb-1 flex items-center justify-between">
                            <div className="flex items-center gap-1.5">
                              <label className="text-xs text-text-secondary">
                                {FIELD_LABELS[key] || key}
                              </label>
                              <span className="font-mono text-[10px] text-text-muted">
                                {meta.env}
                              </span>
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
                            {isBool && (
                              <Toggle
                                checked={boolValue}
                                onChange={(v) =>
                                  setForm({ ...form, [key]: v ? "true" : "false" })
                                }
                                dirty={fieldDirty}
                              />
                            )}
                          </div>
                          {!isBool && (
                            <input
                              type={meta.secret ? "password" : isNum ? "number" : "text"}
                              inputMode={isNum ? "numeric" : undefined}
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
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
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
