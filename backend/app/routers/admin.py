"""Trees Engineering admin (finance/ops) endpoints: see everything, final
sign-off, download, and bulk export."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_role
from app.db import get_db
from app.models import Assignment, Timesheet, TimesheetStatus, User, UserRole
from app.schemas import RejectRequest, TimesheetDetail, TimesheetSummary
from app.services import exporter, timesheet_service as svc

router = APIRouter(prefix="/admin", tags=["admin"])
_guard = require_role(UserRole.ADMIN)


def _month_bounds(year: int, month: int) -> date:
    return date(year, month, 1)


@router.get("/timesheets", response_model=list[TimesheetSummary])
def list_all(
    status_filter: TimesheetStatus | None = None,
    client_id: uuid.UUID | None = None,
    freelancer_id: uuid.UUID | None = None,
    month: int | None = None,
    year: int | None = None,
    _: User = Depends(_guard),
    db: Session = Depends(get_db),
):
    stmt = select(Timesheet).join(Assignment, Assignment.id == Timesheet.assignment_id)
    if status_filter is not None:
        stmt = stmt.where(Timesheet.status == status_filter)
    if client_id is not None:
        stmt = stmt.where(Assignment.client_id == client_id)
    if freelancer_id is not None:
        stmt = stmt.where(Timesheet.freelancer_id == freelancer_id)
    if month is not None and year is not None:
        stmt = stmt.where(Timesheet.billing_period == _month_bounds(year, month))
    stmt = stmt.order_by(Timesheet.billing_period.desc(), Timesheet.client_project)
    return db.scalars(stmt.options(selectinload(Timesheet.entries))).all()


@router.get("/timesheets/{ts_id}", response_model=TimesheetDetail)
def detail(ts_id: uuid.UUID, _: User = Depends(_guard), db: Session = Depends(get_db)):
    return svc._load(db, ts_id)


@router.post("/timesheets/{ts_id}/approve", response_model=TimesheetDetail)
def approve(ts_id: uuid.UUID, admin: User = Depends(_guard), db: Session = Depends(get_db)):
    return svc.admin_approve(db, svc._load(db, ts_id), admin)


@router.post("/timesheets/{ts_id}/reject", response_model=TimesheetDetail)
def reject(ts_id: uuid.UUID, body: RejectRequest, admin: User = Depends(_guard), db: Session = Depends(get_db)):
    return svc.reject(db, svc._load(db, ts_id), admin, body.reason, by_manager=False)


@router.get("/timesheets/{ts_id}/pdf")
def download_pdf(ts_id: uuid.UUID, _: User = Depends(_guard), db: Session = Depends(get_db)):
    ts = svc._load(db, ts_id)
    return Response(
        content=exporter.timesheet_pdf(ts),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{exporter.pdf_filename(ts)}"'},
    )


@router.get("/export")
def bulk_export(
    client_id: uuid.UUID,
    month: int,
    year: int,
    status_filter: TimesheetStatus = TimesheetStatus.APPROVED,
    _: User = Depends(_guard),
    db: Session = Depends(get_db),
):
    """ZIP of PDFs for a client + month (approved by default), ready to send to
    the client or feed the invoice system."""
    rows = db.scalars(
        select(Timesheet)
        .join(Assignment, Assignment.id == Timesheet.assignment_id)
        .where(
            Assignment.client_id == client_id,
            Timesheet.billing_period == _month_bounds(year, month),
            Timesheet.status == status_filter,
        )
        .options(selectinload(Timesheet.entries))
    ).all()
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No matching timesheets to export")
    fname = f"timesheets_{year}-{month:02d}.zip"
    return Response(
        content=exporter.bulk_zip(rows),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
