import { useState } from "react";
import { api } from "../api.js";
import { Banner } from "../components/Layout.jsx";

export default function Login() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(null);
  const [devLink, setDevLink] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setErr(null); setBusy(true); setDevLink(null); setSent(null);
    try {
      const r = await api.post("/auth/request-link", { email });
      setSent(r.detail);
      if (r.magic_link) setDevLink(r.magic_link); // dev convenience, no email sending set up yet
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="narrow">
      <h1>Sign in</h1>
      <p className="lead">Enter your email and we'll send you a secure sign-in link — no password needed.</p>
      <div className="card">
        <form onSubmit={submit}>
          <label htmlFor="email">Email address</label>
          <input id="email" type="email" required placeholder="you@company.com"
                 value={email} onChange={(e) => setEmail(e.target.value)} />
          <div style={{ marginTop: 16 }}>
            <button disabled={busy || !email}>{busy ? "Sending…" : "Send sign-in link"}</button>
          </div>
        </form>
        <Banner kind="err">{err}</Banner>
        {sent && <Banner kind="info">{sent}</Banner>}
        {devLink && (
          <Banner kind="warn">
            Email sending isn't wired up yet — use this link to continue:{" "}
            <a href={devLink}>Open sign-in link</a>
          </Banner>
        )}
      </div>
      <p className="muted" style={{ marginTop: 12 }}>
        Don't have access yet? Ask Trees Engineering to set up your assignment first.
      </p>
    </div>
  );
}
