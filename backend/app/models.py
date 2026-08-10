"""SQLAlchemy ORM models for BusTracker.

Geometry is stored as plain lat/lng floats plus JSON polylines so the
application runs identically on SQLite (dev/test) and PostgreSQL (prod).
A PostGIS-enabled migration (migrations/001_initial.sql) adds spatial
indexes and generated geometry columns on PostgreSQL for scale.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.sqlite import JSONType


class Driver(Base):
    __tablename__ = "drivers"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(120))
    language: Mapped[str] = mapped_column(String(8), default="ta")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    fcm_token: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    buses: Mapped[list["Bus"]] = relationship(back_populates="driver")


class OtpCode(Base):
    __tablename__ = "otp_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), index=True)
    code_hash: Mapped[str] = mapped_column(String(128))
    purpose: Mapped[str] = mapped_column(String(20), default="driver_login")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Bus(Base):
    __tablename__ = "buses"
    __table_args__ = (
        Index("ix_buses_number", "bus_number"),
        Index("ix_buses_rto", "rto_number"),
        UniqueConstraint("bus_number", "rto_number", name="uq_bus_number_rto"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"))
    bus_number: Mapped[str] = mapped_column(String(30))
    bus_name: Mapped[str | None] = mapped_column(String(120))
    bus_type: Mapped[str] = mapped_column(String(20), default="govt")  # govt|private
    rto_number: Mapped[str] = mapped_column(String(30))
    route_id: Mapped[int | None] = mapped_column(ForeignKey("routes.id"), nullable=True)
    photo_path: Mapped[str | None] = mapped_column(String(255))
    verification_status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True
    )  # pending|approved|rejected
    rejected_reason: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    driver: Mapped["Driver"] = relationship(back_populates="buses")
    route: Mapped["Route | None"] = relationship(back_populates="buses")


class District(Base):
    __tablename__ = "districts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    name_ta: Mapped[str | None] = mapped_column(String(80))
    code: Mapped[str | None] = mapped_column(String(10), index=True)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    taluks: Mapped[list["Taluk"]] = relationship(
        back_populates="district", cascade="all, delete-orphan"
    )


class Taluk(Base):
    __tablename__ = "taluks"
    __table_args__ = (UniqueConstraint("district_id", "name", name="uq_taluk_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"))
    name: Mapped[str] = mapped_column(String(80))
    name_ta: Mapped[str | None] = mapped_column(String(80))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    district: Mapped["District"] = relationship(back_populates="taluks")
    villages: Mapped[list["Village"]] = relationship(
        back_populates="taluk", cascade="all, delete-orphan"
    )


class Village(Base):
    __tablename__ = "villages"
    __table_args__ = (
        Index("ix_villages_name", "name"),
        Index("ix_villages_district", "district_id"),
        Index("ix_villages_taluk", "taluk_id"),
        # census_code is part of identity: two villages in the same taluk may
        # legitimately share a name but carry different official census codes
        # (e.g. Madurai's intra-block duplicates). Merging them by name alone
        # would silently drop a government-listed village.
        UniqueConstraint(
            "taluk_id",
            "name_normalized",
            "census_code",
            name="uq_village_taluk_name_code",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"))
    taluk_id: Mapped[int] = mapped_column(ForeignKey("taluks.id"))
    name: Mapped[str] = mapped_column(String(120))
    name_normalized: Mapped[str] = mapped_column(String(120))
    name_ta: Mapped[str | None] = mapped_column(String(120))
    place_type: Mapped[str] = mapped_column(String(20), default="village")
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    census_code: Mapped[str | None] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(20), default="census")
    has_coords: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)

    taluk: Mapped["Taluk"] = relationship(back_populates="villages")
    district: Mapped["District"] = relationship()


class Route(Base):
    __tablename__ = "routes"
    __table_args__ = (
        Index("ix_routes_district", "district_id"),
        Index("ix_routes_from_to", "from_village_id", "to_village_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"))
    from_village_id: Mapped[int] = mapped_column(ForeignKey("villages.id"))
    to_village_id: Mapped[int] = mapped_column(ForeignKey("villages.id"))
    # polyline as list of [lat, lng] pairs (GeoJSON LineString coordinates).
    polyline: Mapped[list] = mapped_column(JSONType, nullable=False)
    distance_m: Mapped[float | None] = mapped_column(Float)
    duration_estimate_min: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(20), default="driver_built")
    status: Mapped[str] = mapped_column(String(20), default="unverified", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    from_village: Mapped["Village"] = relationship(foreign_keys=[from_village_id])
    to_village: Mapped["Village"] = relationship(foreign_keys=[to_village_id])
    stops: Mapped[list["RouteStop"]] = relationship(
        back_populates="route", cascade="all, delete-orphan"
    )
    buses: Mapped[list["Bus"]] = relationship(back_populates="route")


class RouteStop(Base):
    __tablename__ = "route_stops"
    __table_args__ = (UniqueConstraint("route_id", "village_id", name="uq_route_stop"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"))
    village_id: Mapped[int] = mapped_column(ForeignKey("villages.id"))
    seq: Mapped[int] = mapped_column(Integer)
    progress: Mapped[float] = mapped_column(Float)  # 0.0 -> 1.0 along the route

    route: Mapped["Route"] = relationship(back_populates="stops")
    village: Mapped["Village"] = relationship()


class Trip(Base):
    __tablename__ = "trips"
    __table_args__ = (Index("ix_trips_bus_active", "bus_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"))
    bus_id: Mapped[int] = mapped_column(ForeignKey("buses.id"))
    route_id: Mapped[int | None] = mapped_column(ForeignKey("routes.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_points: Mapped[int] = mapped_column(Integer, default=0)

    locations: Mapped[list["LocationPoint"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan"
    )


class LocationPoint(Base):
    __tablename__ = "location_points"
    __table_args__ = (
        Index("ix_locations_trip_ts", "trip_id", "ts"),
        Index("ix_locations_bus_ts", "bus_id", "ts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"))
    bus_id: Mapped[int] = mapped_column(ForeignKey("buses.id"))
    route_id: Mapped[int | None] = mapped_column(ForeignKey("routes.id"), nullable=True)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    speed_kmh: Mapped[float | None] = mapped_column(Float)
    heading: Mapped[float | None] = mapped_column(Float)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    is_anomalous: Mapped[bool] = mapped_column(Boolean, default=False)
    off_route_m: Mapped[float | None] = mapped_column(Float)

    trip: Mapped["Trip"] = relationship(back_populates="locations")


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (
        UniqueConstraint(
            "device_id", "from_village_id", "to_village_id", name="uq_favorite"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    from_village_id: Mapped[int] = mapped_column(ForeignKey("villages.id"))
    to_village_id: Mapped[int] = mapped_column(ForeignKey("villages.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AlertSubscription(Base):
    __tablename__ = "alert_subscriptions"
    __table_args__ = (
        Index("ix_alert_sub_bus_stop", "bus_id", "stop_village_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    bus_id: Mapped[int] = mapped_column(ForeignKey("buses.id"))
    stop_village_id: Mapped[int] = mapped_column(ForeignKey("villages.id"))
    fcm_token: Mapped[str | None] = mapped_column(String(255))
    distance_m: Mapped[float] = mapped_column(Float, default=1000.0)
    triggered: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    bus: Mapped["Bus"] = relationship()
    stop_village: Mapped["Village"] = relationship()
