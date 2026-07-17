"""Seed demo data for local dev: clients, one admin, one line manager, two
freelancers, and active assignments. Idempotent-ish (skips if users exist).

Run:  python -m app.seed
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.models import Assignment, Client, User, UserRole

DEMO = {
    "admin": ("finance@trees-engineering.com", "Trees Finance Ops"),
    "manager": ("wm.tan@novmalaysia.com", "Ir. Tan Wei Ming", "Engineering Manager"),
    "freelancers": [
        ("shahmin@example.com", "Muhammad Shahmin Bin Ahmad Fadzil",
         "Senior Mechanical Package Engineer (Rotating)", "P-ADMIN -2105 Rev0", "Remote/Kuala Lumpur"),
        ("khairul@example.com", "Khairul Azli", "Senior E&I Engineer", "1000784", "KL"),
    ],
}


def run() -> None:
    init_db()
    db = SessionLocal()
    try:
        if db.scalar(select(User).limit(1)) is not None:
            print("Data already present — skipping seed.")
            return

        client = Client(name="NOV Malaysia")
        db.add(client)
        db.flush()

        admin = User(email=DEMO["admin"][0], full_name=DEMO["admin"][1], role=UserRole.ADMIN)
        m_email, m_name, m_desig = DEMO["manager"]
        manager = User(
            email=m_email, full_name=m_name, role=UserRole.LINE_MANAGER,
            designation=m_desig, client_id=client.id,
        )
        db.add_all([admin, manager])
        db.flush()

        for email, name, position, po, loc in DEMO["freelancers"]:
            f = User(email=email, full_name=name, role=UserRole.FREELANCER)
            db.add(f)
            db.flush()
            db.add(Assignment(
                freelancer_id=f.id, client_id=client.id, line_manager_id=manager.id,
                position=position, po_code=po,
                line_manager_name=manager.full_name, line_manager_designation=manager.designation,
                default_work_location=loc, start_date=date(2024, 1, 1),
            ))
        db.commit()
        print("Seeded: 1 client, 1 admin, 1 line manager, 2 freelancers with assignments.")
        print("Login emails:")
        print("  admin    :", DEMO["admin"][0])
        print("  manager  :", m_email)
        for email, name, *_ in DEMO["freelancers"]:
            print(f"  freelancer: {email}  ({name})")
    finally:
        db.close()


if __name__ == "__main__":
    run()
