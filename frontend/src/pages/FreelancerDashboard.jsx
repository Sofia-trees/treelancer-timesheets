import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { Banner, StatusBadge } from "../components/Layout.jsx";
import { MONTHS, periodLabel } from "../util.js";

export default function FreelancerDashboard() {
  const navigate = useNavigate();
  const [assignments, setAssignments] = useState([]);
  const [sheets, setSheets] = useState([]);
  const [err, setErr] = useState(null);
  const now = new Date();
  const [assignmentId, setAssignmentId] = useState("");
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [year, setYear] = useState(now.getFullYear());
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const [a, s] = await Promise.all([api.get("/assignments/mine"), api.get("/timesheets")]);
      setAssignments(a);
      setSheets(s);
      if (a.length && !assignmentId) setAssignmentId(a[0].id);
    } catch (e) { setErr(e.message); }
  }
  useEffect(() => { load(); }, []);

  async function openOrCreate(e) {
    e.preventDefault();
    setErr(null); setBusy(true);
    try {
      const ts = await api.post("/timesheets", { assignment_id: assignmentId, month: Number(month), year: Number(year) });
      navigate(`/timesheets/${ts.id}`);
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  const selected = assignments.find((a) => a.id === assignmentId);

  return (
    <>
      <h1>Your timesheets</h1>
      <p className="lead">Fill in and submit your monthly hours. Your client, position and PO are pre-filled from your assignment.</p>
      <Banner kind="err">{err}</Banner>

      {assignments.length === 0 ? (
        <div className="card"><p className="muted">You have no active assignment yet. Ask Trees Engineering ops to set one up.</p></div>
      ) : (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>Start / open a month</h2>
          <form onSubmit={openOrCreate}>
            <div className="row">
              <div>
                <label>Assignment</label>
                <select value={assignmentId} onChange={(e) => setAssignmentId(e.target.value)}>
                  {assignments.map((a) => (
                    <option key={a.id} value={a.id}>{a.position} · {a.po_code || "NA"}</option>
                  ))}
                </select>
              </div>
              <div>
                <label>Month</label>
                <select value={month} onChange={(e) => setMonth(e.target.value)}>
                  {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
                </select>
              </div>
              <div>
                <label>Year</label>
                <input type="number" value={year} onChange={(e) => setYear(e.target.value)} />
              </div>
            </div>
            {selected && (
              <p className="muted" style={{ marginTop: 10 }}>
                Line manager: {selected.line_manager_name || "—"} · Default location: {selected.default_work_location || "—"}
              </p>
            )}
            <div style={{ marginTop: 14 }}>
              <button disabled={busy}>{busy ? "Opening…" : "Open timesheet →"}</button>
            </div>
          </form>
        </div>
      )}

      <h2>History</h2>
      {sheets.length === 0 ? (
        <p className="muted">No timesheets yet.</p>
      ) : (
        <div className="card" style={{ padding: 0 }}>
          <table>
            <thead>
              <tr><th>Period</th><th>Client</th><th>Std</th><th>OT</th><th>Status</th></tr>
            </thead>
            <tbody>
              {sheets.map((s) => (
                <tr key={s.id} className="clickable" onClick={() => navigate(`/timesheets/${s.id}`)}>
                  <td>{periodLabel(s.billing_period)}</td>
                  <td>{s.client_project}</td>
                  <td>{Number(s.total_standard_hours)}</td>
                  <td>{Number(s.total_overtime_hours)}</td>
                  <td><StatusBadge status={s.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
