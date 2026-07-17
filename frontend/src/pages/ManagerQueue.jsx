import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Banner, StatusBadge } from "../components/Layout.jsx";
import { periodLabel } from "../util.js";

const FILTERS = [
  ["submitted", "Awaiting my approval"],
  ["manager_approved", "Approved by me"],
  ["approved", "Fully approved"],
  ["rejected", "Rejected"],
  ["", "All"],
];

export default function ManagerQueue() {
  const [filter, setFilter] = useState("submitted");
  const [rows, setRows] = useState([]);
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(null);

  async function load() {
    setErr(null);
    try {
      const q = filter ? `?status_filter=${filter}` : "";
      setRows(await api.get(`/manager/timesheets${q}`));
    } catch (e) { setErr(e.message); }
  }
  useEffect(() => { load(); }, [filter]);

  async function act(id, kind) {
    setBusy(id); setErr(null); setMsg(null);
    try {
      if (kind === "approve") {
        await api.post(`/manager/timesheets/${id}/approve`);
        setMsg("Approved and forwarded to Trees Engineering.");
      } else {
        const reason = prompt("Reason for returning this timesheet to the Treelancer:");
        if (!reason) { setBusy(null); return; }
        await api.post(`/manager/timesheets/${id}/reject`, { reason });
        setMsg("Returned to the Treelancer.");
      }
      await load();
    } catch (e) { setErr(e.message); } finally { setBusy(null); }
  }

  return (
    <>
      <h1>Approvals</h1>
      <p className="lead">Review and approve your team's timesheets. Approved sheets go to Trees Engineering for final sign-off.</p>

      <div className="toolbar">
        {FILTERS.map(([v, label]) => (
          <button key={label} className={`btn-sm ${filter === v ? "" : "btn-ghost"}`} onClick={() => setFilter(v)}>{label}</button>
        ))}
      </div>
      <Banner kind="err">{err}</Banner>
      <Banner kind="info">{msg}</Banner>

      {rows.length === 0 ? (
        <p className="muted">Nothing here.</p>
      ) : (
        <div className="card" style={{ padding: 0 }}>
          <table>
            <thead><tr><th>Treelancer</th><th>Period</th><th>Std</th><th>OT</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>{r.resource_name}<div className="muted">{r.position}</div></td>
                  <td>{periodLabel(r.billing_period)}</td>
                  <td>{Number(r.total_standard_hours)}</td>
                  <td>{Number(r.total_overtime_hours)}</td>
                  <td><StatusBadge status={r.status} /></td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    {r.status === "submitted" && (
                      <>
                        <button className="btn-sm" disabled={busy === r.id} onClick={() => act(r.id, "approve")}>Approve</button>
                        <button className="btn-sm btn-danger" disabled={busy === r.id} onClick={() => act(r.id, "reject")} style={{ marginLeft: 6 }}>Return</button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
