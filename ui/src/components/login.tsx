import { useState } from "react";
import { LogIn } from "lucide-react";
import { Logo } from "@/components/logo";
import { api } from "@/lib/api";

interface LoginProps {
  onSuccess: () => void;
}

export function Login({ onSuccess }: LoginProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    const ok = await api.login(username, password);
    setLoading(false);

    if (ok) {
      onSuccess();
    } else {
      setError("Invalid credentials");
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <Logo className="mx-auto mb-3 h-10 w-10" />
          <h1 className="text-xl font-bold text-text-primary">TunnelVision</h1>
          <p className="mt-1 text-sm text-text-muted">Sign in to continue</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Username"
              aria-label="Username"
              autoComplete="username"
              autoFocus
              className="w-full rounded-lg border border-surface-border bg-surface-card px-4 py-2.5 text-sm text-text-primary placeholder-text-muted outline-none transition-colors focus:border-amber-500/50"
            />
          </div>
          <div>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              aria-label="Password"
              autoComplete="current-password"
              className="w-full rounded-lg border border-surface-border bg-surface-card px-4 py-2.5 text-sm text-text-primary placeholder-text-muted outline-none transition-colors focus:border-amber-500/50"
            />
          </div>

          {error && (
            <p className="text-center text-sm text-status-down">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading || !username || !password}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-medium text-black transition-colors hover:bg-amber-400 disabled:opacity-50"
          >
            {loading ? (
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-black/30 border-t-black" />
            ) : (
              <LogIn className="h-4 w-4" />
            )}
            Sign in
          </button>
        </form>
      </div>
    </div>
  );
}
