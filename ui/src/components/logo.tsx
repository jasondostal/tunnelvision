export function Logo({ className = "h-6 w-6" }: { className?: string }) {
  return (
    <img
      src="/tunnelvision-icon.svg"
      alt="TunnelVision"
      className={className}
    />
  );
}
