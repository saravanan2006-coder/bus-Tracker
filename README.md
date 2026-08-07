# BusTracker

Live village-to-village bus tracking for Tamil Nadu's tier-2/3 cities. Drivers
share GPS from their phones; the public tracks any bus with **no login**,
navigating by **district → village pair** (e.g. Villupuram → "Tindivanam →
Gingee"). Tamil-first with an English toggle.

```
Drivers (Android)                    Public (Android/iOS/Web)
 ┌──────────────────┐                ┌──────────────────────────┐
 │ start village     │  OTP login    │ district auto-detect     │
 │ stop village      │─────────────► │ village search           │
 │ OSRM polyline     │               │ live map + ETA + stops   │
 │ auto-attach stops │               │ favorites (device-only)  │
 └────────┬─────────┘                └────────────┬─────────────┘
          │ GPS 5s/15s                WebSocket   │ REST
          ▼                             │         │
 FastAPI  ┌─────────────────────────────┼─────────┴─────────────┐
          │ /driver/*  /public/*  /ws/bus/{id}                 │
          │ tracking  ·  ETA  ·  OSRM  ·  alerts ·  admin      │
          ├───────────────────────────────────────────────────┤
 Redis (Upstash): live positions + pub/sub fan-out             │
 Postgres + PostGIS (Supabase): villages, routes, trips, points│
 OSRM (public router): route polylines + snapping              │
 └─────────────────────────────────────────────────────────────┘
```

## Repo layout

```
bus-tracker/
├── backend/            FastAPI service (the whole backend)
│   ├── app/            api/, services/, core/, seed/, utils/
│   ├── migrations/     production Postgres + PostGIS schema (001_initial.sql)
│   ├── scripts/        village ingestion CLIs (ingest_villages.py, ingest_tn_census.py)
│   ├── data/fixtures/  taluk reference lists
│   ├── tests/          pytest suite (36 tests)
│   ├── Dockerfile      container for Render
│   └── requirements.txt
├── mobile/             Flutter app (driver + public in one codebase)
│   ├── lib/            core/, features/driver/, features/public/, shared_widgets/
│   └── test/           unit tests (geo formatting, JSON models)
└── render.yaml         Render Blueprint for the API service
```

## Backend

### Local development

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env

uvicorn app.main:app --reload          # http://localhost:8000/docs
python -m pytest -q                    # 36 tests
```

Defaults run on SQLite with an in-memory broker (no external services) so the
full flow works out of the box. Seed demo data:

```bash
python -m app.seed.demo_data           # real TN districts/taluks/towns
```

### Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `ENVIRONMENT` | `dev` | `dev` / `test` / `prod` |
| `DATABASE_URL` | `sqlite+aiosqlite:///./bus_tracker.db` | Async SQLAlchemy URL; `postgresql+asyncpg://...` in prod |
| `USE_POSTGIS` | `false` | `true` when Postgres runs the spatial migration |
| `REDIS_URL` | `redis://localhost:6379/0` | Upstash/Redis URL; empty → in-memory broker |
| `REDIS_ENABLED` | `true` | set `false` in dev/tests for the in-memory fallback |
| `JWT_SECRET` | `change-me-in-production` | **generate**: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ADMIN_API_KEY` | `change-me-admin` | header `X-Admin-Key` for `/admin/*` |
| `SMS_PROVIDER` | `console` | `console` prints OTPs to logs; `msg91` / `twilio` in prod |
| `OSRM_BASE_URL` | `https://router.project-osrm.org` | OSRM routing server |
| `STALE_AFTER_SECONDS` | `60` | position considered stale after N seconds |
| `ANOMALY_MAX_SPEED_KMH` | `130` | speed anomaly threshold |

### API summary

All routes are under `/api/v1` (docs at `/docs`).

| Area | Endpoints |
| --- | --- |
| Auth | `POST /auth/driver/otp` · `POST /auth/driver/verify` · `POST /auth/refresh` · `GET /auth/me` |
| Driver | `POST /driver/buses` · `GET /driver/buses` · `GET /driver/routes` |
| Trips | `POST /driver/trips` · `GET /driver/trips/active` · `POST /driver/trips/{id}/end` |
| Public | `GET /districts` · `GET /districts/{id}/taluks` · `GET /districts/{id}/taluks/{id}/villages` · `GET /routes/find` · `GET /routes/{id}` · `GET /buses/search` · `GET /buses/{id}` · `GET /buses/{id}/history` · `POST /favorites` · `GET /favorites` · `DELETE /favorites/{id}` · `POST /alerts` |
| Realtime | `WS /ws/bus/{bus_id}` — last position immediately, then live stream |
| Admin | `GET /admin/stats` · `POST /admin/buses/{id}/approve` · `/reject` · `POST /admin/routes/{id}/verify` |

## Mobile

One Flutter app contains both driver and public experiences, split by feature.

```bash
cd mobile
flutter pub get
flutter analyze                       # must be clean
flutter test                          # 17 tests
flutter run                           # pick a connected device/emulator
```

App settings are read from `lib/core/config.dart`; point the API base URL at
your backend.

**Get an APK without an Android SDK:** every push to `main` triggers the
`.github/workflows/apk-build.yml` workflow, which runs `flutter analyze`,
`flutter test`, builds a signed release APK, and uploads it as a build
artifact. Download it from the workflow run page and install it on any
Android phone.

To build locally on a machine with the Android SDK:

```bash
flutter build apk --release
```

## Village data pipeline

Villages come from three sources merged by `scripts/ingest_villages.py`:
Census 2011 Village Directory CSV, TNRD revenue village lists, and OSM
(`place=village/town`) via Overpass. The pipeline reconciles each taluk against
expected counts and **blocks publishing** if any taluk is under count, so a
village is never silently dropped.

The **authoritative path** ingests the TN e-Governance
district-block-village-habitation census file (`tn_dist_blk_vill_hab_0_1.csv`).
That file predates the 2019 district split, so it is scoped by district code
and its block names become the taluk level; expected per-block counts are
rebased on the file itself (`data/fixtures/villupuram_expected.csv`). OSM
coordinates are attached to villages whose names match unambiguously; the rest
are searchable but flagged for review until coordinates are added. The census
file lists rural villages only, so the district's urban towns (Villupuram,
Tindivanam, Gingee, Ulundurpet, …) are filled from the OSM extract by
`merge_osm_places`, which pins known towns to their curated block and assigns
the remainder to the nearest block centroid.

```bash
cd backend
# 1. Ingest the full authoritative list for the old Villupuram district
#    (22 blocks, 1099 villages; district code 4).
#    Attach OSM coordinates by unambiguous name match, then merge the
#    urban towns missing from the census file.
python -m scripts.ingest_tn_census \
    --input ../tn_dist_blk_vill_hab_0_1.csv \
    --district Villupuram --district-code 4 \
    --osm data/census_villupuram.csv \
    --expected-file data/fixtures/villupuram_expected.csv
```

The OSM-only path still exists as a lightweight option — it builds an extract
(assigning taluk by nearest HQ) and reconciles against the same fixture:

```bash
# 1. Build an OSM-derived extract (assigns taluk by nearest HQ)
python -m scripts.build_osm_extract --input osm_elements.json \
    --out data/census_villupuram.csv
# 2. Ingest and reconcile (blocks publishing on incomplete data)
python -m scripts.ingest_villages --census data/census_villupuram.csv \
    --district Villupuram --expected-file data/fixtures/villupuram_expected.csv
```

Note: `data/census_villupuram.csv` is a real OSM extract (632 places). OSM
covers only a fraction of the district, so an OSM-only run **blocks publishing**
(e.g. Tindivanam 18/174, Gingee 7/166) with `dropped: []` — nothing is silently
lost. The TN census file above clears the gate (1099 villages plus merged towns,
`dropped: []`, `blocks_publishing: false`).

## Deploying the free-tier prototype

1. **Supabase** — create a project, then run `backend/migrations/001_initial.sql`
   in the SQL editor (enables PostGIS and creates all tables/indexes).
2. **Upstash Redis** — create a database; copy the `redis://` URL.
3. **Render** — push the repo, then use `render.yaml` (Blueprint) to deploy the
   API as a Docker web service on the free plan. Set `DATABASE_URL`,
   `REDIS_URL`, `JWT_SECRET`, and `ADMIN_API_KEY` as secrets.
4. **UptimeRobot** — ping `GET /health` every 5 minutes to keep the free
   instance awake.
5. **App** — point the mobile client at the Render URL, then run the village
   ingestion and seed data.

Free-tier notes: Render free instances sleep after ~15 min of inactivity
(UptimeRobot mitigates this); `location_points` is partitioned by month so
retention pruning stays cheap; the SMS provider is `console` until a real
provider is added.

## Load testing

A locust scenario in `backend/locustfile.py` exercises the anonymous public
paths and keeps open WebSocket streams:

```bash
cd backend
pip install -r requirements-dev.txt
locust --host https://bustracker.onrender.com --users 200 --spawn-rate 20 \
    --run-time 3m --only-summary
```

## Design decisions

- **No public accounts** — public users are anonymous; favorites are keyed to a
  per-device UUID stored in secure storage.
- **Minimal driver flow** — drivers only pick start/stop village. The backend
  snaps both to the road network via OSRM, computes the polyline, and
  auto-attaches nearby villages as stops (~1.5 km).
- **5 s moving / 15 s stopped** GPS interval to keep bandwidth and battery
  low; anomalies (overspeed, off-route) are flagged server-side.
- **Postgres as system of record**, Redis only as a hot cache + pub/sub
  fan-out; the in-memory fallback keeps dev/test dependency-free.
