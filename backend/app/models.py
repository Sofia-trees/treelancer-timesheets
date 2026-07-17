"""Trees Engineering — Treelancer Timesheets: database schema (SQLAlchemy 2.0).

Design goals
------------
1. Two-step approval: freelancer submits -> client Line Manager approves/rejects
   -> Trees admin gives final sign-off. Every transition is written to
   ``approval_events`` for a full audit trail.
2. Magic-link auth (no passwords): a short-lived, single-use token is emailed;
   ``magic_link_tokens`` stores only a hash of it.
3. Assignment-driven pre-fill: a freelancer's ``Assignment`` carries client,
   position, PO code and line manager, so the monthly timesheet header is never
   retyped.
4. Invoice-automation compatibility: the ``Timesheet`` snapshot columns mirror
   ``CanonicalTimesheetLine`` in the trees-invoice engine
   (client_project / resource_name / position / billing_period /
   standard_hours / overtime_hours / po_code / overtime_multiplier), so a future
   direct DB/API feed needs no field remapping — the PDF path works today.

All money-free; hours only. Postgres dialect (NUMERIC, uuid, timestamptz).
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _enum(enum_cls: type[enum.Enum], name: str) -> SAEnum:
    """Persist the enum's *value* (e.g. 'line_manager'), not its member name.
    This keeps stored data aligned with the CHECK constraints and the Postgres
    CREATE TYPE definitions (both of which use the lowercase values)."""
    return SAEnum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


# Generic Uuid: native UUID on Postgres (prod), CHAR(32) on SQLite (local dev/
# verification) — one model definition runs on both.
def _uuid_col() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class UserRole(str, enum.Enum):
    FREELANCER = "freelancer"      # a Treelancer
    LINE_MANAGER = "line_manager"  # client-company approver (first step)
    ADMIN = "admin"                # Trees Engineering finance/ops (final step)


class TimesheetStatus(str, enum.Enum):
    DRAFT = "draft"                          # editable by freelancer
    SUBMITTED = "submitted"                  # locked, awaiting line-manager review
    MANAGER_APPROVED = "manager_approved"    # awaiting Trees admin final sign-off
    APPROVED = "approved"                    # admin-approved, final; feeds invoicing
    REJECTED = "rejected"                    # bounced back with a reason; freelancer can revise


class ApprovalAction(str, enum.Enum):
    SUBMITTED = "submitted"
    MANAGER_APPROVED = "manager_approved"
    MANAGER_REJECTED = "manager_rejected"
    ADMIN_APPROVED = "admin_approved"
    ADMIN_REJECTED = "admin_rejected"
    REOPENED = "reopened"        # a rejected sheet reverted to draft for revision


# OFF is the only leave/day-off code in the current Excel template
# ("Leave/Day Off Codes: OFF"). Modelled as an enum so more codes (AL, MC, PH…)
# can be added later without a schema change to the daily rows.
class DayOffCode(str, enum.Enum):
    OFF = "OFF"


# --------------------------------------------------------------------------- #
# Identity & org
# --------------------------------------------------------------------------- #
class Client(Base):
    """A client company a Treelancer is placed at (NOV Malaysia, SBM Offshore…).

    ``name`` is the canonical billing name and MUST match the client name used
    in the trees-invoice config workbook, because the invoice parser matches a
    timesheet's CLIENT Name against the selected client_project.
    """

    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = _uuid_col()
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    assignments: Mapped[list["Assignment"]] = relationship(back_populates="client")


class User(Base):
    """Everyone who logs in: freelancers, client line managers, Trees admins.

    Magic-link auth only — no password column. Role-specific fields:
      * line managers carry a ``designation`` and a ``client_id`` (they only
        see their own client's timesheets);
      * freelancers keep identity here, but their client/position/PO come from
        the active ``Assignment``, not this row.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_col()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[UserRole] = mapped_column(_enum(UserRole, "user_role"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Line-manager-only attributes (NULL for freelancers/admins).
    designation: Mapped[str | None] = mapped_column(String(200))
    client_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("clients.id"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    client: Mapped["Client | None"] = relationship()
    assignments: Mapped[list["Assignment"]] = relationship(
        back_populates="freelancer",
        foreign_keys="Assignment.freelancer_id",
    )

    __table_args__ = (
        # A line manager must be scoped to a client; a freelancer/admin must not.
        CheckConstraint(
            "(role = 'line_manager') = (client_id IS NOT NULL)",
            name="ck_line_manager_has_client",
        ),
    )


class MagicLinkToken(Base):
    """Single-use, short-lived login token. Only the SHA-256 hash is stored, so
    a DB leak can't be replayed. ``consumed_at`` enforces one-time use."""

    __tablename__ = "magic_link_tokens"

    id: Mapped[uuid.UUID] = _uuid_col()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship()


# --------------------------------------------------------------------------- #
# Assignments (admin-managed; pre-fills the timesheet header)
# --------------------------------------------------------------------------- #
class Assignment(Base):
    """A freelancer's placement: which client, what position, PO code, and who
    the client-side line manager is. This is the single source of the timesheet
    header pre-fill. ``end_date`` NULL means open-ended/current."""

    __tablename__ = "assignments"

    id: Mapped[uuid.UUID] = _uuid_col()
    freelancer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), nullable=False)
    line_manager_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    position: Mapped[str] = mapped_column(String(200), nullable=False)
    # "Put NA if unknown" in the template; NULL here renders as NA on the PDF.
    po_code: Mapped[str | None] = mapped_column(String(100))
    # Snapshot of the manager's name/designation for the PDF, in case the LM
    # user record changes or is absent at generation time.
    line_manager_name: Mapped[str | None] = mapped_column(String(200))
    line_manager_designation: Mapped[str | None] = mapped_column(String(200))
    # Optional default that pre-fills each day's Work Location (e.g. "KL").
    default_work_location: Mapped[str | None] = mapped_column(String(200))

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    freelancer: Mapped["User"] = relationship(
        back_populates="assignments", foreign_keys=[freelancer_id]
    )
    line_manager: Mapped["User | None"] = relationship(foreign_keys=[line_manager_id])
    client: Mapped["Client"] = relationship(back_populates="assignments")
    timesheets: Mapped[list["Timesheet"]] = relationship(back_populates="assignment")


# --------------------------------------------------------------------------- #
# Timesheets
# --------------------------------------------------------------------------- #
class Timesheet(Base):
    """One monthly timesheet for one assignment.

    Header fields are SNAPSHOTTED onto the row at submit time (not just joined
    through the assignment) so an approved/exported sheet is immutable and stays
    faithful to what the freelancer signed, even if the assignment later
    changes. The snapshot column names deliberately mirror
    ``CanonicalTimesheetLine`` for a zero-remap invoice feed.
    """

    __tablename__ = "timesheets"

    id: Mapped[uuid.UUID] = _uuid_col()
    assignment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assignments.id"), nullable=False)
    freelancer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    # Billing period normalized to the 1st of the month (matches the parser).
    billing_period: Mapped[date] = mapped_column(Date, nullable=False)

    status: Mapped[TimesheetStatus] = mapped_column(
        _enum(TimesheetStatus, "timesheet_status"),
        default=TimesheetStatus.DRAFT,
        nullable=False,
    )

    # --- Canonical header snapshot (mirrors CanonicalTimesheetLine) ---------- #
    client_project: Mapped[str] = mapped_column(String(200), nullable=False)   # CLIENT Name
    resource_name: Mapped[str] = mapped_column(String(200), nullable=False)    # Treelancer Name
    position: Mapped[str] = mapped_column(String(200), nullable=False)
    po_code: Mapped[str | None] = mapped_column(String(100))                   # None -> "NA"
    line_manager_name: Mapped[str | None] = mapped_column(String(200))
    line_manager_designation: Mapped[str | None] = mapped_column(String(200))

    # --- Cached totals (recomputed on every entry change) -------------------- #
    total_standard_hours: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), default=Decimal("0"), nullable=False
    )
    total_overtime_hours: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), default=Decimal("0"), nullable=False
    )
    # Not decided at timesheet time; carried for the invoice engine's benefit.
    overtime_multiplier: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=Decimal("1.5"))

    # --- Submission / signature --------------------------------------------- #
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # E-signature = typed name + confirmation checkbox + timestamp (not drawn).
    signature_name: Mapped[str | None] = mapped_column(String(200))
    signature_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    date_signed: Mapped[date | None] = mapped_column(Date)

    # --- Approval outcome (denormalized for fast filtering) ----------------- #
    manager_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manager_action_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    admin_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    admin_action_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    assignment: Mapped["Assignment"] = relationship(back_populates="timesheets")
    entries: Mapped[list["TimesheetEntry"]] = relationship(
        back_populates="timesheet",
        cascade="all, delete-orphan",
        order_by="TimesheetEntry.day",
    )
    approval_events: Mapped[list["ApprovalEvent"]] = relationship(
        back_populates="timesheet",
        cascade="all, delete-orphan",
        order_by="ApprovalEvent.created_at",
    )

    __table_args__ = (
        # One timesheet per assignment per month.
        UniqueConstraint("assignment_id", "billing_period", name="uq_timesheet_period"),
    )


class TimesheetEntry(Base):
    """A single day (1..31) within a timesheet. A day is either worked (hours +
    location + remarks) or marked OFF via ``day_off_code``. Days with no hours
    and no OFF code are simply empty (as in the Excel blank rows)."""

    __tablename__ = "timesheet_entries"

    id: Mapped[uuid.UUID] = _uuid_col()
    timesheet_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("timesheets.id", ondelete="CASCADE"), nullable=False
    )
    day: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..31, must be valid for the month

    standard_hours: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=Decimal("0"), nullable=False)
    overtime_hours: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=Decimal("0"), nullable=False)
    work_location: Mapped[str | None] = mapped_column(String(200))
    remarks: Mapped[str | None] = mapped_column(Text)
    day_off_code: Mapped[DayOffCode | None] = mapped_column(_enum(DayOffCode, "day_off_code"))

    timesheet: Mapped["Timesheet"] = relationship(back_populates="entries")

    @property
    def is_off(self) -> bool:
        return self.day_off_code is not None

    __table_args__ = (
        UniqueConstraint("timesheet_id", "day", name="uq_entry_day"),
        CheckConstraint("day BETWEEN 1 AND 31", name="ck_entry_day_range"),
        CheckConstraint("standard_hours >= 0 AND overtime_hours >= 0", name="ck_entry_hours_nonneg"),
        # An OFF day carries no worked hours.
        CheckConstraint(
            "day_off_code IS NULL OR (standard_hours = 0 AND overtime_hours = 0)",
            name="ck_off_has_no_hours",
        ),
    )


class ApprovalEvent(Base):
    """Immutable audit log of every status transition (the two-step chain).
    Never updated — one row per action, newest last."""

    __tablename__ = "approval_events"

    id: Mapped[uuid.UUID] = _uuid_col()
    timesheet_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("timesheets.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[ApprovalAction] = mapped_column(
        _enum(ApprovalAction, "approval_action"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text)  # required for the *_rejected actions
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    timesheet: Mapped["Timesheet"] = relationship(back_populates="approval_events")
    actor: Mapped["User"] = relationship()
