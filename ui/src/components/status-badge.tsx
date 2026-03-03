import { cn } from "@/lib/utils";

const variants: Record<string, string> = {
  up: "bg-status-up/15 text-status-up border-status-up/30",
  active: "bg-status-up/15 text-status-up border-status-up/30",
  running: "bg-status-up/15 text-status-up border-status-up/30",
  healthy: "bg-status-up/15 text-status-up border-status-up/30",
  down: "bg-status-down/15 text-status-down border-status-down/30",
  error: "bg-status-down/15 text-status-down border-status-down/30",
  stopped: "bg-status-down/15 text-status-down border-status-down/30",
  disabled: "bg-status-disabled/15 text-status-disabled border-status-disabled/30",
  unknown: "bg-status-warning/15 text-status-warning border-status-warning/30",
};

export function StatusBadge({ value }: { value: string }) {
  const style = variants[value.toLowerCase()] ?? variants.unknown;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium uppercase tracking-wide",
        style
      )}
    >
      {value}
    </span>
  );
}
