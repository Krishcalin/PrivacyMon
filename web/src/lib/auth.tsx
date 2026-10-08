// Session context for the console. Holds the current principal (resolved from
// GET /auth/me), the login/logout actions, and role helpers used to gate UI.
// The JWT itself lives in localStorage (see api.ts); this provider mirrors the
// identity it encodes so components can render without re-fetching.
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api, getToken, setToken, Unauthorized, type Me, type Role } from "./api";

interface AuthState {
  user: Me | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  hasGlobal: (...roles: Role[]) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  // Resolve an existing token on first mount (page reload keeps you signed in).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!getToken()) {
        setLoading(false);
        return;
      }
      try {
        const me = await api.me();
        if (!cancelled) setUser(me);
      } catch {
        setToken(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // A 401 anywhere in the app drops the session back to the login screen.
  useEffect(() => {
    const onError = (e: PromiseRejectionEvent) => {
      if (e.reason instanceof Unauthorized) {
        setToken(null);
        setUser(null);
      }
    };
    window.addEventListener("unhandledrejection", onError);
    return () => window.removeEventListener("unhandledrejection", onError);
  }, []);

  async function login(email: string, password: string) {
    const res = await api.login(email, password);
    setToken(res.access_token);
    setUser(await api.me());
  }

  function logout() {
    setToken(null);
    setUser(null);
  }

  function hasGlobal(...roles: Role[]) {
    return !!user && user.global_roles.some((r) => roles.includes(r));
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, hasGlobal }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
