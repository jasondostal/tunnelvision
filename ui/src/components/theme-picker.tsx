import { useEffect, useRef, useState } from "react";
import { Palette } from "lucide-react";
import { getAccentHue, setAccentHue, HUE_PRESETS } from "@/lib/theme";

export function ThemePicker() {
  const [open, setOpen] = useState(false);
  const [hue, setHue] = useState(getAccentHue);
  const panelRef = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open]);

  const handleSlider = (e: React.ChangeEvent<HTMLInputElement>) => {
    const h = Number(e.target.value);
    setHue(h);
    setAccentHue(h);
  };

  const handlePreset = (h: number) => {
    setHue(h);
    setAccentHue(h);
  };

  return (
    <div className="relative" ref={panelRef}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 rounded-lg border border-surface-border px-3 py-1.5 text-xs text-text-secondary transition-colors hover:border-amber-500/30 hover:text-amber-400"
        title="Theme"
      >
        <Palette className="h-3 w-3" />
      </button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-64 rounded-xl border border-surface-border bg-surface-card p-4 shadow-2xl">
          {/* Hue slider */}
          <label className="mb-3 block">
            <span className="mb-2 block text-[11px] font-medium text-text-muted">
              Accent hue
            </span>
            <input
              type="range"
              min={0}
              max={360}
              value={hue}
              onChange={handleSlider}
              className="hue-slider w-full"
            />
          </label>

          {/* Presets */}
          <div className="flex flex-wrap gap-1.5">
            {HUE_PRESETS.map((p) => (
              <button
                key={p.label}
                onClick={() => handlePreset(p.hue)}
                title={p.label}
                className="group relative h-6 w-6 rounded-full border-2 transition-transform hover:scale-110"
                style={{
                  backgroundColor: `oklch(0.769 0.188 ${p.hue})`,
                  borderColor:
                    Math.abs(hue - p.hue) < 5
                      ? "oklch(0.95 0 0)"
                      : "transparent",
                }}
              />
            ))}
          </div>

          {/* Current value */}
          <div className="mt-3 flex items-center justify-between">
            <span className="font-mono text-[11px] text-text-muted">
              {Math.round(hue)}°
            </span>
            <button
              onClick={() => handlePreset(70)}
              className="text-[11px] text-text-muted transition-colors hover:text-text-secondary"
            >
              Reset
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
