# Admin runbook (API)

Every endpoint below lives under `/api/v1/admin` and is gated by a static
key sent as the `X-Admin-Key` header. The key is `ADMIN_API_KEY` (default
`change-me-admin`). **Set a real key in production** and treat it as a
secret. The public app never calls these routes.

> There is no admin UI on purpose: the free-tier prototype keeps the surface
> tiny. These curl commands are the whole workflow. Run them from anywhere
> that can reach the API.

Set the variables once:

```bash
BASE=http://localhost:8000/api/v1           # or https://your-app.onrender.com/api/v1
KEY=change-me-admin
ADMIN='-H "X-Admin-Key: '"$KEY"'"'         # reuse below as $ADMIN
```

## 1. Platform health

```bash
curl -s http://localhost:8000/health          # liveness probe
curl -s $ADMIN "$BASE/admin/stats"            # platform stats
```

Example output:

```json
{"ok":true,"data":{"districts":31,"taluks":385,"villages":26822,
 "buses":3,"verified_buses":1,"drivers":2,"routes":2,"active_trips":1}}
```

Use `stats` to answer "what needs attention today": `buses` with
`verified_buses` below it are waiting on you.

## 2. Review pending bus registrations

Drivers register a bus after their OTP login; it lands with status
`pending`. List them:

```bash
curl -s $ADMIN "$BASE/admin/buses?status=pending"
curl -s $ADMIN "$BASE/admin/buses?status=approved"   # history
curl -s $ADMIN "$BASE/admin/buses?status=rejected"
```

Each item carries `bus_number`, `rto_number`, `bus_type`, `driver_id`,
`photo_path`, and `created_at`. Cross-check the RTO number and the photo (if
any) against the real vehicle before approving.

## 3. Approve or reject a bus

```bash
curl -s $ADMIN -X POST "$BASE/admin/buses/1/approve"
curl -s $ADMIN -X POST "$BASE/admin/buses/1/reject" \
  -H 'Content-Type: application/json' \
  -d '{"reason": "RTO photo does not match vehicle"}'
```

Only approved buses appear in public search, and only approved buses may be
assigned a route. The rejection reason is stored and shown to the driver.

## 4. Verify a driver-built route

When a driver builds a route (start village -> stop village, polyline from
OSRM, nearby villages auto-attached as stops), it starts as `unverified`.
Drivers cannot start a trip until the route is active:

```bash
curl -s $ADMIN -X POST "$BASE/admin/routes/1/verify"
```

Check the polyline geometry in `/docs` (`GET /api/v1/routes/{id}`) if you
want to eyeball it first.

## 5. End-to-end: what produces the queue

The items you review come from the driver flow. To exercise it against a dev
server (or to sanity-check a staging instance), run the OTP login loop:

```bash
# 1. request an OTP (printed to backend logs with SMS_PROVIDER=console)
curl -s -X POST "$BASE/auth/driver/otp" -H 'Content-Type: application/json' \
  -d '{"phone":"+919876543210"}'
# 2. verify it and capture the access token from the response
curl -s -X POST "$BASE/auth/driver/verify" -H 'Content-Type: application/json' \
  -d '{"phone":"+919876543210","otp":"123456"}'
TOKEN=eyJ...
AUTH="-H 'Authorization: Bearer '"$TOKEN"'"

# 3. register a bus (appears in admin/buses as pending)
curl -s $AUTH -X POST "$BASE/driver/buses" -H 'Content-Type: application/json' \
  -d '{"bus_number":"TN 57 AB 1234","rto_number":"TN57-AB-1234","bus_type":"govt","bus_name":"Town Bus"}'

# 4. build a route between two villages (village ids from /districts/{id}/villages)
curl -s $AUTH -X POST "$BASE/driver/routes/build" -H 'Content-Type: application/json' \
  -d '{"district_id":1,"from_village_id":100,"to_village_id":200}'

# 5. assign the route, then start a trip
curl -s $AUTH -X POST "$BASE/driver/buses/1/assign-route" -H 'Content-Type: application/json' \
  -d '{"route_id":1}'
curl -s $AUTH -X POST "$BASE/driver/trips" -H 'Content-Type: application/json' \
  -d '{"bus_id":1,"route_id":1}'
```

After step 3 the bus shows up in `GET /admin/buses?status=pending`; after
step 4 the route shows up for `POST /admin/routes/{id}/verify`.

## Production notes

- `ADMIN_API_KEY` is compared with a constant-time digest; there is no way to
  read it back through the API.
- The key is a shared static secret, not a per-admin credential. If you need
  multiple admins with audit trails later, swap `require_admin` in
  `app/api/admin.py` for a role check on a real auth token.
- Logs never include the key. Do not paste `X-Admin-Key` values into tickets
  or screenshots.
