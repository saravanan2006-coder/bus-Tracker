"""Driver authentication endpoints (OTP + JWT)."""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.errors import OtpVerificationFailed, RateLimitedError
from app.config import settings
from app.core.rate_limit import RateLimiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.deps import CurrentDriver, DbSession, Store
from app.models import Driver
from app.schemas import (
    OtpRequest,
    OtpVerifyRequest,
    RefreshRequest,
    TokenResponse,
)
from app.services.otp_service import OtpService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/driver/otp", summary="Request a login OTP for a driver phone")
async def request_otp(
    request: Request, body: OtpRequest, db: DbSession, store: Store
) -> dict:
    # Per-IP limit stops phone-number spraying from a single client.
    ip = request.client.host if request.client else "unknown"
    ip_limiter = RateLimiter(
        store, limit=20, window_seconds=settings.otp_rate_limit_window_seconds
    )
    if not await ip_limiter.allow(f"otp-ip:{ip}"):
        raise RateLimitedError("Too many OTP requests from this device. Try again later.")

    service = OtpService(store)
    await service.request_code(db, body.phone)
    return {"ok": True, "data": {"sent": True, "phone": body.phone}}


@router.post("/driver/verify", response_model=TokenResponse)
async def verify_otp(body: OtpVerifyRequest, db: DbSession, store: Store) -> TokenResponse:
    # Per-phone limit slows OTP brute-force; the per-record attempt cap is the
    # second layer inside OtpService.verify_code.
    verify_limiter = RateLimiter(store, limit=10, window_seconds=300)
    if not await verify_limiter.allow(f"otp-verify:{body.phone}"):
        raise RateLimitedError("Too many verification attempts. Try again later.")

    service = OtpService(store)
    try:
        driver = await service.verify_code(db, body.phone, body.otp)
    except OtpVerificationFailed:
        raise
    return TokenResponse(
        access_token=create_access_token(driver.id),
        refresh_token=create_refresh_token(driver.id),
        driver_id=driver.id,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(
    body: RefreshRequest, db: DbSession, store: Store
) -> TokenResponse:
    try:
        driver_id = decode_token(body.refresh_token, "refresh")
    except ValueError as exc:
        raise OtpVerificationFailed(str(exc)) from exc
    driver = await db.get(Driver, driver_id)
    if driver is None:
        raise OtpVerificationFailed("Driver not found")
    return TokenResponse(
        access_token=create_access_token(driver.id),
        refresh_token=create_refresh_token(driver.id),
        driver_id=driver.id,
    )


@router.get("/me", summary="Current driver profile")
async def me(driver: CurrentDriver) -> dict:
    return {
        "ok": True,
        "data": {
            "id": driver.id,
            "phone": driver.phone,
            "name": driver.name,
            "language": driver.language,
        },
    }
