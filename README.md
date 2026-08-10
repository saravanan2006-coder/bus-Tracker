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
│   ├── scripts/        village ingestion CLIs + migration runner + coord enrichment
│   ├── data/fixtures/  taluk reference lists + expected-count fixtures
│   ├── tests/          pytest suite (59 tests)
│   ├── Dockerfile      container for Render
│   └── requirements.txt
├── mobile/             Flutter app (driver + public in one codebase)
│   ├── lib/            core/, features/driver/, features/public/, shared_widgets/
│   └── test/           unit tests (geo formatting, JSON models)
├── docs/               runbooks (docs/ADMIN.md)
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
python -m pytest -q                    # 59 tests
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
| `FCM_ENABLED` | `false` | `true` to send real Firebase Cloud Messaging pushes |
| `FCM_CREDENTIALS_FILE` | `` | path to the Firebase service-account JSON |
| `ALERT_WORKER` | unset | set `1` to run the alert→push worker in-process (see below) |
| `RUN_DEMO_BUS` | unset | set `1` to run the simulated demo bus in-process |

### API summary

All routes are under `/api/v1` (docs at `/docs`).

| Area | Endpoints |
| --- | --- |
| Auth | `POST /auth/driver/otp` · `POST /auth/driver/verify` · `POST /auth/refresh` · `GET /auth/me` |
| Driver | `POST /driver/buses` · `GET /driver/buses` · `GET /driver/routes` |
| Trips | `POST /driver/trips` · `GET /driver/trips/active` · `POST /driver/trips/{id}/end` |
| Public | `GET /districts` · `GET /districts/{id}/taluks` · `GET /districts/{id}/taluks/{id}/villages` · `GET /routes/find` · `GET /routes/{id}` · `GET /buses/search` · `GET /buses/{id}` · `GET /buses/{id}/history` · `POST /favorites` · `GET /favorites` · `DELETE /favorites/{id}` · `POST /alerts` |
| Realtime | `WS /ws/bus/{bus_id}` — last position immediately, then live stream |
| Admin | `GET /admin/stats` · `POST /admin/buses/{id}/approve` · `/reject` · `POST /admin/routes/{id}/verify` — full curl runbook in `docs/ADMIN.md` |

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

## Push alerts worker

`POST /api/v1/alerts` lets a guest subscribe to "notify me when bus X gets
within N metres of my stop". Delivery is handled by a background worker that
runs inside the backend process (`ALERT_WORKER=1`):

- every 10s it scans subscriptions for buses with a fresh live position;
- when a bus crosses within `distance_m` of the requested stop it sends an
  FCM push (`app/services/push_service.py`) and marks the subscription
  `triggered`, so each approach yields exactly one notification;
- once the bus leaves the radius the subscription re-arms for the next trip.

Without `FCM_CREDENTIALS_FILE` the worker uses a `NoopPushSender` that logs
instead of sending, so the full flow runs in dev and is covered by tests.

### Mobile side (Firebase Cloud Messaging)

The Flutter client uses the Firebase packages **only when configured** — with
no Firebase project it compiles and runs fine (guarded by
`lib/core/push/push_service.dart`). To enable real pushes:

1. Create a Firebase project and add a web app to it.
2. Run the app with the web-app credentials as dart-defines:

```bash
cd mobile
flutter run --dart-define=FIREBASE_API_KEY=... \
  --dart-define=FIREBASE_APP_ID=... \
  --dart-define=FIREBASE_MESSAGING_SENDER_ID=... \
  --dart-define=FIREBASE_PROJECT_ID=...
```

3. Backend: set `FCM_ENABLED=true` and `FCM_CREDENTIALS_FILE` to the
   service-account JSON, and run with `ALERT_WORKER=1`.

Android initializes Firebase programmatically at startup (no
`google-services.json` or Gradle plugin needed), so the APK build stays
dependency-free. Foreground pushes surface as an in-app SnackBar via the
global messenger key in `lib/main.dart`; background/terminated pushes open
the app through `FirebaseMessaging.onMessageOpenedApp`.

## Village data pipeline

Villages come from two authoritative layers merged by the ingestion CLIs:
the TN e-Governance census file and OSM (`place=village/town`) via Overpass.
The pipeline reconciles each taluk against expected counts and **blocks
publishing** if any taluk is under count, so a village is never silently
dropped. Two villages in one block that share a name but carry different
official census codes (Madurai has intra-block duplicates) are kept as
separate rows — `census_code` is part of the `villages` identity, so merging
them by name alone would silently lose a government-listed village.

The **authoritative path** ingests the TN e-Governance
district-block-village-habitation census file (`tn_dist_blk_vill_hab_0_1.csv`,
all 31 districts). That file predates the 2019 district split, so it is scoped
by district code and its block names become the taluk level; expected per-block
counts are rebased on the file itself and written to
`data/fixtures/<district>_expected.csv`. OSM coordinates are attached to
villages whose names match unambiguously; the rest are searchable but flagged
for review until coordinates are added. The census file lists rural villages
only, so the district's urban towns are filled from the OSM extract by
`merge_osm_places`, which pins known towns to their curated block and assigns
the remainder to the nearest block centroid.

```bash
cd backend
# 1. (optional) Fetch an OSM place extract for a district. Queries Overpass for
#    the district admin area (admin_level=5) and writes data/census_<slug>.csv.
#    A real User-Agent is required — Overpass 406s bare clients.
python -m scripts.build_osm_extract --district Madurai

# 2. Ingest the full authoritative list for the district (Madurai = code 20).
#    Attach OSM coordinates by unambiguous name match, then merge the urban
#    towns missing from the census file.
python -m scripts.ingest_tn_census \
    --input ../tn_dist_blk_vill_hab_0_1.csv \
    --district Madurai --district-code 20 \
    --osm data/census_madurai.csv \
    --expected-file data/fixtures/madurai_expected.csv
```

The same commands work for any district — e.g. Villupuram (`--district-code 4`,
extract `data/census_villupuram.csv`, fixture `villupuram_expected.csv`) and
Theni (`--district-code 21`, `data/census_theni.csv`). Ingesting is
idempotent: census rows are matched by official code and towns by name, so a
re-run upgrades coordinates and town classification without duplicating rows.

To fetch OSM extracts **and** enrich every Census-2011 district in one pass
(the `scripts/enrich_all_districts.py` driver):

```bash
cd backend
python -m scripts.enrich_all_districts --input ../tn_dist_blk_vill_hab_0_1.csv
```

It runs `build_osm_extract` then `ingest_tn_census` per district, pauses
~30 s between Overpass queries to respect the public API's rate limit, and
reports each district's reconciliation. Re-running is safe (idempotent) —
use `--only Madurai,Theni` to spot-check one district and `--no-extract` to
reuse the saved `data/census_<slug>.csv` files.

The OSM-only path still exists as a lightweight option — it ingests an extract
with no census backing and reconciles against a fixture, so it **blocks
publishing** whenever the extract under-covers a taluk:

```bash
python -m scripts.ingest_villages --census data/census_madurai.csv \
    --district Madurai --expected-file data/fixtures/madurai_expected.csv
```

Note: the extracts are real OSM snapshots for the current district admin areas
(`data/census_<district>.csv`). OSM covers only a fraction of a district, so an
OSM-only run **blocks publishing** on any taluk it under-covers, with
`dropped: []` — nothing is silently lost. The TN census file above clears the
gate for every block (e.g. Villupuram 1059/1059 census villages, Madurai
420/420, Theni 130/130, plus merged towns; `dropped: []`,
`blocks_publishing: false`).

**Current dataset:** all 31 districts are ingested from the authoritative
census file and enriched with OSM coordinates — 26,822 villages total
(census villages + OSM towns/hamlets merged in), 17,002 with coordinates and
3,857 with Tamil names (from OSM `name:ta`). Census rows are matched by their
official per-block code, so the reconciliation gate never drops a listed
village; the ones OSM could not place are searchable but flagged
(`needs_review`, `has_coords=false`). OSM admin-area spellings that differ
from the census names (Tiruvallur→Thiruvallur, Thoothukkudi→Thoothukudi,
The Nilgiris→Nilgiris, Tiruvarur→Thiruvarur, Villupuram→Viluppuram) are
handled in `build_osm_extract.AREA_NAME_ALIASES`.

## Local real-stack (Postgres + Redis)

The suite normally runs on SQLite so it stays dependency-free. To exercise the
same suite against the production dialect, spin up the local Postgres (with
PostGIS) + Redis stack and point the tests at it:

```bash
docker compose up -d                          # applies migrations/001_initial.sql
cd backend
TEST_DATABASE_URL=postgresql+asyncpg://bustracker:bustracker@localhost:5432/bustracker_test \
    python -m pytest                          # same 59 tests, on Postgres
```

To apply (or patch) the schema on an already-running Postgres instead of a
fresh volume, use the migration runner — it records applied files in a
`schema_migrations` table so re-runs and additive migrations are safe:

```bash
python -m scripts.migrate                      # uses DATABASE_URL
python -m scripts.migrate --dry-run            # list pending files only
```

On Postgres the fixtures drop and recreate the schema per test (the prod
migration is additive on top of the ORM schema). Redis is intentionally kept
out of the test run (`REDIS_ENABLED=false`) so tests stay deterministic; the
in-memory store/broker is what the worker and demo bus use in dev.

## Deploying the free-tier prototype

1. **Supabase** — create a project, then run `backend/migrations/001_initial.sql`
   in the SQL editor (enables PostGIS and creates all tables/indexes), or apply
   it programmatically with `python -m scripts.migrate`.
2. **Upstash Redis** — create a database; copy the `redis://` URL.
3. **Render** — push the repo, then use `render.yaml` (Blueprint) to deploy the
   API as a Docker web service on the free plan. Set `DATABASE_URL`,
   `REDIS_URL`, `JWT_SECRET`, and `ADMIN_API_KEY` as secrets.
4. **UptimeRobot** — ping `GET /health` every 5 minutes to keep the free
   instance awake.
5. **App** — point the mobile client at the Render URL, then run the village
   ingestion and seed data.
6. **Admin** — see `docs/ADMIN.md` for the curl workflow (approve buses,
   verify routes, watch platform stats).

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
