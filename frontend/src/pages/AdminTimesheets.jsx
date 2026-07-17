import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { Banner, StatusBadge } from "../components/Layout.jsx";
import { MONTHS, periodLabel } from "../util.js";

const STATUSES = ["", "submitted", "manager_approved", "approved", "rejected"];

export default function AdminTimesheets() {
  const [clients, setClients] = useState([]);
  const [freelancers, setFreelancers] = useState([]);
  const [rows, setRows] = useState([]);
  const [f, setF] = useState({ status: "", client_id: "", freelancer_id: "", month: "", year: "" });
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        setClients(await api.get("/admin/clients"));
        setFreelancers(await api.get("/admin/users?role=freelancer"));
      } catch (e) { setErr(e.message); }
    })();
  }, []);

  async function load() {
    setErr(null);
    const q = new URLSearchParams();
    if (f.status) q.set("status_filter", f.status);
    if (f.client_id) q.set("client_id", f.client_id);
    if (f.freelancer_id) q.set("freelancer_id", f.freelancer_id);
    if (f.month && f.year) { q.set("month", f.month); q.set("year", f.year); }
    try { setRows(await api.get(`/admin/timesheets?${q.toString()}`)); }
    catch (e) { setErr(e.message); }
  }
  useEffect(() => { load(); }, [f]);

  async function act(id, kind) {
    setBusy(id); setErr(null); setMsg(null);
    try {
      if (kind === "approve") {
        await api.post(`/admin/timesheets/${id}/approve`);
        setMsg("Final approval recorded.");
      } else {
        const reason = prompt("Reason for rejecting:");
        if (!reason) { setBusy(null); return; }
        await api.post(`/admin/timesheets/${id}/reject`, { reason });
        setMsg("Rejected and returned to the Treelancer.");
      }
      await load();
    } catch (e) { setErr(e.message); } finally { setBusy(null); }
  }

  async function bulkExport() {
    setErr(null); setMsg(null);
    if (!f.client_id || !f.month || !f.year) {
      setErr("Pick a client, month and year to bulk-export approved timesheets.");
      return;
    }
    try {
      await api.download(
        `/admin/export?client_id=${f.client_id}&month=${f.month}&year=${f.year}&status_filter=approved`,
        "timesheets.zip"
      );
    } catch (e) { setErr(e.message); }
  }

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  return (
    <>
      <div className="between">
        <div>
          <h1>All timesheets</h1>
          <p className="lead">Review, approve, and export timesheets across all freelancers and clients.</p>
        </div>
        <Link className="btn btn-ghost" to="/admin/assignments">Manage assignments →</Link>
      </div>

      <div className="card">
        <div className="row">
          <div>
            <label>Client</label>
            <select value={f.client_id} onChange={set("client_id")}>
              <option value="">All clients</option>
              {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
          <div>
            <label>Freelancer</label>
            <select value={f.freelancer_id} onChange={set("freelancer_id")}>
              <option value="">All freelancers</option>
              {freelancers.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
            </select>
          </div>
          <div>
            <label>Status</label>
            <select value={f.status} onChange={set("status")}>
              {STATUSES.map((s) => <option key={s} value={s}>{s ? s.replace("_", " ") : "All"}</option>)}
            </select>
          </div>
          <div>
            <label>Month</label>
            <select value={f.month} onChange={set("month")}>
              <option value="">—</option>
              {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
            </select>
          </div>
          <div>
            <label>Year</label>
            <input type="number" placeholder="2024" value={f.year} onChange={set("year")} />
          </div>
        </div>
        <div className="toolbar" style={{ marginBottom: 0 }}>
          <button className="btn-gold btn-sm" onClick={bulkExport}>⬇ Bulk export approved (ZIP)</button>
          <span className="muted" style={{ alignSelf: "center" }}>Needs client + month + year</span>
        </div>
      </div>

      <Banner kind="err">{err}</Banner>
      <Banner kind="info">{msg}</Banner>

      <div className="card" style={{ padding: 0, marginTop: 16 }}>
        <table>
          <thead>
            <tr><th>Treelancer</th><th>Client</th><th>Period</th><th>Std</th><th>OT</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={7} className="muted" style={{ padding: 20 }}>No timesheets match.</td></tr>}
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.resource_name}</td>
                <td>{r.client_project}</td>
                <td>{periodLabel(r.billing_period)}</td>
                <td>{Number(r.total_standard_hours)}</td>
                <td>{Number(r.total_overtime_hours)}</td>
                <td><StatusBadge status={r.status} /></td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <button className="btn-ghost btn-sm" onClick={() => api.download(`/admin/timesheets/${r.id}/pdf`, "timesheet.pdf")}>PDF</button>
                  {r.status === "manager_approved" && (
                    <button className="btn-sm" style={{ marginLeft: 6 }} disabled={busy === r.id} onClick={() => act(r.id, "approve")}>Final approve</button>
                  )}
                  {(r.status === "submitted" || r.status === "manager_approved") && (
                    <button className="btn-sm btn-danger" style={{ marginLeft: 6 }} disabled={busy === r.id} onClick={() => act(r.id, "reject")}>Reject</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
