/** Typed API client with GET cache and inflight dedup. */

import type {
  HealthResponse,
  VPNStatusResponse,
  QBTStatusResponse,
  SystemResponse,
  HistoryResponse,
  ServerListResponse,
  ConfigListResponse,
} from "./types";

const cache = new Map<string, { data: unknown; ts: number }>();
const inflight = new Map<string, Promise<unknown>>();
const CACHE_TTL = 5_000; // 5s — health monitor updates every 30s anyway

async function get<T>(path: string): Promise<T> {
  const now = Date.now();
  const cached = cache.get(path);
  if (cached && now - cached.ts < CACHE_TTL) return cached.data as T;

  const existing = inflight.get(path);
  if (existing) return existing as Promise<T>;

  const promise = fetch(path)
    .then((r) => {
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      return r.json() as Promise<T>;
    })
    .then((data) => {
      cache.set(path, { data, ts: Date.now() });
      inflight.delete(path);
      return data;
    })
    .catch((err) => {
      inflight.delete(path);
      throw err;
    });

  inflight.set(path, promise);
  return promise;
}

export interface AuthResponse {
  authenticated: boolean;
  user?: string;
  login_required?: boolean;
}

export const api = {
  health: () => get<HealthResponse>("/api/v1/health"),
  vpnStatus: () => get<VPNStatusResponse>("/api/v1/vpn/status"),
  qbtStatus: () => get<QBTStatusResponse>("/api/v1/qbt/status"),
  system: () => get<SystemResponse>("/api/v1/system"),
  history: () => get<HistoryResponse>("/api/v1/vpn/history"),
  configs: () => get<ConfigListResponse>("/api/v1/vpn/configs"),
  servers: (country?: string, city?: string) => {
    const params = new URLSearchParams();
    if (country) params.set("country", country);
    if (city) params.set("city", city);
    const qs = params.toString();
    return get<ServerListResponse>(`/api/v1/vpn/servers${qs ? `?${qs}` : ""}`);
  },

  async checkAuth(): Promise<AuthResponse> {
    const r = await fetch("/api/v1/auth/me");
    return r.json();
  },

  async login(username: string, password: string): Promise<boolean> {
    const r = await fetch("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    return r.ok;
  },

  async logout(): Promise<void> {
    await fetch("/api/v1/auth/logout", { method: "POST" });
  },
};
