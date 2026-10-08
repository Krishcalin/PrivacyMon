// Sign-in screen. Shown by <App> whenever there is no resolved session. On
// success the AuthProvider stores the JWT and the console renders.
import { useState, type FormEvent } from "react";
import { useAuth } from "../lib/auth";

export function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email.trim(), password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-screen">
      <form className="card login-card" onSubmit={onSubmit}>
        <div className="brand" style={{ color: "var(--text)" }}>
          PrivacyMon
          <small style={{ color: "var(--muted)" }}>DPIA Console · DPDP Act 2023</small>
        </div>
        <h2 style={{ margin: "18px 0 4px", fontSize: 18 }}>Sign in</h2>
        <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
          Use the account issued by your platform administrator.
        </p>

        <label htmlFor="email">Email</label>
        <input
          id="email"
          type="email"
          autoComplete="username"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          autoFocus
        />

        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />

        {error && (
          <div className="login-error" role="alert">
            {error}
          </div>
        )}

        <button className="btn primary" type="submit" disabled={busy} style={{ marginTop: 16, width: "100%" }}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
