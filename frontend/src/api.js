// Thin API client. Token in localStorage; all calls go through the Vite proxy
// at /api (rewritten to the FastAPI backend), or VITE_API_BASE in prod.
const BASE = import.meta.env.VITE_API_BASE ?? "/api";
const TOKEN_KEY = "tt_token";

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

async function request(method, path, body, { raw = false } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (raw) {
    if (!res.ok) throw new ApiError(res.status, await safeJson(res));
    return res;
  }
  const data = await safeJson(res);
  if (!res.ok) throw new ApiError(res.status, data);
  return data;
}

async function safeJson(res) {
  const text = await res.text();
  try { return text ? JSON.parse(text) : null; } catch { return { detail: text }; }
}

export class ApiError extends Error {
  constructor(status, data) {
    super(data?.detail || `Request failed (${status})`);
    this.status = status;
    this.data = data;
  }
}

export const api = {
  get: (p) => request("GET", p),
  post: (p, b) => request("POST", p, b ?? {}),
  put: (p, b) => request("PUT", p, b),
  patch: (p, b) => request("PATCH", p, b),
  // Download a file (PDF/ZIP) as a blob and trigger a browser save.
  async download(p, fallbackName) {
    const res = await request("GET", p, undefined, { raw: true });
    const blob = await res.blob();
    const cd = res.headers.get("Content-Disposition") || "";
    const m = cd.match(/filename="?([^"]+)"?/);
    const name = m ? m[1] : fallbackName;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = name; a.click();
    URL.revokeObjectURL(url);
  },
};
