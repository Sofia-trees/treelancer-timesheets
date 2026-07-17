"""Proof: generate a Treelancer Monthly Timesheet PDF with our generator, then
parse it with the REAL trees-invoice TreelancerParser (unchanged) and assert
every canonical field round-trips.

Run:  python scripts/verify_parser.py
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

# --- wire up both codebases -------------------------------------------------
HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
INVOICE_SCRIPTS = Path.home() / ".claude" / "skills" / "trees-invoice" / "scripts"
sys.path.insert(0, str(PROJECT / "backend"))
sys.path.insert(0, str(INVOICE_SCRIPTS))

from app.pdf.timesheet_pdf import DailyRow, TimesheetPDF, render  # noqa: E402

from treesinvoice.parsers.treelancer import TreelancerParser  # noqa: E402


def build_sample() -> TimesheetPDF:
    # Long name + long position + text PO code = the band-overflow stress case.
    rows: list[DailyRow] = []
    for day in range(1, 32):
        weekday = date(2024, 1, day).weekday()  # 0=Mon
        if weekday >= 5:  # Sat/Sun -> OFF
            rows.append(DailyRow(day=day, is_off=True))
        else:
            ot = Decimal("2.5") if day == 15 else Decimal("0")
            rows.append(
                DailyRow(
                    day=day,
                    standard_hours=Decimal("8"),
                    overtime_hours=ot,
                    work_location="Remote/Kuala Lumpur",
                    remarks="Rotating equipment package review and vendor doc check",
                )
            )
    return TimesheetPDF(
        resource_name="Muhammad Shahmin Bin Ahmad Fadzil",
        client_name="NOV Malaysia",
        position="Senior Mechanical Package Engineer (Rotating)",
        po_code="P-ADMIN -2105 Rev0",
        month=1,
        year=2024,
        rows=rows,
        line_manager_name="Ir. Tan Wei Ming",
        line_manager_designation="Engineering Manager",
        signature_name="Muhammad Shahmin Bin Ahmad Fadzil",
        date_signed=date(2024, 2, 1),
    )


def main() -> int:
    data = build_sample()
    out_pdf = PROJECT / "out" / "sample_timesheet.pdf"
    out_pdf.parent.mkdir(exist_ok=True)
    render(data, out_pdf)
    print(f"Generated: {out_pdf}  ({out_pdf.stat().st_size} bytes)")

    lines = TreelancerParser().parse(out_pdf, client_project="NOV Malaysia")
    assert len(lines) == 1, f"expected 1 canonical line, got {len(lines)}"
    ln = lines[0]

    exp_std = data.total_standard
    exp_ot = data.total_overtime
    checks = [
        ("resource_name", ln.resource_name, data.resource_name),
        ("client_project", ln.client_project, "NOV Malaysia"),
        ("position", ln.position, data.position),
        ("po_code", ln.po_code, data.po_code),
        ("billing_period", ln.billing_period, date(2024, 1, 1)),
        ("standard_hours", ln.standard_hours, exp_std),
        ("overtime_hours", ln.overtime_hours, exp_ot),
        ("extraction_method", ln.extraction_method.value, "text_layer"),
        ("needs_manual_review", ln.needs_manual_review, False),
    ]

    print("\n%-22s %-38s %-38s %s" % ("FIELD", "PARSED", "EXPECTED", "OK"))
    print("-" * 108)
    ok_all = True
    for name, got, exp in checks:
        ok = str(got).strip() == str(exp).strip()
        ok_all &= ok
        print("%-22s %-38s %-38s %s" % (name, str(got)[:38], str(exp)[:38], "PASS" if ok else "FAIL"))

    raw = ln.raw_extracted_value or {}
    print("\nfooter totals match doc:", raw.get("totals_match_document_footer"))
    print("client name on doc     :", raw.get("client_name_on_document"))
    print("daily rows parsed      :", len(raw.get("daily", {})))
    off_days = sum(1 for v in raw.get("daily", {}).values() if "OFF" in (v.get("remarks") or ""))
    worked = sum(
        1 for v in raw.get("daily", {}).values() if Decimal(v.get("standard_hours", "0")) > 0
    )
    print(f"worked days            : {worked}   OFF days: {off_days}")

    print("\nRESULT:", "ALL CHECKS PASSED" if ok_all else "SOME CHECKS FAILED")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
