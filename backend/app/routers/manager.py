"""Line-manager endpoints (first approval step). A manager only sees timesheets
for their own client, scoped via the assignment's client_id."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_role
from app.db import get_db
from app.models import Assignment, Timesheet, TimesheetStatus, User, UserRole
from app.schemas import RejectRequest, TimesheetDetail, TimesheetSummary
from app.services import timesheet_service as svc

router = APIRouter(prefix="/manager", tags=["manager"])
_guard = require_role(UserRole.LINE_MANAGER)


def _scoped(db: Session, ts_id: uuid.UUID, mgr: User) -> Timesheet:
    ts = svc._load(db, ts_id)
    assignment = db.get(Assignment, ts.assignment_id)
    if assignment is None or assignment.client_id != mgr.client_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Timesheet is not for your client")
    return ts


@router.get("/timesheets", response_model=list[TimesheetSummary])
def list_for_client(
    status_filter: TimesheetStatus | None = None,
    mgr: User = Depends(_guard),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Timesheet)
        .join(Assignment, Assignment.id == Timesheet.assignment_id)
        .where(Assignment.client_id == mgr.client_id)
        .order_by(Timesheet.submitted_at.desc().nullslast())
    )
    if status_filter is not None:
        stmt = stmt.where(Timesheet.status == status_filter)
    else:
        # Default view: everything that has left Draft.
        stmt = stmt.where(Timesheet.status != TimesheetStatus.DRAFT)
    return db.scalars(stmt.options(selectinload(Timesheet.entries))).all()


@router.post("/timesheets/{ts_id}/approve", response_model=TimesheetDetail)
def approve(ts_id: uuid.UUID, mgr: User = Depends(_guard), db: Session = Depends(get_db)):
    return svc.manager_approve(db, _scoped(db, ts_id, mgr), mgr)


@router.post("/timesheets/{ts_id}/reject", response_model=TimesheetDetail)
def reject(ts_id: uuid.UUID, body: RejectRequest, mgr: User = Depends(_guard), db: Session = Depends(get_db)):
    return svc.reject(db, _scoped(db, ts_id, mgr), mgr, body.reason, by_manager=True)
