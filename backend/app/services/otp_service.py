"""OTP lifecycle: rate limiting, generation, persistence and verification."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.rate_limit import RateLimiter
from app.core.security import generate_otp, hash_otp
from app.core.redis_client import KeyValueStore
from app.models import Driver, OtpCode
from app.utils.time import ensure_utc, utc_now


def _now() -> datetime:
    return datetime.now(timezone.utc)


class OtpService:
    def __init__(self, store: KeyValueStore) -> None:
        self._rate_limiter = RateLimiter(
            store,
            limit=settings.otp_rate_limit_max,
            window_seconds=settings.otp_rate_limit_window_seconds,
        )

    async def request_code(self, db: AsyncSession, phone: str) -> None:
        """Generate and dispatch an OTP. Raising on rate-limit violations."""
        allowed = await self._rate_limiter.allow(f"otp:{phone}")
        if not allowed:
            from app.api.errors import RateLimitedError

            raise RateLimitedError("Too many OTP requests. Try again later.")

        code = generate_otp()
        record = OtpCode(
            phone=phone,
            code_hash=hash_otp(code),
            purpose="driver_login",
            expires_at=utc_now() + timedelta(seconds=settings.otp_ttl_seconds),
        )
        db.add(record)
        await db.commit()

        # Upsert a provisional driver record so sign-in and sign-up share a flow.
        existing = await db.scalar(select(Driver).where(Driver.phone == phone))
        if existing is None:
            db.add(Driver(phone=phone))
            await db.commit()

        await self._send(phone, code)

    async def verify_code(self, db: AsyncSession, phone: str, code: str) -> Driver:
        """Verify a code; raise OtpVerificationFailed on any failure."""
        records = (
            await db.execute(
                select(OtpCode)
                .where(OtpCode.phone == phone, OtpCode.consumed.is_(False))
                .order_by(OtpCode.created_at.desc())
            )
        ).scalars().all()

        for record in records:
            if ensure_utc(record.expires_at) < _now():
                continue
            if record.attempts >= settings.otp_max_attempts:
                continue
            record.attempts += 1
            if record.code_hash == hash_otp(code):
                record.consumed = True
                record.attempts = 0
                driver = await db.scalar(select(Driver).where(Driver.phone == phone))
                await db.execute(
                    update(OtpCode)
                    .where(OtpCode.id != record.id, OtpCode.phone == phone)
                    .values(consumed=True)
                )
                await db.commit()
                if driver is None:
                    from app.api.errors import OtpVerificationFailed

                    raise OtpVerificationFailed("Driver record missing")
                return driver
            await db.commit()
            break

        from app.api.errors import OtpVerificationFailed

        raise OtpVerificationFailed("Invalid or expired OTP")

    async def _send(self, phone: str, code: str) -> None:
        provider = settings.sms_provider
        if provider == "console":
            print(f"[OTP:{phone}] {code}", flush=True)
        elif provider == "msg91":
            await self._send_msg91(phone, code)
        elif provider == "twilio":
            await self._send_twilio(phone, code)

    async def _send_msg91(self, phone: str, code: str) -> None:
        import httpx

        payload = {
            "authkey": settings.sms_api_key,
            "template_id": "",
            "mobile": phone.removeprefix("+91"),
            "sender": settings.sms_sender_id,
            "message": f"Your BusTracker OTP is {code}. Valid for 5 minutes.",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://control.msg91.com/api/v5/flow/", json=payload
            )
            resp.raise_for_status()

    async def _send_twilio(self, phone: str, code: str) -> None:
        # Requires TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN. Kept minimal: use
        # the API key via Basic auth with the Verify/Message endpoints.
        raise NotImplementedError(
            "Twilio transport not configured. Set SMS_PROVIDER=msg91 or console."
        )
