"""End-to-end backend smoke test against a running server (default :8000).
Exercises the full lifecycle: magic-link login for all three roles, timesheet
create -> fill -> submit -> manager approve -> admin approve -> PDF -> ZIP,
plus a reject/resubmit round-trip. Verifies the downloaded PDF with the REAL
invoice parser.

Run (server must be up):  python scripts/smoke_test.py
"""

from __future__ import annotations

import io
import json
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlparse, parse_qs

BASE = "http://127.0.0.1:8077"
HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
sys.path.insert(0, str(PROJECT / "backend"))
sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "trees-invoice" / "scripts"))

_passed = 0
_failed = 0


def check(label: str, cond: bool, extra: str = "") -> None:
    global _passed, _failed
    mark = "PASS" if cond else "FAIL"
    if cond:
        _passed += 1
    else:
        _failed += 1
    print(f"  [{mark}] {label}" + (f"  -- {extra}" if extra and not cond else ""))


def api(method: str, path: str, token: str | None = None, body: dict | None = None, raw: bool = False):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as resp:
            payload = resp.read()
            if raw:
                return resp.status, payload
            return resp.status, (json.loads(payload) if payload else None)
    except urllib.error.HTTPError as e:
        payload = e.read()
        if raw:
            return e.code, payload
        try:
            return e.code, json.loads(payload)
        except Exception:
            return e.code, {"raw": payload.decode(errors="replace")}


def login(email: str) -> str:
    _, r = api("POST", "/auth/request-link", body={"email": email})
    token = parse_qs(urlparse(r["magic_link"]).query)["token"][0]
    _, r2 = api("POST", "/auth/verify", body={"token": token})
    return r2["access_token"]


def main() -> int:
    print("1) Magic-link login (all roles)")
    ftok = login("shahmin@example.com")
    mtok = login("wm.tan@novmalaysia.com")
    atok = login("finance@trees-engineering.com")
    s, me = api("GET", "/auth/me", ftok)
    check("freelancer /auth/me", s == 200 and me["role"] == "freelancer", str(me))

    print("2) Freelancer creates & fills a timesheet")
    _, assigns = api("GET", "/assignments/mine", ftok)
    check("has an assignment", len(assigns) >= 1)
    aid = assigns[0]["id"]
    s, ts = api("POST", "/timesheets", ftok, {"assignment_id": aid, "month": 1, "year": 2024})
    check("create timesheet (draft)", s == 200 and ts["status"] == "draft", str(ts))
    check("header pre-filled from assignment", ts["client_project"] == "NOV Malaysia" and ts["po_code"] == "P-ADMIN -2105 Rev0")
    tid = ts["id"]

    import calendar
    from datetime import date
    entries = []
    for day in range(1, 32):
        if date(2024, 1, day).weekday() >= 5:
            entries.append({"day": day, "is_off": True})
        else:
            entries.append({"day": day, "standard_hours": "8", "overtime_hours": "2.5" if day == 15 else "0",
                            "work_location": "Remote/Kuala Lumpur", "remarks": "Rotating equipment package review"})
    s, ts = api("PUT", f"/timesheets/{tid}/entries", ftok, {"entries": entries})
    from decimal import Decimal as _D
    check("save entries recomputes totals", s == 200 and _D(ts["total_standard_hours"]) == 184 and _D(ts["total_overtime_hours"]) == _D("2.5"), str(ts.get("total_standard_hours")))

    print("3) Access control")
    s, _ = api("GET", f"/timesheets/{tid}", mtok)
    check("manager cannot read via freelancer route (403)", s == 403)
    s, _ = api("GET", "/admin/timesheets", ftok)
    check("freelancer blocked from admin route (403)", s == 403)

    print("4) Submit -> manager approve -> admin approve")
    s, ts = api("POST", f"/timesheets/{tid}/submit", ftok, {"signature_name": me["full_name"], "confirm": True})
    check("submit locks & signs", s == 200 and ts["status"] == "submitted" and ts["date_signed"], str(ts.get("status")))
    s, _ = api("PUT", f"/timesheets/{tid}/entries", ftok, {"entries": entries})
    check("edit after submit blocked (409)", s == 409)
    s, mlist = api("GET", "/manager/timesheets?status_filter=submitted", mtok)
    check("manager sees submitted sheet", s == 200 and any(t["id"] == tid for t in mlist))
    s, _ = api("POST", f"/admin/timesheets/{tid}/approve", atok)
    check("admin cannot final-approve before manager (409)", s == 409)
    s, ts = api("POST", f"/manager/timesheets/{tid}/approve", mtok)
    check("manager approves", s == 200 and ts["status"] == "manager_approved")
    s, ts = api("POST", f"/admin/timesheets/{tid}/approve", atok)
    check("admin final approves", s == 200 and ts["status"] == "approved")

    print("5) Reject / resubmit round-trip (second freelancer)")
    ftok2 = login("khairul@example.com")
    _, ass2 = api("GET", "/assignments/mine", ftok2)
    _, ts2 = api("POST", "/timesheets", ftok2, {"assignment_id": ass2[0]["id"], "month": 2, "year": 2024})
    api("PUT", f"/timesheets/{ts2['id']}/entries", ftok2, {"entries": [{"day": 1, "standard_hours": "8", "work_location": "KL", "remarks": "x"}]})
    _, me2 = api("GET", "/auth/me", ftok2)
    api("POST", f"/timesheets/{ts2['id']}/submit", ftok2, {"signature_name": me2["full_name"], "confirm": True})
    s, ts2 = api("POST", f"/manager/timesheets/{ts2['id']}/reject", mtok, {"reason": "Missing overtime justification"})
    check("manager rejects with reason", s == 200 and ts2["status"] == "rejected" and ts2["rejection_reason"])
    s, ts2 = api("POST", f"/timesheets/{ts2['id']}/submit", ftok2, {"signature_name": me2["full_name"], "confirm": True})
    check("freelancer can resubmit after rejection", s == 200 and ts2["status"] == "submitted")

    print("6) PDF download + parse with the REAL invoice parser")
    s, pdf_bytes = api("GET", f"/admin/timesheets/{tid}/pdf", atok, raw=True)
    check("admin downloads PDF", s == 200 and pdf_bytes[:4] == b"%PDF", f"status={s}")
    tmp = PROJECT / "out" / "downloaded.pdf"
    tmp.parent.mkdir(exist_ok=True)
    tmp.write_bytes(pdf_bytes)
    from treesinvoice.parsers.treelancer import TreelancerParser
    lines = TreelancerParser().parse(tmp, client_project="NOV Malaysia")
    ln = lines[0]
    check("parser: resource_name", ln.resource_name == "Muhammad Shahmin Bin Ahmad Fadzil", ln.resource_name)
    check("parser: totals 184 / 2.5", str(ln.standard_hours) == "184" and str(ln.overtime_hours) == "2.5")
    check("parser: text-layer, no manual review", ln.extraction_method.value == "text_layer" and not ln.needs_manual_review)

    print("7) Bulk ZIP export (approved, client+month)")
    cid = assigns[0]["client_id"]
    s, zbytes = api("GET", f"/admin/export?client_id={cid}&month=1&year=2024&status_filter=approved", atok, raw=True)
    check("admin bulk export returns a zip", s == 200 and zbytes[:2] == b"PK", f"status={s}")
    if s == 200:
        zf = zipfile.ZipFile(io.BytesIO(zbytes))
        check("zip contains the approved PDF", len(zf.namelist()) >= 1, str(zf.namelist()))

    print(f"\nRESULT: {_passed} passed, {_failed} failed")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
