import { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import { Banner } from "../components/Layout.jsx";
import { DOW, MONTHS, daysInMonth, isWeekend, num, weekdayIdx } from "../util.js";

const PROFILE_KEY = "tt_profile"; // remembered in this browser so nobody retypes each month

const emptyProfile = {
  resource_name: "",
  client_name: "",
  position: "",
  po_code: "",
  line_manager_name: "",
  line_manager_designation: "",
  default_location: "",
  email: "",
};

const emptyRow = () => ({ standard: "", overtime: "", location: "", remarks: "", off: false });

function loadProfile() {
  try {
    return { ...emptyProfile, ...JSON.parse(localStorage.getItem(PROFILE_KEY) || "{}") };
  } catch {
    return { ...emptyProfile };
  }
}

function freshRows(year, month) {
  const map = {};
  for (let d = 1; d <= daysInMonth(year, month); d++) map[d] = emptyRow();
  return map;
}

export default function TimesheetForm() {
  const now = new Date();
  const [profile, setProfile] = useState(loadProfile);
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [year, setYear] = useState(now.getFullYear());
  const [rows, setRows] = useState(() => freshRows(now.getFullYear(), now.getMonth() + 1));
  const [signature, setSignature] = useState("");
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  const nDays = daysInMonth(year, month);

  // Remember the person's details in their browser.
  useEffect(() => {
    localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
  }, [profile]);

  // Keep the daily grid sized to the selected month, preserving what's typed.
  useEffect(() => {
    setRows((prev) => {
      const next = {};
      for (let d = 1; d <= nDays; d++) next[d] = prev[d] || emptyRow();
      return next;
    });
  }, [nDays]);

  function setField(key, value) {
    setProfile((p) => ({ ...p, [key]: value }));
  }
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
  function fillWeekdays8() {
    setRows((r) => {
      const next = { ...r };
      for (let d = 1; d <= nDays; d++) {
        if (isWeekend(year, month, d) || next[d].off) continue;
        next[d] = { ...next[d], standard: 8, location: next[d].location || profile.default_location };
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
    setRows(freshRows(year, month));
  }

  const totals = useMemo(() => {
    let std = 0, ot = 0;
    for (const d in rows) {
      if (rows[d].off) continue;
      std += num(rows[d].standard);
      ot += num(rows[d].overtime);
    }
    return { std, ot };
  }, [rows]);

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

  async function generate() {
    setErr(null);
    if (!profile.resource_name.trim() || !profile.client_name.trim() || !profile.position.trim()) {
      setErr("Please fill in your name, the client and your position before generating the PDF.");
      return;
    }
    setBusy(true);
    try {
      await api.postDownload("/generate-pdf", {
        resource_name: profile.resource_name.trim(),
        client_name: profile.client_name.trim(),
        position: profile.position.trim(),
        po_code: profile.po_code.trim() || null,
        month: Number(month),
        year: Number(year),
        line_manager_name: profile.line_manager_name.trim(),
        line_manager_designation: profile.line_manager_designation.trim(),
        signature_name: (signature || profile.resource_name).trim(),
        email: profile.email.trim() || null,
        entries: buildEntries(),
      }, "timesheet.pdf");
    } catch (e) {
      setErr(e.message || "Could not generate the PDF.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Monthly timesheet</h1>
      <p className="lead">
        Fill in your details and your hours, then generate your PDF timesheet. Your details are
        remembered on this device, so next month you only update the hours.
      </p>
      <Banner kind="err">{err}</Banner>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Your details</h2>
        <div className="row">
          <div>
            <label>Your full name *</label>
            <input value={profile.resource_name} onChange={(e) => setField("resource_name", e.target.value)} placeholder="e.g. Jane Doe" />
          </div>
          <div>
            <label>Client / company *</label>
            <input value={profile.client_name} onChange={(e) => setField("client_name", e.target.value)} placeholder="e.g. NOV Malaysia" />
          </div>
        </div>
        <div className="row">
          <div>
            <label>Position *</label>
            <input value={profile.position} onChange={(e) => setField("position", e.target.value)} placeholder="e.g. Senior Mechanical Engineer" />
          </div>
          <div>
            <label>PO code</label>
            <input value={profile.po_code} onChange={(e) => setField("po_code", e.target.value)} placeholder="Leave blank if unknown (NA)" />
          </div>
        </div>
        <div className="row">
          <div>
            <label>Line manager name</label>
            <input value={profile.line_manager_name} onChange={(e) => setField("line_manager_name", e.target.value)} placeholder="Optional" />
          </div>
          <div>
            <label>Line manager designation</label>
            <input value={profile.line_manager_designation} onChange={(e) => setField("line_manager_designation", e.target.value)} placeholder="Optional" />
          </div>
        </div>
        <div className="row">
          <div>
            <label>Default work location</label>
            <input value={profile.default_location} onChange={(e) => setField("default_location", e.target.value)} placeholder="Used by 'Fill weekdays' — e.g. Remote / Kuala Lumpur" />
          </div>
          <div>
            <label>Email</label>
            <input type="email" value={profile.email} onChange={(e) => setField("email", e.target.value)} placeholder="Optional" />
          </div>
        </div>
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Period</h2>
        <div className="row">
          <div>
            <label>Month</label>
            <select value={month} onChange={(e) => setMonth(Number(e.target.value))}>
              {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
            </select>
          </div>
          <div>
            <label>Year</label>
            <input type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} />
          </div>
        </div>
      </div>

      <h2>Daily hours</h2>
      <div className="toolbar">
        <button className="btn-ghost btn-sm" onClick={fillWeekdays8}>Fill weekdays · 8h standard</button>
        <button className="btn-ghost btn-sm" onClick={weekendsOff}>Mark weekends OFF</button>
        <button className="btn-ghost btn-sm" onClick={clearAll}>Clear all</button>
      </div>

      <div className="grid-wrap">
        <table className="grid">
          <thead>
            <tr>
              <th>Date</th><th>Standard</th><th>Overtime</th><th>Work location</th><th>Remarks / notes</th><th></th>
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
                      <td><input className="num" type="number" min="0" step="0.5"
                                 value={row.standard} onChange={(e) => setDay(d, { standard: e.target.value })} /></td>
                      <td><input className="num" type="number" min="0" step="0.5"
                                 value={row.overtime} onChange={(e) => setDay(d, { overtime: e.target.value })} /></td>
                      <td><input type="text" value={row.location}
                                 onChange={(e) => setDay(d, { location: e.target.value })} /></td>
                    </>
                  )}
                  <td><input type="text" value={row.remarks}
                             onChange={(e) => setDay(d, { remarks: e.target.value })} /></td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    <button className="btn-ghost btn-sm" onClick={() => toggleOff(d)}>{row.off ? "Undo OFF" : "OFF"}</button>
                    {d > 1 && <button className="btn-ghost btn-sm" onClick={() => copyPrev(d)} style={{ marginLeft: 4 }}>Copy ↑</button>}
                  </td>
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

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Generate</h2>
        <div className="row">
          <div>
            <label>Name to sign the PDF</label>
            <input value={signature} onChange={(e) => setSignature(e.target.value)} placeholder={profile.resource_name || "Your full name"} />
          </div>
        </div>
        <p className="muted" style={{ marginTop: 6 }}>Leave blank to sign with your full name above.</p>
        <div style={{ marginTop: 14 }}>
          <button className="btn-gold" onClick={generate} disabled={busy}>
            {busy ? "Generating…" : "Generate PDF →"}
          </button>
        </div>
      </div>
    </>
  );
}
