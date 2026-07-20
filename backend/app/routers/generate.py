"""Open, stateless PDF generation.

The self-service site has no accounts and no database: a Treelancer types their
own header info + daily hours into one form and gets the parser-proof PDF back.
This endpoint takes that payload and renders it with the *unchanged*
``timesheet_pdf`` generator, so the produced PDF still ingests cleanly into the
trees-invoice ``TreelancerParser``.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.pdf.timesheet_pdf import DailyRow, TimesheetPDF, render

router = APIRouter(tags=["generate"])


class GenEntry(BaseModel):
    day: int = Field(ge=1, le=31)
    standard_hours: Decimal = Decimal("0")
    overtime_hours: Decimal = Decimal("0")
    work_location: str | None = None
    remarks: str | None = None
    is_off: bool = False


class GenRequest(BaseModel):
    resource_name: str = ""
    client_name: str = ""
    position: str = ""
    po_code: str | None = None
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2020, le=2100)
    line_manager_name: str = ""
    line_manager_designation: str = ""
    signature_name: str = ""
    email: str | None = None
    entries: list[GenEntry] = []


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_") or "timesheet"


@router.post("/generate-pdf")
def generate_pdf(body: GenRequest) -> Response:
    rows = [
        DailyRow(
            day=e.day,
            standard_hours=e.standard_hours,
            overtime_hours=e.overtime_hours,
            work_location=e.work_location or "",
            remarks=e.remarks or "",
            is_off=e.is_off,
        )
        for e in sorted(body.entries, key=lambda e: e.day)
    ]
    model = TimesheetPDF(
        resource_name=body.resource_name,
        client_name=body.client_name,
        position=body.position,
        po_code=body.po_code,
        month=body.month,
        year=body.year,
        rows=rows,
        line_manager_name=body.line_manager_name,
        line_manager_designation=body.line_manager_designation,
        signature_name=body.signature_name,
        date_signed=date.today() if body.signature_name.strip() else None,
        email=(body.email or None),
    )
    pdf = render(model)
    fname = f"{_slug(body.resource_name)}_{_slug(body.client_name)}_{body.year}-{body.month:02d}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
