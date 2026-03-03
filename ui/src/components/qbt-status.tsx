import { Download, Upload, FileDown, HardDrive } from "lucide-react";
import type { QBTStatusResponse } from "@/lib/types";
import { humanSpeed } from "@/lib/utils";
import { StatusBadge } from "./status-badge";

export function QBTStatus({ data }: { data: QBTStatusResponse }) {
  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-5">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <HardDrive className="h-5 w-5 text-amber-400" />
          <h2 className="text-sm font-semibold tracking-wide text-text-primary">
            qBittorrent
          </h2>
        </div>
        <StatusBadge value={data.state} />
      </div>

      {/* Speed display */}
      <div className="mb-4 grid grid-cols-2 gap-3">
        <div className="rounded-lg bg-cyan-500/8 border border-cyan-500/15 px-3 py-2.5 text-center">
          <Download className="mx-auto mb-1 h-4 w-4 text-cyan-400" />
          <div className="font-mono text-base font-medium text-cyan-300">
            {humanSpeed(data.download_speed)}
          </div>
          <div className="text-xs text-text-muted">Download</div>
        </div>
        <div className="rounded-lg bg-amber-500/8 border border-amber-500/15 px-3 py-2.5 text-center">
          <Upload className="mx-auto mb-1 h-4 w-4 text-amber-400" />
          <div className="font-mono text-base font-medium text-amber-300">
            {humanSpeed(data.upload_speed)}
          </div>
          <div className="text-xs text-text-muted">Upload</div>
        </div>
      </div>

      {/* Torrents */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileDown className="h-3.5 w-3.5 text-text-muted" />
            <span className="text-xs text-text-muted">Active</span>
          </div>
          <span className="font-mono text-sm text-text-primary">
            {data.active_torrents}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <HardDrive className="h-3.5 w-3.5 text-text-muted" />
            <span className="text-xs text-text-muted">Total</span>
          </div>
          <span className="font-mono text-sm text-text-primary">
            {data.total_torrents}
          </span>
        </div>
        {data.version && (
          <div className="flex items-center justify-between border-t border-surface-border pt-2">
            <span className="text-xs text-text-muted">Version</span>
            <span className="font-mono text-xs text-text-secondary">
              {data.version}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
