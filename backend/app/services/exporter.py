"""Render a stored Timesheet to the parser-proof PDF, and bundle many into a ZIP."""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterable

from app.models import Timesheet
from app.pdf.timesheet_pdf import DailyRow, TimesheetPDF, render


def _to_pdf_model(ts: Timesheet) -> TimesheetPDF:
    rows = [
        DailyRow(
            day=e.day,
            standard_hours=e.standard_hours,
            overtime_hours=e.overtime_hours,
            work_location=e.work_location or "",
            remarks=e.remarks or "",
            is_off=e.is_off,
        )
        for e in sorted(ts.entries, key=lambda e: e.day)
    ]
    return TimesheetPDF(
        resource_name=ts.resource_name,
        client_name=ts.client_project,
        position=ts.position,
        po_code=ts.po_code,
        month=ts.billing_period.month,
        year=ts.billing_period.year,
        rows=rows,
        line_manager_name=ts.line_manager_name or "",
        line_manager_designation=ts.line_manager_designation or "",
        signature_name=ts.signature_name or "",
        date_signed=ts.date_signed,
    )


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")


def pdf_filename(ts: Timesheet) -> str:
    return f"{_slug(ts.resource_name)}_{_slug(ts.client_project)}_{ts.billing_period:%Y-%m}.pdf"


def timesheet_pdf(ts: Timesheet) -> bytes:
    return render(_to_pdf_model(ts))


def bulk_zip(timesheets: Iterable[Timesheet]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for ts in timesheets:
            zf.writestr(pdf_filename(ts), timesheet_pdf(ts))
    return buf.getvalue()
