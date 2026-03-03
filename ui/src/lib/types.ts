/** API response types — mirrors api/models.py */

export interface HealthResponse {
  healthy: boolean;
  vpn: string;
  killswitch: string;
  qbittorrent: string;
  api: string;
  uptime_seconds: number;
  checked_at: string;
}

export interface VPNStatusResponse {
  state: string;
  public_ip: string;
  vpn_ip: string;
  endpoint: string;
  country: string;
  city: string;
  location: string;
  interface: string;
  connected_since: string | null;
  last_handshake: string | null;
  transfer_rx: number;
  transfer_tx: number;
  killswitch: string;
  provider: string;
}

export interface QBTStatusResponse {
  state: string;
  version: string;
  webui_port: number;
  download_speed: number;
  upload_speed: number;
  active_torrents: number;
  total_torrents: number;
}

export interface SystemResponse {
  version: string;
  container_uptime: number;
  vpn_uptime: number | null;
  alpine_version: string;
  qbittorrent_version: string;
  wireguard_version: string;
  python_version: string;
  api_port: number;
  webui_port: number;
}

export interface ConfigResponse {
  vpn_enabled: boolean;
  vpn_provider: string;
  killswitch_enabled: boolean;
  webui_port: number;
  api_port: number;
  ui_enabled: boolean;
  health_check_interval: number;
  timezone: string;
  puid: number;
  pgid: number;
  allowed_networks: string;
}
