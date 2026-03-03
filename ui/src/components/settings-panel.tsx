import { useEffect, useState } from "react";
import { X, Save, RotateCcw } from "lucide-react";

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
    fields: ["vpn_provider", "vpn_country", "vpn_city", "vpn_dns", "killswitch_enabled"],
  },
  {
    label: "MQTT",
    fields: ["mqtt_enabled", "mqtt_broker", "mqtt_port", "mqtt_user", "mqtt_pass"],
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
};

const FIELD_HINTS: Record<string, string> = {
  admin_user: "Leave blank to disable login",
  auth_proxy_header: "e.g. Remote-User, X-Forwarded-User",
  api_key: "For Homepage, HACS, Prometheus",
  vpn_provider: "custom or mullvad",
  vpn_country: "e.g. ch, us, de",
  vpn_city: "e.g. zurich, new-york",
  vpn_dns: "Override DNS (default: provider DNS)",
  killswitch_enabled: "true or false",
  mqtt_enabled: "true or false",
  ui_enabled: "true or false",
};

export function SettingsPanel({ onClose }: SettingsPanelProps) {
  const [data, setData] = useState<SettingsData | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [needsRestart, setNeedsRestart] = useState(false);

  useEffect(() => {
    fetch("/api/v1/settings")
      .then((r) => r.json())
      .then((d: SettingsData) => {
        setData(d);
        setForm(d.settings);
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
          <h2 className="text-base font-bold text-text-primary">Settings</h2>
          <button
            onClick={onClose}
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
                  return (
                    <div key={key}>
                      <label className="mb-1 block text-xs text-text-secondary">
                        {FIELD_LABELS[key] || key}
                        <span className="ml-2 font-mono text-text-muted">
                          ${meta.env}
                        </span>
                      </label>
                      <input
                        type={meta.secret ? "password" : "text"}
                        value={form[key] || ""}
                        onChange={(e) =>
                          setForm({ ...form, [key]: e.target.value })
                        }
                        placeholder={FIELD_HINTS[key] || ""}
                        className="w-full rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-sm text-text-primary placeholder-text-muted outline-none transition-colors focus:border-amber-500/50"
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
            {message && (
              <span
                className={
                  needsRestart ? "text-amber-400" : "text-status-up"
                }
              >
                {message}
              </span>
            )}
          </div>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="rounded-lg border border-surface-border px-3 py-1.5 text-xs text-text-secondary transition-colors hover:bg-surface-card"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
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
