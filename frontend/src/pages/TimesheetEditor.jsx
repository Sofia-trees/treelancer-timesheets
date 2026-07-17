import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api.js";
import { Banner, StatusBadge } from "../components/Layout.jsx";
import { DOW, daysInMonth, isWeekend, num, periodLabel, weekdayIdx } from "../util.js";

const emptyRow = () => ({ standard: "", overtime: "", location: "", remarks: "", off: false });

export default function TimesheetEditor() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [ts, setTs] = useState(null);
  const [rows, setRows] = useState({});
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const [sigName, setSigName] = useState("");
  const [confirm, setConfirm] = useState(false);

  const [year, month] = ts ? ts.billing_period.split("-").map(Number) : [0, 0];
  const nDays = ts ? daysInMonth(year, month) : 0;
  const editable = ts && (ts.status === "draft" || ts.status === "rejected");

  function hydrate(detail) {
    setTs(detail);
    setSigName(detail.signature_name || detail.resource_name || "");
    const [y, m] = detail.billing_period.split("-").map(Number);
    const map = {};
    for (let d = 1; d <= daysInMonth(y, m); d++) map[d] = emptyRow();
    for (const e of detail.entries) {
      map[e.day] = {
        standard: e.is_off ? "" : (Number(e.standard_hours) || ""),
        overtime: e.is_off ? "" : (Number(e.overtime_hours) || ""),
        location: e.work_location || "",
        remarks: e.remarks || "",
        off: e.is_off,
      };
    }
    setRows(map);
  }

  async function load() {
    try { hydrate(await api.get(`/timesheets/${id}`)); }
    catch (e) { setErr(e.message); }
  }
  useEffect(() => { load(); }, [id]);

  const totals = useMemo(() => {
    let std = 0, ot = 0;
    for (const d in rows) {
      if (rows[d].off) continue;
      std += num(rows[d].standard);
      ot += num(rows[d].overtime);
    }
    return { std, ot };
  }, [rows]);

  function setDay(day, patch) {
    setRows((r) => ({ ...r, [day]: { ...r[day], ...patch } }));
  }
  function toggleOff(day) {
    setRows((r) => {
      const cur = r[day];
      const off = !cur.off;
      return { ...r, [day]: { ...cur, off, standard: off ? "" : cur.standard, overtime: off ? "" : cur.overtime } };
    });
  }

  // ---- quick-fill helpers ----
  const defaultLoc = ts?.entries?.[0]?.work_location || "";
  function fillWeekdays8() {
    setRows((r) => {
      const next = { ...r };
      for (let d = 1; d <= nDays; d++) {
        if (isWeekend(year, month, d) || next[d].off) continue;
        next[d] = { ...next[d], standard: 8, location: next[d].location || defaultLoc };
      }
      return next;
    });
  }
  function weekendsOff() {
    setRows((r) => {
      const next = { ...r };
      for (let d = 1; d <= nDays; d++)
        if (isWeekend(year, month, d)) next[d] = { ...next[d], off: true, standard: "", overtime: "" };
      return next;
    });
  }
  function copyPrev(day) {
    if (day <= 1) return;
    setRows((r) => ({ ...r, [day]: { ...r[day - 1] } }));
  }
  function clearAll() {
    const map = {};
    for (let d = 1; d <= nDays; d++) map[d] = emptyRow();
    setRows(map);
  }

  function buildEntries() {
    const out = [];
    for (let d = 1; d <= nDays; d++) {
      const row = rows[d];
      const has = row.off || num(row.standard) || num(row.overtime) || row.location || row.remarks;
      if (!has) continue;
      out.push({
        day: d,
        standard_hours: row.off ? "0" : String(num(row.standard)),
        overtime_hours: row.off ? "0" : String(num(row.overtime)),
        work_location: row.off ? null : (row.location || null),
        remarks: row.remarks || null,
        is_off: row.off,
      });
    }
    return out;
  }

  async function save() {
    setErr(null); setMsg(null); setBusy(true);
    try {
      hydrate(await api.put(`/timesheets/${id}/entries`, { entries: buildEntries() }));
      setMsg("Saved.");
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  async function submit() {
    setErr(null); setMsg(null); setBusy(true);
    try {
      await api.put(`/timesheets/${id}/entries`, { entries: buildEntries() }); // persist latest edits first
      hydrate(await api.post(`/timesheets/${id}/submit`, { signature_name: sigName, confirm }));
      setMsg("Submitted for approval.");
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  if (!ts) return <Banner kind="err">{err || "Loading…"}</Banner>;

  return (
    <>
      <div className="between">
        <div>
          <a onClick={() => navigate("/dashboard")} style={{ cursor: "pointer" }}>← Dashboard</a>
          <h1 style={{ marginTop: 6 }}>{periodLabel(ts.billing_period)} — {ts.resource_name}</h1>
        </div>
        <StatusBadge status={ts.status} />
      </div>

      <div className="card">
        <div className="row">
          <div><label>Client</label><div>{ts.client_project}</div></div>
          <div><label>Position</label><div>{ts.position}</div></div>
          <div><label>PO Code</label><div>{ts.po_code || "NA"}</div></div>
          <div><label>Line Manager</label><div>{ts.line_manager_name || "—"}</div></div>
        </div>
      </div>

      {ts.status === "rejected" && ts.rejection_reason && (
        <Banner kind="warn"><b>Returned for changes:</b> {ts.rejection_reason}</Banner>
      )}
      <Banner kind="err">{err}</Banner>
      <Banner kind="info">{msg}</Banner>

      {editable && (
        <div className="toolbar">
          <button className="btn-ghost btn-sm" onClick={fillWeekdays8}>Fill weekdays · 8h standard</button>
          <button className="btn-ghost btn-sm" onClick={weekendsOff}>Mark weekends OFF</button>
          <button className="btn-ghost btn-sm" onClick={clearAll}>Clear all</button>
        </div>
      )}

      <div className="grid-wrap">
        <table className="grid">
          <thead>
            <tr>
              <th>Date</th><th>Standard</th><th>Overtime</th><th>Work location</th><th>Remarks / notes</th>
              {editable && <th></th>}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: nDays }, (_, i) => i + 1).map((d) => {
              const row = rows[d] || emptyRow();
              const wknd = isWeekend(year, month, d);
              return (
                <tr key={d} className={row.off ? "off" : wknd ? "weekend" : ""}>
                  <td className="daycell">{d}<div className="dow">{DOW[weekdayIdx(year, month, d)]}</div></td>
                  {row.off ? (
                    <td colSpan={3} style={{ textAlign: "center" }}><span className="off-tag">OFF</span></td>
                  ) : (
                    <>
                      <td><input className="num" type="number" min="0" step="0.5" disabled={!editable}
                                 value={row.standard} onChange={(e) => setDay(d, { standard: e.target.value })} /></td>
                      <td><input className="num" type="number" min="0" step="0.5" disabled={!editable}
                                 value={row.overtime} onChange={(e) => setDay(d, { overtime: e.target.value })} /></td>
                      <td><input type="text" disabled={!editable} value={row.location}
                                 onChange={(e) => setDay(d, { location: e.target.value })} /></td>
                    </>
                  )}
                  <td><input type="text" disabled={!editable} value={row.remarks}
                             onChange={(e) => setDay(d, { remarks: e.target.value })} /></td>
                  {editable && (
                    <td style={{ whiteSpace: "nowrap" }}>
                      <button className="btn-ghost btn-sm" onClick={() => toggleOff(d)}>{row.off ? "Undo OFF" : "OFF"}</button>
                      {d > 1 && <button className="btn-ghost btn-sm" onClick={() => copyPrev(d)} style={{ marginLeft: 4 }}>Copy ↑</button>}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="totals">
        <div>Total standard <b>{totals.std}</b></div>
        <div>Total overtime <b>{totals.ot}</b></div>
      </div>

      {editable ? (
        <div className="card">
          <div className="flex">
            <button className="btn-ghost" onClick={save} disabled={busy}>Save draft</button>
            <div className="spacer" />
          </div>
          <h2>Submit for approval</h2>
          <p className="muted">Submitting locks the timesheet and sends it to your line manager, then Trees Engineering.</p>
          <label>Type your full name to e-sign</label>
          <input value={sigName} onChange={(e) => setSigName(e.target.value)} />
          <div className="checkline">
            <input id="confirm" type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />
            <label htmlFor="confirm" style={{ margin: 0 }}>
              I confirm the hours above are accurate for {periodLabel(ts.billing_period)}.
            </label>
          </div>
          <button className="btn-gold" onClick={submit} disabled={busy || !confirm || !sigName.trim()}>
            {busy ? "Submitting…" : "Submit timesheet"}
          </button>
        </div>
      ) : (
        <div className="card flex">
          <span className="muted">This timesheet is locked ({ts.status}).</span>
          <div className="spacer" />
          <button onClick={() => api.download(`/timesheets/${id}/pdf`, "timesheet.pdf")}>Download PDF</button>
        </div>
      )}
    </>
  );
}
