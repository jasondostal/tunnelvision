/** OKLCH accent theme — driven by a single hue value stored in localStorage. */

const STORAGE_KEY = "tv-accent-hue";
const DEFAULT_HUE = 70; // amber

/** Lightness + chroma per shade — hue is injected at runtime. */
const PRIMARY_SHADES: { shade: number; l: number; c: number }[] = [
  { shade: 50, l: 0.987, c: 0.022 },
  { shade: 100, l: 0.962, c: 0.059 },
  { shade: 200, l: 0.924, c: 0.12 },
  { shade: 300, l: 0.879, c: 0.169 },
  { shade: 400, l: 0.828, c: 0.189 },
  { shade: 500, l: 0.769, c: 0.188 },
  { shade: 600, l: 0.666, c: 0.179 },
  { shade: 700, l: 0.555, c: 0.163 },
  { shade: 800, l: 0.473, c: 0.137 },
  { shade: 900, l: 0.414, c: 0.112 },
];

/** Cyan accent shades — offset from primary hue. */
const SECONDARY_OFFSET = 124; // 194 - 70
const SECONDARY_SHADES: { shade: number; l: number; c: number }[] = [
  { shade: 400, l: 0.789, c: 0.154 },
  { shade: 500, l: 0.715, c: 0.143 },
  { shade: 600, l: 0.609, c: 0.126 },
];

/** Surface tints — very low chroma so it reads as warm/cool, not colored. */
const SURFACE_TINTS: { token: string; l: number; c: number }[] = [
  { token: "surface-bg", l: 0.1, c: 0.006 },
  { token: "surface-card", l: 0.155, c: 0.008 },
  { token: "surface-card-hover", l: 0.18, c: 0.01 },
  { token: "surface-border", l: 0.25, c: 0.012 },
];

/** Text tints — barely perceptible warmth/coolness. */
const TEXT_TINTS: { token: string; l: number; c: number }[] = [
  { token: "text-primary", l: 0.95, c: 0.003 },
  { token: "text-secondary", l: 0.65, c: 0.008 },
  { token: "text-muted", l: 0.45, c: 0.006 },
];

function oklch(l: number, c: number, h: number): string {
  return `oklch(${l} ${c} ${h})`;
}

export function getAccentHue(): number {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v !== null) {
      const n = Number(v);
      if (n >= 0 && n <= 360) return n;
    }
  } catch {
    /* localStorage unavailable */
  }
  return DEFAULT_HUE;
}

export function setAccentHue(hue: number) {
  try {
    localStorage.setItem(STORAGE_KEY, String(Math.round(hue)));
  } catch {
    /* localStorage unavailable */
  }
  applyAccentHue(hue);
}

export function applyAccentHue(hue: number) {
  const root = document.documentElement;
  const h = ((hue % 360) + 360) % 360;
  const h2 = ((h + SECONDARY_OFFSET) % 360 + 360) % 360;

  for (const { shade, l, c } of PRIMARY_SHADES) {
    root.style.setProperty(`--color-amber-${shade}`, oklch(l, c, h));
  }
  for (const { shade, l, c } of SECONDARY_SHADES) {
    root.style.setProperty(`--color-cyan-${shade}`, oklch(l, c, h2));
  }
  // status-warning follows primary accent
  root.style.setProperty("--color-status-warning", oklch(0.769, 0.188, h));

  // surfaces + borders — subtle hue tint
  for (const { token, l, c } of SURFACE_TINTS) {
    root.style.setProperty(`--color-${token}`, oklch(l, c, h));
  }
  // text — barely-there warmth/coolness
  for (const { token, l, c } of TEXT_TINTS) {
    root.style.setProperty(`--color-${token}`, oklch(l, c, h));
  }
  // status-disabled picks up a hint of the theme
  root.style.setProperty("--color-status-disabled", oklch(0.45, 0.005, h));
}

/** Named presets for quick selection. */
export const HUE_PRESETS: { label: string; hue: number }[] = [
  { label: "Rose", hue: 15 },
  { label: "Orange", hue: 45 },
  { label: "Amber", hue: 70 },
  { label: "Lime", hue: 120 },
  { label: "Green", hue: 150 },
  { label: "Teal", hue: 195 },
  { label: "Blue", hue: 240 },
  { label: "Indigo", hue: 270 },
  { label: "Purple", hue: 300 },
  { label: "Pink", hue: 350 },
];

// Apply on import — runs before React render to avoid flash.
applyAccentHue(getAccentHue());
