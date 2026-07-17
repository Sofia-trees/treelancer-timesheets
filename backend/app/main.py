"""Trees Engineering — Treelancer Timesheets API.

In production this single service also serves the built React app (see the
SPA catch-all at the bottom), so one Render deploy gives one shareable URL —
no separate frontend host or CORS to configure.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import init_db
from app.routers import admin, assignments, auth, manager, timesheets

settings = get_settings()

app = FastAPI(title="Treelancer Timesheets API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    if settings.seed_on_startup:
        from app.seed import run as seed_run  # local import: only needed for demo deploys
        seed_run()


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


# All API routes live under /api so the SPA catch-all below can safely own
# everything else (matches the frontend's default VITE_API_BASE of "/api").
app.include_router(auth.router, prefix="/api")
app.include_router(timesheets.router, prefix="/api")
app.include_router(manager.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(assignments.router, prefix="/api")


# ---- Serve the built frontend (frontend/dist), if present ----------------- #
_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

if _FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        # Registered last, so it only catches requests that didn't match an
        # /api/* route above. Any unknown path falls back to index.html so
        # React Router can render the right client-side page.
        candidate = _FRONTEND_DIST / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_DIST / "index.html")
