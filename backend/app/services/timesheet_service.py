"""Timesheet lifecycle: create-from-assignment, save entries, submit, and the
two-step approval transitions. All status changes append an ApprovalEvent so the
audit trail is complete."""

from __future__ import annotations

import calendar
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    ApprovalAction,
    ApprovalEvent,
    Assignment,
    DayOffCode,
    Timesheet,
    TimesheetEntry,
    TimesheetStatus,
    User,
)
from app.schemas import EntryIn


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load(db: Session, timesheet_id: uuid.UUID) -> Timesheet:
    ts = db.scalar(
        select(Timesheet)
        .where(Timesheet.id == timesheet_id)
        .options(selectinload(Timesheet.entries), selectinload(Timesheet.approval_events))
    )
    if ts is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Timesheet not found")
    return ts


def get_or_create(db: Session, assignment: Assignment, month: int, year: int) -> Timesheet:
    """Return the existing timesheet for this assignment+month, or create a
    fresh Draft with the header snapshotted from the assignment."""
    period = date(year, month, 1)
    existing = db.scalar(
        select(Timesheet).where(
            Timesheet.assignment_id == assignment.id, Timesheet.billing_period == period
        )
    )
    if existing is not None:
        return _load(db, existing.id)

    ts = Timesheet(
        assignment_id=assignment.id,
        freelancer_id=assignment.freelancer_id,
        billing_period=period,
        status=TimesheetStatus.DRAFT,
        client_project=assignment.client.name,
        resource_name=assignment.freelancer.full_name,
        position=assignment.position,
        po_code=assignment.po_code,
        line_manager_name=assignment.line_manager_name
        or (assignment.line_manager.full_name if assignment.line_manager else None),
        line_manager_designation=assignment.line_manager_designation
        or (assignment.line_manager.designation if assignment.line_manager else None),
    )
    db.add(ts)
    db.commit()
    return _load(db, ts.id)


def save_entries(db: Session, ts: Timesheet, entries: list[EntryIn]) -> Timesheet:
    """Replace the timesheet's daily entries and recompute totals. Only allowed
    while editable (Draft or Rejected)."""
    if ts.status not in (TimesheetStatus.DRAFT, TimesheetStatus.REJECTED):
        raise HTTPException(status.HTTP_409_CONFLICT, "Timesheet is locked and cannot be edited")

    ndays = calendar.monthrange(ts.billing_period.year, ts.billing_period.month)[1]
    ts.entries.clear()
    db.flush()

    std_total = Decimal("0")
    ot_total = Decimal("0")
    for e in entries:
        if e.day > ndays:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Day {e.day} is out of range for this month")
        if e.is_off:
            std, ot, code = Decimal("0"), Decimal("0"), DayOffCode.OFF
        else:
            std, ot, code = e.standard_hours, e.overtime_hours, None
        std_total += std
        ot_total += ot
        ts.entries.append(
            TimesheetEntry(
                day=e.day,
                standard_hours=std,
                overtime_hours=ot,
                work_location=None if e.is_off else e.work_location,
                remarks=e.remarks,
                day_off_code=code,
            )
        )

    ts.total_standard_hours = std_total
    ts.total_overtime_hours = ot_total
    ts.updated_at = _now()
    db.commit()
    return _load(db, ts.id)


def _event(db: Session, ts: Timesheet, actor: User, action: ApprovalAction, reason: str | None = None) -> None:
    db.add(ApprovalEvent(timesheet_id=ts.id, actor_id=actor.id, action=action, reason=reason))


def submit(db: Session, ts: Timesheet, actor: User, signature_name: str, confirm: bool) -> Timesheet:
    if ts.status not in (TimesheetStatus.DRAFT, TimesheetStatus.REJECTED):
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a draft or rejected timesheet can be submitted")
    if not confirm or not signature_name.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Signature name and confirmation are required")
    if not ts.entries:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Fill in at least one day before submitting")

    ts.status = TimesheetStatus.SUBMITTED
    ts.signature_name = signature_name.strip()
    ts.signature_confirmed = True
    ts.date_signed = _now().date()
    ts.submitted_at = _now()
    ts.rejection_reason = None
    _event(db, ts, actor, ApprovalAction.SUBMITTED)
    db.commit()
    return _load(db, ts.id)


def manager_approve(db: Session, ts: Timesheet, actor: User) -> Timesheet:
    if ts.status != TimesheetStatus.SUBMITTED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a submitted timesheet awaits line-manager approval")
    ts.status = TimesheetStatus.MANAGER_APPROVED
    ts.manager_action_at = _now()
    ts.manager_action_by = actor.id
    _event(db, ts, actor, ApprovalAction.MANAGER_APPROVED)
    db.commit()
    return _load(db, ts.id)


def admin_approve(db: Session, ts: Timesheet, actor: User) -> Timesheet:
    if ts.status != TimesheetStatus.MANAGER_APPROVED:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Timesheet must be line-manager approved before final admin sign-off"
        )
    ts.status = TimesheetStatus.APPROVED
    ts.admin_action_at = _now()
    ts.admin_action_by = actor.id
    _event(db, ts, actor, ApprovalAction.ADMIN_APPROVED)
    db.commit()
    return _load(db, ts.id)


def reject(db: Session, ts: Timesheet, actor: User, reason: str, by_manager: bool) -> Timesheet:
    """Bounce a timesheet back to the freelancer with a reason. A manager can
    reject a Submitted sheet; an admin can reject a Submitted or
    Manager-approved sheet."""
    allowed = (
        {TimesheetStatus.SUBMITTED}
        if by_manager
        else {TimesheetStatus.SUBMITTED, TimesheetStatus.MANAGER_APPROVED}
    )
    if ts.status not in allowed:
        raise HTTPException(status.HTTP_409_CONFLICT, "Timesheet is not in a rejectable state")
    ts.status = TimesheetStatus.REJECTED
    ts.rejection_reason = reason
    action = ApprovalAction.MANAGER_REJECTED if by_manager else ApprovalAction.ADMIN_REJECTED
    if by_manager:
        ts.manager_action_at = _now()
        ts.manager_action_by = actor.id
    else:
        ts.admin_action_at = _now()
        ts.admin_action_by = actor.id
    _event(db, ts, actor, action, reason)
    db.commit()
    return _load(db, ts.id)
