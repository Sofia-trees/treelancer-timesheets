import { createContext, useContext, useEffect, useState } from "react";
import { api, clearToken, getToken, setToken } from "./api.js";

const AuthCtx = createContext(null);
export const useAuth = () => useContext(AuthCtx);

// Treelancer-only site: opens straight into the demo Treelancer's view, no
// login screen. Still goes through the real magic-link + JWT flow under the
// hood, just triggered automatically instead of requiring a click.
const DEFAULT_TREELANCER_EMAIL = "shahmin@example.com";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  async function loginAsDefault() {
    const r = await api.post("/auth/request-link", { email: DEFAULT_TREELANCER_EMAIL });
    if (!r.magic_link) throw new Error("Dev magic link not available from the server.");
    const token = new URL(r.magic_link).searchParams.get("token");
    const v = await api.post("/auth/verify", { token });
    setToken(v.access_token);
  }

  async function refresh() {
    try {
      setUser(await api.get("/auth/me"));
    } catch {
      clearToken();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    (async () => {
      setLoading(true);
      if (!getToken()) {
        try { await loginAsDefault(); } catch { /* surfaced via loading state */ }
      }
      await refresh();
    })();
  }, []);

  return (
    <AuthCtx.Provider value={{ user, loading }}>
      {children}
    </AuthCtx.Provider>
  );
}
