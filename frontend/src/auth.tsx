import { createContext, useCallback, useContext, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { api, type Me } from "./api";

interface AuthContextValue { me: Me; signOut: () => Promise<void> }
const AuthContext = createContext<AuthContextValue | null>(null);

export function useMe(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useMe outside AuthProvider");
  return ctx;
}

type Stage = { kind: "loading" } | { kind: "signin" } | { kind: "verify" } | { kind: "enroll"; secret?: string; uri?: string } | { kind: "in"; me: Me };

/** Step 17: nothing renders until the user has signed in and passed multi-factor authentication. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [stage, setStage] = useState<Stage>({ kind: "loading" });

  const refresh = useCallback(async () => {
    try {
      const me = await api.me();
      setStage(me.mfa_verified || !me.mfa_required ? { kind: "in", me } : { kind: "verify" });
    } catch {
      setStage({ kind: "signin" });
    }
  }, []);

  useEffect(() => {
    refresh();
    const onExpired = () => setStage({ kind: "signin" });
    window.addEventListener("auth-required", onExpired);
    return () => window.removeEventListener("auth-required", onExpired);
  }, [refresh]);

  const signOut = async () => {
    await api.logout().catch(() => undefined);
    setStage({ kind: "signin" });
  };

  if (stage.kind === "in") return <AuthContext.Provider value={{ me: stage.me, signOut }}>{children}</AuthContext.Provider>;
  if (stage.kind === "loading") return <main className="auth-page muted">Loading…</main>;
  return <SignIn stage={stage} setStage={setStage} onDone={refresh} />;
}

function SignIn({ stage, setStage, onDone }: { stage: Stage; setStage: (s: Stage) => void; onDone: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(fn: () => Promise<void>) {
    setBusy(true); setError(null);
    try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  const login = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      const r = await api.login(username, password);
      setPassword("");
      if (r.mfa === "none") return onDone();
      if (r.mfa === "verify") return setStage({ kind: "verify" });
      const enrol = await api.mfaEnroll();
      setStage({ kind: "enroll", secret: enrol.secret, uri: enrol.otpauth_uri });
    });
  };
  const submitCode = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      await (stage.kind === "enroll" ? api.mfaConfirm(code) : api.mfaVerify(code));
      setCode("");
      onDone();
    });
  };

  return (
    <main className="auth-page">
      <section className="card auth-card">
        <div className="wordmark"><span className="wordmark-mark" aria-hidden="true">RE</span><span>Requirements Desk</span></div>
        {stage.kind === "signin" && (
          <form className="stack" onSubmit={login}>
            <h1>Sign in</h1>
            <label htmlFor="u">Username<input id="u" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} /></label>
            <label htmlFor="p">Password<input id="p" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
            <button className="primary" disabled={busy || !username || !password}>{busy ? "Signing in…" : "Continue"}</button>
          </form>
        )}
        {(stage.kind === "verify" || stage.kind === "enroll") && (
          <form className="stack" onSubmit={submitCode}>
            <h1>{stage.kind === "enroll" ? "Set up two-step verification" : "Two-step verification"}</h1>
            {stage.kind === "enroll" && stage.secret && (
              <div className="stack small">
                <p>Multi-factor authentication is required. Add this account to an authenticator app (Microsoft or Google
                  Authenticator, 1Password…) with the key below, then enter the 6-digit code it shows.</p>
                <code className="secret" aria-label="Authenticator key">{stage.secret.match(/.{1,4}/g)?.join(" ")}</code>
                <details><summary className="muted">Setup link</summary><code className="secret small">{stage.uri}</code></details>
              </div>
            )}
            <label htmlFor="code">6-digit code
              <input id="code" inputMode="numeric" autoComplete="one-time-code" maxLength={8} value={code} onChange={(e) => setCode(e.target.value)} />
            </label>
            <button className="primary" disabled={busy || code.trim().length < 6}>{busy ? "Checking…" : "Verify"}</button>
            <button type="button" className="link" onClick={() => setStage({ kind: "signin" })}>Use another account</button>
          </form>
        )}
        {error && <div className="alert error">{error}</div>}
        <p className="muted small">Sessions end after 30 minutes of inactivity. Every action is recorded under your account.</p>
      </section>
    </main>
  );
}
