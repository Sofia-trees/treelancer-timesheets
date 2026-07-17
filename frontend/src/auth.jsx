import { createContext, useContext, useEffect, useState } from "react";
import { api, clearToken, getToken, setToken } from "./api.js";

const AuthCtx = createContext(null);
export const useAuth = () => useContext(AuthCtx);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  async function refresh() {
    if (!getToken()) { setUser(null); setLoading(false); return; }
    try {
      setUser(await api.get("/auth/me"));
    } catch {
      clearToken();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh(); }, []);

  async function completeLogin(accessToken) {
    setToken(accessToken);
    setLoading(true);
    await refresh();
  }

  function logout() {
    clearToken();
    setUser(null);
  }

  return (
    <AuthCtx.Provider value={{ user, loading, completeLogin, logout }}>
      {children}
    </AuthCtx.Provider>
  );
}
