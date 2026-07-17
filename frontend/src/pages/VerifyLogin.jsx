import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Banner } from "../components/Layout.jsx";

export default function VerifyLogin() {
  const [params] = useSearchParams();
  const { completeLogin } = useAuth();
  const navigate = useNavigate();
  const [err, setErr] = useState(null);
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return; // token is single-use — never verify twice
    ran.current = true;
    const token = params.get("token");
    if (!token) { setErr("Missing sign-in token."); return; }
    (async () => {
      try {
        const r = await api.post("/auth/verify", { token });
        await completeLogin(r.access_token);
        navigate("/", { replace: true });
      } catch (e) {
        setErr(e.message);
      }
    })();
  }, []);

  return (
    <div className="narrow">
      <h1>Signing you in…</h1>
      {err ? (
        <>
          <Banner kind="err">{err}</Banner>
          <a href="/">Back to sign in</a>
        </>
      ) : (
        <p className="muted">One moment.</p>
      )}
    </div>
  );
}
