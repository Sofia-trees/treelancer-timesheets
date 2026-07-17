"""Pydantic request/response models (API DTOs), separate from ORM models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import TimesheetStatus, UserRole


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- auth ------------------------------------------------------------------ #
class LinkRequest(BaseModel):
    email: EmailStr


class LinkResponse(BaseModel):
    detail: str
    # dev-only convenience: the magic link, when TT_EXPOSE_MAGIC_LINK is on.
    magic_link: str | None = None


class VerifyRequest(BaseModel):
    token: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    designation: str | None = None
    client_id: uuid.UUID | None = None


# ---- clients / assignments ------------------------------------------------- #
class ClientOut(ORMModel):
    id: uuid.UUID
    name: str
    is_active: bool


class ClientCreate(BaseModel):
    name: str


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    role: UserRole
    designation: str | None = None       # line managers
    client_id: uuid.UUID | None = None   # line managers: which client they approve for


class AssignmentOut(ORMModel):
    id: uuid.UUID
    freelancer_id: uuid.UUID
    client_id: uuid.UUID
    line_manager_id: uuid.UUID | None
    position: str
    po_code: str | None
    line_manager_name: str | None
    line_manager_designation: str | None
    default_work_location: str | None
    start_date: date
    end_date: date | None
    is_active: bool


class AssignmentCreate(BaseModel):
    freelancer_id: uuid.UUID
    client_id: uuid.UUID
    line_manager_id: uuid.UUID | None = None
    position: str
    po_code: str | None = None
    line_manager_name: str | None = None
    line_manager_designation: str | None = None
    default_work_location: str | None = None
    start_date: date
    end_date: date | None = None


class AssignmentFillIn(BaseModel):
    """One-screen assignment creation: every party is typed in free-text and
    resolved to an existing record (matched by email/name) or created on the
    fly. No pre-populated 'choose from a list' — companies and people aren't
    known in advance."""

    freelancer_name: str
    freelancer_email: EmailStr

    client_name: str

    line_manager_name: str | None = None
    line_manager_email: EmailStr | None = None
    line_manager_designation: str | None = None

    position: str
    po_code: str | None = None
    default_work_location: str | None = None
    start_date: date
    end_date: date | None = None


class AssignmentUpdate(BaseModel):
    line_manager_id: uuid.UUID | None = None
    position: str | None = None
    po_code: str | None = None
    line_manager_name: str | None = None
    line_manager_designation: str | None = None
    default_work_location: str | None = None
    end_date: date | None = None
    is_active: bool | None = None


# ---- timesheets ------------------------------------------------------------ #
class EntryIn(BaseModel):
    day: int = Field(ge=1, le=31)
    standard_hours: Decimal = Decimal("0")
    overtime_hours: Decimal = Decimal("0")
    work_location: str | None = None
    remarks: str | None = None
    is_off: bool = False


class EntryOut(ORMModel):
    day: int
    standard_hours: Decimal
    overtime_hours: Decimal
    work_location: str | None
    remarks: str | None
    is_off: bool = False


class TimesheetCreate(BaseModel):
    assignment_id: uuid.UUID
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2020, le=2100)


class EntriesSave(BaseModel):
    entries: list[EntryIn]


class SubmitRequest(BaseModel):
    signature_name: str
    confirm: bool


class RejectRequest(BaseModel):
    reason: str = Field(min_length=1)


class ApprovalEventOut(ORMModel):
    action: str
    reason: str | None
    created_at: datetime


class TimesheetSummary(ORMModel):
    id: uuid.UUID
    billing_period: date
    status: TimesheetStatus
    client_project: str
    resource_name: str
    position: str
    po_code: str | None
    total_standard_hours: Decimal
    total_overtime_hours: Decimal
    submitted_at: datetime | None
    rejection_reason: str | None


class TimesheetDetail(TimesheetSummary):
    assignment_id: uuid.UUID
    line_manager_name: str | None
    line_manager_designation: str | None
    signature_name: str | None
    date_signed: date | None
    entries: list[EntryOut]
    approval_events: list[ApprovalEventOut]
