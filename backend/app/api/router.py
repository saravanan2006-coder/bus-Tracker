"""Aggregate all API routers."""
from fastapi import APIRouter

from app.api import admin, auth, driver, public, trips, ws

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(driver.router)
api_router.include_router(trips.router)
api_router.include_router(public.router)
api_router.include_router(ws.router)
api_router.include_router(admin.router)
