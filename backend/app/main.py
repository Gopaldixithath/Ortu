from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routers import public_site

app = FastAPI(
    title="ORTU Fitness",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.include_router(public_site.router)

# Directory holding the built React frontend (populated in the Docker image).
STATIC_DIR = Path(os.getenv("ORTU_STATIC_DIR", "/app/static")).resolve()


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "ok"}


if (STATIC_DIR / "index.html").exists():
    _assets = STATIC_DIR / "assets"
    if _assets.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

    def _index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/", include_in_schema=False)
    def serve_index():
        return _index()

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        # Serve a real static file when it exists; otherwise fall back to the
        # SPA entry point so client-side state (e.g. ?payment=success) resolves.
        candidate = (STATIC_DIR / full_path).resolve()
        try:
            candidate.relative_to(STATIC_DIR)
        except ValueError:
            return _index()
        if candidate.is_file():
            return FileResponse(candidate)
        return _index()
