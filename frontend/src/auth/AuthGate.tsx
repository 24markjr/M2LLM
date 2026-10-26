/**
 * The sign-in gate (v4 Phase 1a). Nothing renders until the API says who is signed in; a 401 from
 * any later request (session expired, signed out elsewhere, account deactivated) brings the sign-in
 * page back instead of a page full of errors. The static GitHub Pages preview has no accounts.
 */

import { createContext, useCallback, useContext, useEffect, useState, type FormEvent, type ReactNode } from "react";

import { api, ApiError, SIGNED_OUT, type User } from "../api/client";
import { STATIC_DEMO } from "../api/demo";
import "./auth.css";

const UserContext = createContext<{ user: User | null; signOut: () => void }>({ user: null, signOut: () => undefined });

export function useUser(): { user: User | null; signOut: () => void } {
  return useContext(UserContext);
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [state, setState] = useState<"checking" | "in" | "out" | "unreachable">(STATIC_DEMO ? "in" : "checking");

  const check = useCallback(() => {
    if (STATIC_DEMO) return;
    api
      .me()
      .then((u) => {
        setUser(u);
        setState("in");
      })
      .catch((exc: unknown) => setState(exc instanceof ApiError && exc.status === 401 ? "out" : "unreachable"));
  }, []);

  useEffect(check, [check]);
  useEffect(() => {
    const out = () => {
      setUser(null);
      setState("out");
    };
    window.addEventListener(SIGNED_OUT, out);
    return () => window.removeEventListener(SIGNED_OUT, out);
  }, []);

  const signOut = useCallback(() => {
    void api.logout().finally(() => {
      setUser(null);
      setState("out");
    });
  }, []);

  if (state === "checking") return <div className="auth-wait">Opening JARVIS.</div>;
  if (state === "unreachable") {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>JARVIS</h1>
          <p>The engine is not reachable. Start it with scripts\start-jarvis.ps1, then try again.</p>
          <button type="button" className="ui-button primary" onClick={check}>
            Try again
          </button>
        </div>
      </div>
    );
  }
  if (state === "out") return <SignIn onIn={(u) => (setUser(u), setState("in"))} />;
  return <UserContext.Provider value={{ user, signOut }}>{children}</UserContext.Provider>;
}

function SignIn({ onIn }: { onIn: (user: User) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      onIn(await api.login(email, password));
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : "Signing in failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={(e) => void submit(e)}>
        <h1>
          <span className="auth-mark">J</span> JARVIS
        </h1>
        <p className="auth-sub">Sign in to your organisation's investigations.</p>
        <label>
          Email
          <input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
        </label>
        <label>
          Password
          <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {error ? (
          <p className="auth-error" role="alert">
            {error}
          </p>
        ) : null}
        <button type="submit" className="ui-button primary" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <p className="auth-note">No account? Ask your organisation's administrator.</p>
      </form>
    </div>
  );
}
