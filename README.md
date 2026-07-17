# Trees Engineering — Treelancer Timesheets

Web app for Treelancers to fill and submit monthly timesheets online, replacing
the manual Excel template. Feeds the existing invoice-automation system via a
**parser-ingestible PDF** today, and a shared canonical data model for a future
direct DB/API feed.

## Status

**Full app built and verified.** FastAPI + Postgres/SQLite backend and a React
(Vite) SPA covering the freelancer portal, line-manager approvals, the Trees
admin panel, and assignment management — plus the text-layer PDF generator the
existing `trees-invoice` `TreelancerParser` reads unchanged.

Decisions implemented: two-step approval (client line manager → Trees admin),
magic-link auth (passwordless), React SPA + FastAPI/Postgres (Render + Vercel).

Verified: `scripts/verify_parser.py` (PDF↔parser), `scripts/smoke_test.py`
(21/21 backend lifecycle checks), and a full browser pass of all three role
portals.

## Layout

```
backend/app/models.py            SQLAlchemy 2.0 schema (Postgres/SQLite)
backend/app/schema.sql           Generated DDL (runnable, incl. CREATE TYPE)
backend/app/config.py, db.py     Settings + engine/session
backend/app/auth.py              Magic-link issue/verify + JWT + role guards
backend/app/schemas.py           Pydantic DTOs
backend/app/services/            timesheet lifecycle + PDF/ZIP exporter
backend/app/routers/             auth, timesheets, manager, admin, assignments
backend/app/pdf/timesheet_pdf.py PDF generator (reportlab, text-layer)
backend/app/seed.py              Demo data (1 client, admin, manager, 2 freelancers)
frontend/                        React SPA (Vite): login, dashboard, editor,
                                 manager queue, admin panel, assignment mgmt
scripts/verify_parser.py         Generate a PDF and parse it with the REAL parser
scripts/smoke_test.py            End-to-end backend lifecycle test
```

## Run locally

```
# Backend (SQLite, no external services)
cd backend
python -m pip install -r requirements.txt
python -m app.seed                       # demo data
python -m uvicorn app.main:app --port 8077

# Frontend (proxies /api -> :8077)
cd frontend
npm install
npm run dev                              # http://localhost:5173
```

Sign in with any seeded email (e.g. `shahmin@example.com` freelancer,
`wm.tan@novmalaysia.com` manager, `finance@trees-engineering.com` admin). In dev
(`TT_EXPOSE_MAGIC_LINK=true`) the sign-in link is returned in the UI instead of
emailed. For prod, set `DATABASE_URL` (Postgres), `TT_JWT_SECRET`,
`TT_EXPOSE_MAGIC_LINK=false`, and wire a transactional email sender in
`routers/auth.py`.

## Verify the PDF ↔ parser contract

```
python scripts/verify_parser.py
```

Generates a stress-case timesheet (long name, long position, text PO code, 31
rows, OFF days, fractional OT), parses it with the unmodified
`treesinvoice.parsers.treelancer.TreelancerParser`, and asserts every canonical
field round-trips with `extraction_method=text_layer` and
`needs_manual_review=False`.

## The geometry contract (read before touching the generator)

The parser has **no form fields** — it re-derives every value from where words
land, bucketing each word by its bounding-box **centre**. So the generator must
place tokens in exact coordinate bands (PyMuPDF top-left points; reportlab's
bottom-up origin is converted once via `_y`). Break these and the parser
silently misreads or flags manual review:

| Field group | Band (x, top-down pts) |
|---|---|
| Header value-1 (Name / Position / Month) | `cx ∈ [95, 205)` |
| Header value-2 (Client / PO Code / Year) | `cx ∈ [320, 460)` |
| Table: date / std / ot / location / remarks | `[0,108) [108,207) [207,317) [317,423) [423,800)` |

Rules baked into `timesheet_pdf.py`:
- The **day number is the only pure-digit token with `cx < 108`** — it anchors
  each row. Never let another bare integer land in the date column (dates in the
  footer are formatted `DD/MM/YYYY` on purpose so `.isdigit()` is false).
- Long values **wrap within their column width** so no word drifts into the next
  field's band.
- Labels render the exact tokens the parser searches for: `Treelancer Name`,
  `CLIENT Name`, `POSITION`, `PO CODE`, `MONTH`, `YEAR`, `DATES`, `Total`.
- Footer `Total` std/ot must equal the summed rows (parser tolerance 0.1).
- Single page, text layer (reportlab native).

## Invoice-automation compatibility

`Timesheet` snapshot columns mirror the invoice engine's `CanonicalTimesheetLine`
(`client_project`, `resource_name`, `position`, `billing_period`,
`standard_hours`, `overtime_hours`, `po_code`, `overtime_multiplier`) so a future
direct feed needs no field remapping. `clients.name` MUST match the client name
in the trees-invoice config workbook (the parser matches on it).
```
