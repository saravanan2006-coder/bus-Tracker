"""Push notification delivery via Firebase Cloud Messaging (HTTP v1).

The worker never talks to FCM directly; it depends on the PushSender
protocol so tests can record sends without network access. In dev/demo the
NoopPushSender is used (credentials are not configured) so the alert flow
still runs end to end and is observable through logs and the `triggered`
flag.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class PushError(Exception):
    """Raised when push delivery cannot be configured."""


class PushSender(Protocol):
    async def send(
        self, *, token: str, title: str, body: str, data: dict[str, str]
    ) -> bool: ...


class NoopPushSender:
    """Dev fallback: records the intended send, never contacts FCM."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send(
        self, *, token: str, title: str, body: str, data: dict[str, str]
    ) -> bool:
        self.sent.append({"token": token, "title": title, "body": body, "data": data})
        logger.info("push (noop) -> %s: %s", token, title)
        return True


class FcmPushSender:
    """Real FCM HTTP v1 sender backed by the firebase-admin SDK."""

    def __init__(self, credentials_file: str) -> None:
        try:
            from firebase_admin import credentials, initialize_app, messaging
        except ImportError as exc:  # pragma: no cover - dependency missing
            raise PushError(
                "firebase-admin is not installed; add it to requirements.txt"
            ) from exc
        cred = credentials.Certificate(credentials_file)
        self._messaging = messaging
        self._app = initialize_app(cred)

    async def send(
        self, *, token: str, title: str, body: str, data: dict[str, str]
    ) -> bool:
        message = self._messaging.Message(
            token=token,
            notification=self._messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in data.items()},
        )
        try:
            response = await asyncio.to_thread(self._messaging.send, message)
            return bool(response)
        except Exception as exc:  # noqa: BLE001 - deliver best effort, never crash the worker
            logger.warning("FCM send failed: %s", exc)
            return False


def build_sender() -> PushSender:
    """Choose the sender based on configuration (real FCM when configured)."""
    from app.config import settings

    if settings.fcm_enabled and settings.fcm_credentials_file:
        try:
            return FcmPushSender(settings.fcm_credentials_file)
        except PushError as exc:
            logger.warning("FCM disabled: %s", exc)
    return NoopPushSender()
