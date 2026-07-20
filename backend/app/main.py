"""Trees Engineering — Treelancer Timesheets API.

Self-service, no accounts: this single service exposes one API route that turns
a submitted form into the parser-proof PDF, and also serves the built React app
(frontend/dist). One Render deploy, one shareable URL, no login, no database.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import generate

settings = get_settings()

app = FastAPI(title="Treelancer Timesheets API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


# The only API route. Lives under /api so the SPA catch-all below can own
# everything else (matches the frontend's default VITE_API_BASE of "/api").
app.include_router(generate.router, prefix="/api")


# ---- Serve the built frontend (frontend/dist), if present ----------------- #
_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

if _FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        # Registered last, so it only catches requests that didn't match the
        # /api/* route above. Any unknown path falls back to index.html.
        candidate = _FRONTEND_DIST / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_DIST / "index.html")
