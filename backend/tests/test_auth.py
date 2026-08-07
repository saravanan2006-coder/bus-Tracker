"""Auth flow tests: OTP request/verify, token issuance, refresh."""
from __future__ import annotations

from app.core.security import create_access_token


async def test_otp_request(client, otp_code):
    resp = await client.post("/api/v1/auth/driver/otp", json={"phone": "+919876543210"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


async def test_otp_rate_limited(client, otp_code):
    for _ in range(3):
        resp = await client.post(
            "/api/v1/auth/driver/otp", json={"phone": "+919876543211"}
        )
        assert resp.status_code == 200
    resp = await client.post("/api/v1/auth/driver/otp", json={"phone": "+919876543211"})
    assert resp.status_code == 429


async def test_verify_wrong_otp(client, otp_code):
    await client.post("/api/v1/auth/driver/otp", json={"phone": "+919876543212"})
    resp = await client.post(
        "/api/v1/auth/driver/verify",
        json={"phone": "+919876543212", "otp": "000000"},
    )
    assert resp.status_code == 401


async def test_verify_correct_otp(client, otp_code):
    await client.post("/api/v1/auth/driver/otp", json={"phone": "+919876543213"})
    resp = await client.post(
        "/api/v1/auth/driver/verify",
        json={"phone": "+919876543213", "otp": "123456"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    return body


async def test_me_with_token(client, otp_code):
    tokens = await test_verify_correct_otp(client, otp_code)
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["phone"] == "+919876543213"


async def test_refresh_flow(client, otp_code):
    tokens = await test_verify_correct_otp(client, otp_code)
    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_me_rejects_bad_token(client):
    resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer garbage"}
    )
    assert resp.status_code == 401
