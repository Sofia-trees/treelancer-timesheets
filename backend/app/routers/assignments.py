"""Admin-only management of clients, users, and assignments. Assignments are
what pre-fill a freelancer's monthly timesheet header."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth import require_role
from app.db import get_db
from app.models import Assignment, Client, User, UserRole
from app.schemas import (
    AssignmentCreate,
    AssignmentFillIn,
    AssignmentOut,
    AssignmentUpdate,
    ClientCreate,
    ClientOut,
    UserCreate,
    UserOut,
)

router = APIRouter(prefix="/admin", tags=["assignment-management"])
_guard = require_role(UserRole.ADMIN)


def _find_or_create_client(db: Session, name: str) -> Client:
    name = name.strip()
    client = db.scalar(select(Client).where(Client.name == name))
    if client is not None:
        return client
    client = Client(name=name)
    db.add(client)
    db.flush()
    return client


def _find_or_create_person(
    db: Session,
    email: str,
    full_name: str,
    role: UserRole,
    *,
    designation: str | None = None,
    client_id: uuid.UUID | None = None,
) -> User:
    email = email.strip().lower()
    full_name = full_name.strip()
    user = db.scalar(select(User).where(User.email == email))
    if user is not None:
        if user.role != role:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"{email} is already registered as {user.role.value}, not {role.value}",
            )
        if role == UserRole.LINE_MANAGER and client_id is not None and user.client_id != client_id:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"{email} is already a line manager for a different client",
            )
        user.full_name = full_name
        if designation is not None:
            user.designation = designation
        return user
    user = User(email=email, full_name=full_name, role=role, designation=designation, client_id=client_id)
    db.add(user)
    db.flush()
    return user


# ---- clients --------------------------------------------------------------- #
@router.get("/clients", response_model=list[ClientOut])
def list_clients(_: User = Depends(_guard), db: Session = Depends(get_db)):
    return db.scalars(select(Client).order_by(Client.name)).all()


@router.post("/clients", response_model=ClientOut, status_code=201)
def create_client(body: ClientCreate, _: User = Depends(_guard), db: Session = Depends(get_db)):
    client = Client(name=body.name.strip())
    db.add(client)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A client with that name already exists")
    db.refresh(client)
    return client


# ---- users ----------------------------------------------------------------- #
@router.get("/users", response_model=list[UserOut])
def list_users(role: UserRole | None = None, _: User = Depends(_guard), db: Session = Depends(get_db)):
    stmt = select(User).order_by(User.full_name)
    if role is not None:
        stmt = stmt.where(User.role == role)
    return db.scalars(stmt).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, _: User = Depends(_guard), db: Session = Depends(get_db)):
    if body.role == UserRole.LINE_MANAGER and body.client_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A line manager must be tied to a client")
    if body.role != UserRole.LINE_MANAGER and body.client_id is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Only line managers carry a client")
    user = User(
        email=body.email.strip().lower(),
        full_name=body.full_name.strip(),
        role=body.role,
        designation=body.designation,
        client_id=body.client_id,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with that email already exists")
    db.refresh(user)
    return user


# ---- assignments ----------------------------------------------------------- #
@router.get("/assignments", response_model=list[AssignmentOut])
def list_assignments(
    freelancer_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
    _: User = Depends(_guard),
    db: Session = Depends(get_db),
):
    stmt = select(Assignment).order_by(Assignment.start_date.desc())
    if freelancer_id is not None:
        stmt = stmt.where(Assignment.freelancer_id == freelancer_id)
    if client_id is not None:
        stmt = stmt.where(Assignment.client_id == client_id)
    return db.scalars(stmt).all()


@router.post("/assignments", response_model=AssignmentOut, status_code=201)
def create_assignment(body: AssignmentCreate, _: User = Depends(_guard), db: Session = Depends(get_db)):
    freelancer = db.get(User, body.freelancer_id)
    if freelancer is None or freelancer.role != UserRole.FREELANCER:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "freelancer_id must reference a freelancer")
    if db.get(Client, body.client_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown client")
    if body.line_manager_id is not None:
        lm = db.get(User, body.line_manager_id)
        if lm is None or lm.role != UserRole.LINE_MANAGER:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "line_manager_id must reference a line manager")
    assignment = Assignment(**body.model_dump())
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.post("/assignments/fill", response_model=AssignmentOut, status_code=201)
def fill_assignment(body: AssignmentFillIn, _: User = Depends(_guard), db: Session = Depends(get_db)):
    """Single-screen assignment creation: client, freelancer, and line manager
    are typed in free-text and resolved to an existing record or created on
    the spot — no picking from a pre-populated list of companies/people."""
    try:
        client = _find_or_create_client(db, body.client_name)
        freelancer = _find_or_create_person(db, body.freelancer_email, body.freelancer_name, UserRole.FREELANCER)
        line_manager = None
        if body.line_manager_email:
            line_manager = _find_or_create_person(
                db,
                body.line_manager_email,
                body.line_manager_name or body.line_manager_email,
                UserRole.LINE_MANAGER,
                designation=body.line_manager_designation,
                client_id=client.id,
            )
        assignment = Assignment(
            freelancer_id=freelancer.id,
            client_id=client.id,
            line_manager_id=line_manager.id if line_manager else None,
            position=body.position.strip(),
            po_code=(body.po_code or "").strip() or None,
            line_manager_name=line_manager.full_name if line_manager else body.line_manager_name,
            line_manager_designation=line_manager.designation if line_manager else body.line_manager_designation,
            default_work_location=(body.default_work_location or "").strip() or None,
            start_date=body.start_date,
            end_date=body.end_date,
        )
        db.add(assignment)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Could not create assignment — check for a duplicate")
    db.refresh(assignment)
    return assignment


@router.patch("/assignments/{assignment_id}", response_model=AssignmentOut)
def update_assignment(
    assignment_id: uuid.UUID, body: AssignmentUpdate, _: User = Depends(_guard), db: Session = Depends(get_db)
):
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(assignment, field, value)
    db.commit()
    db.refresh(assignment)
    return assignment
