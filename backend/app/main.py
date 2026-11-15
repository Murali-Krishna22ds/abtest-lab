"""FastAPI application entry point."""
from __future__ import annotations

import logging
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import settings
from .errors import AppError
from .routers import analyze, data, power, studies, tests

log = logging.getLogger("ablab")

@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.warmup_pymc:  # compile the PyMC model in the background so the first user request is fast
        from .stats import bayes

        threading.Thread(target=bayes.warmup, daemon=True).start()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Experimentation Lab API",
    version=__version__,
    description="Power analysis, classical and sequential tests, Bayesian A/B analysis and observational causal methods.",
)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def timing(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time-Ms"] = f"{(time.perf_counter() - start) * 1000:.1f}"
    return response


@app.exception_handler(AppError)
async def app_error(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(ValueError)
async def value_error(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unexpected(_: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Unexpected server error. The analysis could not be completed."})


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "version": __version__}


for r in (data.router, power.router, tests.router, studies.router, analyze.router):
    app.include_router(r)


_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.exists():  # single-container deployment: serve the built React app
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        target = (_DIST / path).resolve()
        if path and target.is_file() and _DIST in target.parents:
            return FileResponse(target)
        return FileResponse(_DIST / "index.html")
