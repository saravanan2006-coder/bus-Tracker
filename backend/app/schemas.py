"""Pydantic request/response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.security import normalize_phone


class ApiResponse(BaseModel):
    ok: bool = True
    data: dict[str, Any] | list[Any] | None = None
    error: str | None = None


# --------------------------------------------------------------------- #
# Auth / driver
# --------------------------------------------------------------------- #
class OtpRequest(BaseModel):
    phone: str

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: str) -> str:
        return normalize_phone(value)


class OtpVerifyRequest(BaseModel):
    phone: str
    otp: str = Field(min_length=4, max_length=8)

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: str) -> str:
        return normalize_phone(value)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    driver_id: int


class DriverOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str
    name: str | None
    language: str


class BusRegisterRequest(BaseModel):
    bus_number: str = Field(min_length=1, max_length=30)
    bus_name: str | None = Field(default=None, max_length=120)
    bus_type: Literal["govt", "private"] = "govt"
    rto_number: str = Field(min_length=3, max_length=30)


class BusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bus_number: str
    bus_name: str | None
    bus_type: str
    rto_number: str
    verification_status: str
    rejected_reason: str | None = None
    route_id: int | None = None


# --------------------------------------------------------------------- #
# Trips
# --------------------------------------------------------------------- #
class TripStartRequest(BaseModel):
    bus_id: int
    route_id: int


class LocationUpdate(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    speed_kmh: float | None = Field(default=None, ge=0, le=200)
    heading: float | None = Field(default=None, ge=0, le=360)
    ts: datetime | None = None


class TripOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bus_id: int
    route_id: int | None
    status: str
    started_at: datetime
    ended_at: datetime | None = None


# --------------------------------------------------------------------- #
# Public: districts / villages / routes
# --------------------------------------------------------------------- #
class DistrictOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    name_ta: str | None
    taluk_count: int = 0
    village_count: int = 0


class TalukOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    district_id: int
    name: str
    name_ta: str | None


class VillageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    taluk_id: int
    district_id: int
    name: str
    name_ta: str | None
    place_type: str
    has_coords: bool


class RouteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    district_id: int
    from_village_id: int
    to_village_id: int
    polyline: list[list[float]]
    distance_m: float | None
    status: str


class RouteWithBuses(BaseModel):
    route: RouteOut
    buses: list[dict[str, Any]]


class FavoriteCreate(BaseModel):
    device_id: str
    from_village_id: int
    to_village_id: int


class AlertSubscribeRequest(BaseModel):
    device_id: str
    bus_id: int
    stop_village_id: int
    fcm_token: str | None = None
    distance_m: float = Field(default=1000.0, ge=100, le=5000)
