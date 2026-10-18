# DhabaGo

Pre-order food from highway dhabas at bus stops your bus hasn't reached yet.

**Live:** https://bus-food-backend.vercel.app
**API docs:** https://bus-food-backend.vercel.app/docs

---

## The problem

Rail passengers in India have had catering since IRCTC e-catering launched — enter a PNR, pick a station ahead, food arrives at your seat. Intercity bus passengers have nothing. The driver picks the dhaba, nobody knows which one until the bus stops, and forty people order at a counter that starts cooking from zero.

A typical halt on NH-334 is 20 minutes. A butter chicken takes 18 minutes to cook. The two numbers never overlapped, because the kitchen only learned about the order when the bus was already parked.

DhabaGo closes that gap: it knows when the bus will reach each stop and how long each kitchen needs, and places the order at the moment that makes the food ready as the bus pulls in.

---

## How it works

Two calculations carry the whole system.

**Arrival time at a stop**

```
ETA = trip.departure_time + stop.minutes_from_origin + trip.current_delay_minutes
```

**Whether the kitchen can still make it**

```
(ETA − now) >= dhaba.avg_prep_time_minutes + 10 minute buffer
```

An order that fails the second check is refused by the API with `409` and a readable reason — *"bus arrives in 0 min but prep needs 25 min"*. The cut-off is enforced server-side, not hidden in the interface.

**Delay propagation.** Buses do not run to the minute. When an operator reports a delay, `PATCH /trips/{id}/delay` recalculates `expected_arrival_time` on every open order for that trip, so each kitchen's deadline moves and stops that had closed for ordering reopen. One request, every affected passenger and kitchen updated.

**AI review summaries.** A passenger has about ninety seconds to choose a dhaba and will not read 287 Google reviews. Dhaba listings pull rating and review text from the Google Places API, condense them to one line with Gemini, and cache the result for 24 hours. The ordering path never blocks on a third-party API, and a failed call falls back to the last good summary.

---

## Three roles, three dashboards

| Role | Sees |
|---|---|
| **Passenger** | Route map with live ETAs, dhabas with ratings and AI summaries, menu, cart, seat number, live order tracker |
| **Dhaba manager** | Incoming queue sorted by bus arrival, status advancement, menu and availability editing |
| **Admin** | Every route, bus and trip; delay reporting; trip scheduling; CRUD over routes, stops, dhabas and menu items |

Role comes from the JWT. The interface hides what a role cannot use, and the API returns `403` regardless — tested both ways.

---

## Stack

Python 3.11 · FastAPI · SQLAlchemy 2.0 · Alembic · Pydantic v2 · PostgreSQL (Neon) · JWT via python-jose and passlib · pytest · Google Places API · Gemini API

Frontend is a single self-contained HTML page served by the same app, so there is one origin and no build step.

Deployed on Vercel as serverless functions with `NullPool`, since a serverless invocation must not hold a pooled connection.

---

## Running it locally

```bash
git clone https://github.com/thakurishan9990-jpg/bus-food-backend
cd bus-food-backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # defaults to SQLite; set DATABASE_URL for Postgres
alembic upgrade head
python -m scripts.seed

uvicorn app.main:app --reload
```

Open http://localhost:8000 for the app, `/docs` for the API.

**Demo accounts** — password `password123`:

| Role | Phone |
|---|---|
| Passenger | `9876543210` |
| Dhaba manager | `9876543211` |

The admin account's password comes from the `ADMIN_PASSWORD` environment variable at seed time; if unset, the seed generates one and prints it.

**Seed data** is the Delhi ISBT Kashmere Gate → Dehradun ISBT corridor on NH-334: five stops (Meerut, Khatauli, Muzaffarnagar, Roorkee, Chhutmalpur) with real coordinates, halt durations and distances, plus dhabas and menus. The seed is idempotent — re-running it updates rather than duplicates — and schedules a week of departures so the demo never goes stale.

---

## Tests

```bash
pytest
```

77 tests covering ETA calculation, the order cut-off, the status machine, role guards, idempotent seeding, and the admin password path. SQLite in-memory, `respx` for the external APIs.

---

## API

| Endpoint | Role |
|---|---|
| `POST /auth/signup` · `POST /auth/login` | public |
| `GET /routes` · `/routes/{id}/trips` · `/trips/{id}/upcoming-stops` | any authenticated |
| `GET /stops/{id}/dhabas` · `/dhabas/{id}/menu` | any authenticated |
| `POST /orders` · `PATCH /orders/{id}/cancel` | passenger (own) |
| `GET /dhabas/{id}/incoming-orders` · `PATCH /orders/{id}/status` | dhaba (own) |
| `PATCH /trips/{id}/delay` · `/last-passed-stop` | admin |
| `POST/PATCH/DELETE /admin/{routes,stops,dhabas,trips,menu-items}` | admin |

Full interactive documentation at `/docs`.

---

## Project structure

```
app/
  main.py  config.py  database.py
  models/      Route Stop Trip Dhaba MenuItem ReviewCache User Order OrderItem
  schemas/     Pydantic request and response models
  routers/     auth  passengers  dhabas  trips  admin
  services/    eta_service  order_service  places_service  gemini_service
  utils/       auth  security  errors
alembic/       migrations
scripts/       seed.py  fetch_place_ids.py
static/        index.html — the whole frontend
tests/
```

---

## What is not built

- **No payment gateway.** Orders are placed, not paid for.
- **Bus position is operator-reported**, not GPS. ETAs come from a timetable plus a reported delay rather than live location.
- **Prep times are static** per dhaba, not learned from order history.

All three are deliberate scope cuts, and each is the obvious next piece of work.

---

Built by [Ishan Singh](https://github.com/thakurishan9990-jpg) — BCA (AI & Data Science), Graphic Era Deemed to be University, Dehradun.
