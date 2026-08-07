-- BusTracker production schema for PostgreSQL (with PostGIS).
-- The ORM creates the same tables on SQLite for dev/tests; this migration
-- adds spatial indexes and generated geometry columns for production scale.

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS districts (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(80) NOT NULL UNIQUE,
    name_ta     VARCHAR(80),
    code        VARCHAR(10),
    lat         DOUBLE PRECISION,
    lng         DOUBLE PRECISION,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS taluks (
    id          SERIAL PRIMARY KEY,
    district_id INTEGER NOT NULL REFERENCES districts(id) ON DELETE CASCADE,
    name        VARCHAR(80) NOT NULL,
    name_ta     VARCHAR(80),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (district_id, name)
);

CREATE TABLE IF NOT EXISTS villages (
    id              SERIAL PRIMARY KEY,
    district_id     INTEGER NOT NULL REFERENCES districts(id),
    taluk_id        INTEGER NOT NULL REFERENCES taluks(id),
    name            VARCHAR(120) NOT NULL,
    name_normalized VARCHAR(120) NOT NULL,
    name_ta         VARCHAR(120),
    place_type      VARCHAR(20) NOT NULL DEFAULT 'village',
    lat             DOUBLE PRECISION,
    lng             DOUBLE PRECISION,
    geom            geography(POINT, 4326) GENERATED ALWAYS AS (
        ST_SetSRID(ST_MakePoint(lng, lat), 4326)
    ) STORED,
    census_code     VARCHAR(20),
    source          VARCHAR(20) NOT NULL DEFAULT 'census',
    has_coords      BOOLEAN NOT NULL DEFAULT FALSE,
    needs_review    BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (taluk_id, name_normalized)
);

CREATE INDEX IF NOT EXISTS ix_villages_name        ON villages (name);
CREATE INDEX IF NOT EXISTS ix_villages_district    ON villages (district_id);
CREATE INDEX IF NOT EXISTS ix_villages_taluk       ON villages (taluk_id);
CREATE INDEX IF NOT EXISTS ix_villages_geom        ON villages USING GIST (geom);

-- Village lookup by taluk + prefix search is the hottest public query.
CREATE INDEX IF NOT EXISTS ix_villages_taluk_name  ON villages (taluk_id, name_normalized);

CREATE TABLE IF NOT EXISTS drivers (
    id          SERIAL PRIMARY KEY,
    phone       VARCHAR(20) NOT NULL UNIQUE,
    name        VARCHAR(120),
    language    VARCHAR(8) NOT NULL DEFAULT 'ta',
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    fcm_token   VARCHAR(255),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS otp_codes (
    id          SERIAL PRIMARY KEY,
    phone       VARCHAR(20) NOT NULL,
    code_hash   VARCHAR(128) NOT NULL,
    purpose     VARCHAR(20) NOT NULL DEFAULT 'driver_login',
    attempts    INTEGER NOT NULL DEFAULT 0,
    consumed    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_otp_phone    ON otp_codes (phone);
CREATE INDEX IF NOT EXISTS ix_otp_expires  ON otp_codes (expires_at);

CREATE TABLE IF NOT EXISTS routes (
    id                  SERIAL PRIMARY KEY,
    district_id         INTEGER NOT NULL REFERENCES districts(id),
    from_village_id     INTEGER NOT NULL REFERENCES villages(id),
    to_village_id       INTEGER NOT NULL REFERENCES villages(id),
    polyline            JSONB NOT NULL,
    distance_m          DOUBLE PRECISION,
    duration_estimate_min DOUBLE PRECISION,
    source              VARCHAR(20) NOT NULL DEFAULT 'driver_built',
    status              VARCHAR(20) NOT NULL DEFAULT 'unverified',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_routes_district ON routes (district_id);
CREATE INDEX IF NOT EXISTS ix_routes_from_to  ON routes (from_village_id, to_village_id);
CREATE INDEX IF NOT EXISTS ix_routes_status   ON routes (status);

CREATE TABLE IF NOT EXISTS route_stops (
    id          SERIAL PRIMARY KEY,
    route_id    INTEGER NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
    village_id  INTEGER NOT NULL REFERENCES villages(id),
    seq         INTEGER NOT NULL,
    progress    DOUBLE PRECISION NOT NULL,
    UNIQUE (route_id, village_id)
);
CREATE INDEX IF NOT EXISTS ix_route_stops_route ON route_stops (route_id);

CREATE TABLE IF NOT EXISTS buses (
    id                  SERIAL PRIMARY KEY,
    driver_id           INTEGER NOT NULL REFERENCES drivers(id),
    bus_number          VARCHAR(30) NOT NULL,
    bus_name            VARCHAR(120),
    bus_type            VARCHAR(20) NOT NULL DEFAULT 'govt',
    rto_number          VARCHAR(30) NOT NULL,
    route_id            INTEGER REFERENCES routes(id),
    photo_path          VARCHAR(255),
    verification_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    rejected_reason     TEXT,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    verified_at         TIMESTAMPTZ,
    UNIQUE (bus_number, rto_number)
);
CREATE INDEX IF NOT EXISTS ix_buses_number ON buses (bus_number);
CREATE INDEX IF NOT EXISTS ix_buses_rto    ON buses (rto_number);
CREATE INDEX IF NOT EXISTS ix_buses_status ON buses (verification_status);
CREATE INDEX IF NOT EXISTS ix_buses_route  ON buses (route_id);

CREATE TABLE IF NOT EXISTS trips (
    id          SERIAL PRIMARY KEY,
    driver_id   INTEGER NOT NULL REFERENCES drivers(id),
    bus_id      INTEGER NOT NULL REFERENCES buses(id),
    route_id    INTEGER REFERENCES routes(id),
    status      VARCHAR(20) NOT NULL DEFAULT 'active',
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at    TIMESTAMPTZ,
    total_points INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_trips_bus_active ON trips (bus_id, status);

-- Time-series location data: partitioned by month for retention-friendly
-- pruning. Orphaned partitions are cleaned by a nightly job.
CREATE TABLE IF NOT EXISTS location_points (
    id          BIGSERIAL,
    trip_id     INTEGER NOT NULL REFERENCES trips(id),
    bus_id      INTEGER NOT NULL REFERENCES buses(id),
    route_id    INTEGER REFERENCES routes(id),
    lat         DOUBLE PRECISION NOT NULL,
    lng         DOUBLE PRECISION NOT NULL,
    geom        geography(POINT, 4326) GENERATED ALWAYS AS (
        ST_SetSRID(ST_MakePoint(lng, lat), 4326)
    ) STORED,
    speed_kmh   DOUBLE PRECISION,
    heading     DOUBLE PRECISION,
    ts          TIMESTAMPTZ NOT NULL,
    is_anomalous BOOLEAN NOT NULL DEFAULT FALSE,
    off_route_m DOUBLE PRECISION,
    PRIMARY KEY (id, ts)
) PARTITION BY RANGE (ts);

CREATE INDEX IF NOT EXISTS ix_locations_bus_ts ON location_points (bus_id, ts);
CREATE INDEX IF NOT EXISTS ix_locations_route_ts ON location_points (route_id, ts);
CREATE INDEX IF NOT EXISTS ix_locations_geom ON location_points USING GIST (geom);

CREATE TABLE IF NOT EXISTS favorites (
    id              SERIAL PRIMARY KEY,
    device_id       VARCHAR(64) NOT NULL,
    from_village_id INTEGER NOT NULL REFERENCES villages(id),
    to_village_id   INTEGER NOT NULL REFERENCES villages(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (device_id, from_village_id, to_village_id)
);
CREATE INDEX IF NOT EXISTS ix_favorites_device ON favorites (device_id);

CREATE TABLE IF NOT EXISTS alert_subscriptions (
    id              SERIAL PRIMARY KEY,
    device_id       VARCHAR(64) NOT NULL,
    bus_id          INTEGER NOT NULL REFERENCES buses(id),
    stop_village_id INTEGER NOT NULL REFERENCES villages(id),
    fcm_token       VARCHAR(255),
    distance_m      DOUBLE PRECISION NOT NULL DEFAULT 1000,
    triggered       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_alert_sub_bus_stop ON alert_subscriptions (bus_id, stop_village_id);
CREATE INDEX IF NOT EXISTS ix_alert_sub_device  ON alert_subscriptions (device_id);
