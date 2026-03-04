import { useState } from "react";
import { FileStack, Loader2 } from "lucide-react";
import type { ConfigListResponse } from "@/lib/types";

export function ConfigManager({ data }: { data: ConfigListResponse }) {
  const [activating, setActivating] = useState<string | null>(null);

  const handleActivate = async (name: string) => {
    setActivating(name);
    try {
      await fetch(`/api/v1/vpn/configs/${encodeURIComponent(name)}/activate`, {
        method: "POST",
      });
    } finally {
      setTimeout(() => setActivating(null), 2000);
    }
  };

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-5">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <FileStack className="h-5 w-5 text-amber-500" />
          <h2 className="text-sm font-semibold tracking-wide text-text-primary">
            VPN Configs
          </h2>
        </div>
        <span className="rounded-full bg-status-up/15 px-2 py-0.5 text-[10px] font-medium text-status-up border border-status-up/30">
          {data.active}
        </span>
      </div>

      <div className="space-y-1.5">
        {data.configs.map((cfg) => {
          const isActivating = activating === cfg.name;
          const isActive = cfg.active && !activating;
          return (
            <button
              key={cfg.name}
              onClick={() => !cfg.active && !activating && handleActivate(cfg.name)}
              disabled={cfg.active || !!activating}
              className={`flex w-full items-center gap-3 rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
                isActive
                  ? "border-amber-500/30 bg-amber-500/8 text-text-primary"
                  : "border-surface-border bg-surface-bg/50 text-text-secondary hover:border-amber-500/20 hover:text-text-primary disabled:opacity-50"
              }`}
            >
              {/* Radio indicator */}
              <span
                className={`flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border ${
                  isActive
                    ? "border-amber-500 bg-amber-500"
                    : "border-text-muted"
                }`}
              >
                {isActive && (
                  <span className="h-1.5 w-1.5 rounded-full bg-black" />
                )}
              </span>

              {isActivating ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-amber-400" />
              ) : null}

              <span className="flex-1 truncate font-mono text-xs">
                {cfg.name}
              </span>

              <span className="rounded bg-surface-bg px-1.5 py-0.5 text-[10px] text-text-muted">
                {cfg.type}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
