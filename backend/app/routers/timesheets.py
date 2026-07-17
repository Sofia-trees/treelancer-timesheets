"""Freelancer-facing timesheet endpoints. A freelancer only ever sees/edits
their own timesheets and assignments."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import current_user
from app.db import get_db
from app.models import Assignment, Timesheet, User
from app.schemas import (
    AssignmentOut,
    EntriesSave,
    SubmitRequest,
    TimesheetCreate,
    TimesheetDetail,
    TimesheetSummary,
)
from app.services import exporter, timesheet_service as svc

router = APIRouter(tags=["timesheets"])


def _own_timesheet(db: Session, ts_id: uuid.UUID, user: User) -> Timesheet:
    ts = svc._load(db, ts_id)
    if ts.freelancer_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your timesheet")
    return ts


@router.get("/assignments/mine", response_model=list[AssignmentOut])
def my_assignments(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(Assignment)
        .where(Assignment.freelancer_id == user.id, Assignment.is_active.is_(True))
        .options(selectinload(Assignment.client))
    ).all()


@router.get("/timesheets", response_model=list[TimesheetSummary])
def my_timesheets(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(Timesheet)
        .where(Timesheet.freelancer_id == user.id)
        .order_by(Timesheet.billing_period.desc())
    ).all()


@router.post("/timesheets", response_model=TimesheetDetail)
def create_timesheet(body: TimesheetCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    assignment = db.scalar(
        select(Assignment)
        .where(Assignment.id == body.assignment_id)
        .options(selectinload(Assignment.client), selectinload(Assignment.freelancer), selectinload(Assignment.line_manager))
    )
    if assignment is None or assignment.freelancer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found")
    return svc.get_or_create(db, assignment, body.month, body.year)


@router.get("/timesheets/{ts_id}", response_model=TimesheetDetail)
def get_timesheet(ts_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _own_timesheet(db, ts_id, user)


@router.put("/timesheets/{ts_id}/entries", response_model=TimesheetDetail)
def save_entries(ts_id: uuid.UUID, body: EntriesSave, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return svc.save_entries(db, _own_timesheet(db, ts_id, user), body.entries)


@router.post("/timesheets/{ts_id}/submit", response_model=TimesheetDetail)
def submit_timesheet(ts_id: uuid.UUID, body: SubmitRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return svc.submit(db, _own_timesheet(db, ts_id, user), user, body.signature_name, body.confirm)


@router.get("/timesheets/{ts_id}/pdf")
def download_pdf(ts_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ts = _own_timesheet(db, ts_id, user)
    pdf = exporter.timesheet_pdf(ts)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{exporter.pdf_filename(ts)}"'},
    )
