"""FastAPI application entrypoint."""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.errors import ApiError, as_http_exception
from app.api.router import api_router
from app.config import settings
from app.database import init_db

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("Database initialised")
    demo_task: asyncio.Task | None = None
    if os.environ.get("RUN_DEMO_BUS") == "1":
        from scripts.run_demo_bus import run_demo_loop

        demo_task = asyncio.create_task(run_demo_loop())
        logger.info("Demo bus simulator started")
    alert_task: asyncio.Task | None = None
    if os.environ.get("ALERT_WORKER") == "1":
        from app.services.alert_worker import run_alert_worker

        alert_task = asyncio.create_task(run_alert_worker())
        logger.info("Alert worker started")
    yield
    if demo_task is not None:
        demo_task.cancel()
        logger.info("Demo bus simulator stopped")
    if alert_task is not None:
        alert_task.cancel()
        logger.info("Alert worker stopped")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Village-to-village live bus tracking for Tamil Nadu. "
        "Drivers share GPS from their phones; the public tracks without an account."
    ),
    lifespan=lifespan,
    openapi_url=f"{settings.api_prefix}/openapi.json",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"ok": False, "error": exc.code, "detail": exc.message},
    )


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"ok": True, "service": settings.app_name}


app.include_router(api_router, prefix=settings.api_prefix)
