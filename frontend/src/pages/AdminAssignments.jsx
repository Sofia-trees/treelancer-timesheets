import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { Banner } from "../components/Layout.jsx";

export default function AdminAssignments() {
  const [clients, setClients] = useState([]);
  const [freelancers, setFreelancers] = useState([]);
  const [managers, setManagers] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);

  async function reload() {
    setErr(null);
    try {
      const [c, f, m, a] = await Promise.all([
        api.get("/admin/clients"),
        api.get("/admin/users?role=freelancer"),
        api.get("/admin/users?role=line_manager"),
        api.get("/admin/assignments"),
      ]);
      setClients(c); setFreelancers(f); setManagers(m); setAssignments(a);
    } catch (e) { setErr(e.message); }
  }
  useEffect(() => { reload(); }, []);

  function ok(text) { setMsg(text); setErr(null); reload(); }
  function fail(e) { setErr(e.message); }

  const clientName = (id) => clients.find((c) => c.id === id)?.name || "—";
  const userName = (list, id) => list.find((u) => u.id === id)?.full_name || "—";

  return (
    <>
      <div className="between">
        <div>
          <h1>Assignment management</h1>
          <p className="lead">
            Fill in a new placement — company, Treelancer, and line manager are typed in directly.
            Nothing to pick from a preset list: new companies and people are created automatically.
          </p>
        </div>
        <Link className="btn btn-ghost" to="/admin">← Timesheets</Link>
      </div>

      <Banner kind="err">{err}</Banner>
      <Banner kind="info">{msg}</Banner>

      <AssignmentFillForm onOk={ok} onFail={fail} />

      <h2>Assignments</h2>
      <div className="card" style={{ padding: 0 }}>
        <table>
          <thead><tr><th>Treelancer</th><th>Client</th><th>Position</th><th>PO</th><th>Line manager</th><th>Active</th></tr></thead>
          <tbody>
            {assignments.length === 0 && <tr><td colSpan={6} className="muted" style={{ padding: 20 }}>No assignments yet — fill in the form above to create one.</td></tr>}
            {assignments.map((a) => (
              <tr key={a.id}>
                <td>{userName(freelancers, a.freelancer_id)}</td>
                <td>{clientName(a.client_id)}</td>
                <td>{a.position}</td>
                <td>{a.po_code || "NA"}</td>
                <td>{a.line_manager_name || userName(managers, a.line_manager_id)}</td>
                <td>{a.is_active ? "Yes" : "No"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

const blank = {
  freelancer_name: "", freelancer_email: "",
  client_name: "",
  line_manager_name: "", line_manager_email: "", line_manager_designation: "",
  position: "", po_code: "", default_work_location: "",
  start_date: new Date().toISOString().slice(0, 10),
};

function AssignmentFillForm({ onOk, onFail }) {
  const [a, setA] = useState(blank);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setA({ ...a, [k]: e.target.value });
  const canSubmit = a.freelancer_name && a.freelancer_email && a.client_name && a.position && a.start_date;

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    try {
      const body = { ...a };
      if (!body.line_manager_email) {
        body.line_manager_name = null;
        body.line_manager_email = null;
        body.line_manager_designation = null;
      }
      body.po_code = body.po_code || null;
      body.default_work_location = body.default_work_location || null;
      await api.post("/admin/assignments/fill", body);
      setA(blank);
      onOk("Assignment created — the company and people involved were added automatically if new.");
    } catch (e) {
      onFail(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card" onSubmit={submit}>
      <h2 style={{ marginTop: 0 }}>New assignment</h2>

      <h2 style={{ fontSize: 14, marginTop: 4 }}>Treelancer</h2>
      <div className="row">
        <div><label>Full name</label><input value={a.freelancer_name} onChange={set("freelancer_name")} placeholder="Jane Doe" /></div>
        <div><label>Email</label><input type="email" value={a.freelancer_email} onChange={set("freelancer_email")} placeholder="jane@example.com" /></div>
      </div>

      <h2 style={{ fontSize: 14 }}>Client company</h2>
      <div className="row">
        <div><label>Company name</label><input value={a.client_name} onChange={set("client_name")} placeholder="Any company — typed freely" /></div>
        <div><label>Position</label><input value={a.position} onChange={set("position")} placeholder="Senior Mechanical Engineer" /></div>
        <div><label>PO code</label><input value={a.po_code} onChange={set("po_code")} placeholder="NA if unknown" /></div>
        <div><label>Default work location</label><input value={a.default_work_location} onChange={set("default_work_location")} placeholder="e.g. KL" /></div>
      </div>

      <h2 style={{ fontSize: 14 }}>Line manager <span className="muted" style={{ fontWeight: 400 }}>(optional — leave blank if not known yet)</span></h2>
      <div className="row">
        <div><label>Full name</label><input value={a.line_manager_name} onChange={set("line_manager_name")} /></div>
        <div><label>Email</label><input type="email" value={a.line_manager_email} onChange={set("line_manager_email")} /></div>
        <div><label>Designation</label><input value={a.line_manager_designation} onChange={set("line_manager_designation")} placeholder="Engineering Manager" /></div>
      </div>

      <div className="row">
        <div><label>Start date</label><input type="date" value={a.start_date} onChange={set("start_date")} /></div>
        <div><label>End date <span className="muted">(optional)</span></label><input type="date" value={a.end_date || ""} onChange={set("end_date")} /></div>
      </div>

      <div style={{ marginTop: 14 }}>
        <button disabled={!canSubmit || busy}>{busy ? "Creating…" : "Create assignment"}</button>
      </div>
    </form>
  );
}
