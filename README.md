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

**When ordering closes at a stop**

```
order_cutoff = min over the stop's live dhabas of (ETA − prep time − 10 minute buffer)
```

The slowest kitchen at a stop sets its cut-off, so a stop closes for ordering all at once. For bus `UK07 PA 1187` (departs 08:00, running 15 min late) Meerut is 159 minutes out: it arrives at 10:54, and with an 18-minute kitchen there ordering closes at 10:26. An order after the cut-off is refused by the API with `409` and a readable reason. The cut-off is enforced server-side, not hidden in the interface.

**Delay propagation.** Buses do not run to the minute. When an operator reports a delay, `PATCH /trips/{id}/delay` recalculates `expected_arrival_time` on every open order for that trip, so each kitchen's deadline moves and stops that had closed for ordering reopen. One request, every affected passenger and kitchen updated.

**AI review summaries.** A passenger has about ninety seconds to choose a dhaba and will not read 287 Google reviews. Dhaba listings pull rating and review text from the Google Places API, condense them to one line with Gemini, and cache the result for 24 hours. The ordering path never blocks on a third-party API, and a failed call falls back to the last good summary.

---

## Three roles, three dashboards

| Role | Sees |
|---|---|
| **Passenger** | Trip (route, bus number, stops with cut-offs), Dhabas, Menu, Checkout, Order tracker, Search, Alerts, Profile, and a Veg / Non-veg switch |
| **Dhaba manager** | Kitchen: their own dhaba's open orders, soonest bus first, moved along placed → accepted → preparing → ready → picked up |
| **Admin** | Operations (live trips, open orders, kitchens that can't keep up) and Business (income by stream) |

Passengers can browse without signing in; placing an order needs a passenger account. The role inside the JWT decides which tabs show, and the API returns `403` regardless — tested both ways.

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
ADMIN_PASSWORD='choose-one' python -m scripts.seed

uvicorn app.main:app --reload
```

Open http://localhost:8000 for the app, `/docs` for the API (use **Authorize** with a phone number as the username).

### Seeding

`python -m scripts.seed` loads `data/dhabago_seed.json` (pass `--file` for another export): 8 routes, 32 buses, 39 stops, 284 dhabas, 2,245 menu items, ad campaigns and the demo users, and prints the counts. All names, ratings, prices and reviews in it are invented demo data.

It is safe to re-run: rows are matched by natural key (route code, bus number, dhaba slug, …) and updated, never duplicated. A re-run does not undo what has happened in the app since — dhaba status, item availability, reported delays and ad stats are only set when a row is first created. Each run also creates today's trip for every bus, carrying the bus's delay.

Against production, run the same two commands with `DATABASE_URL` pointing at the hosted database: `alembic upgrade head`, then the seed.

### Demo logins

| Role | Phone | Password |
|---|---|---|
| Passenger | `9876543210` | `password123` |
| Dhaba (Punjabi Rasoi, Meerut) | `9876500001` | `dhaba123` |
| Admin | `9000000001` (`ADMIN_PHONE`) | the `ADMIN_PASSWORD` you seeded with |

The admin isn't in the seed file at all, and an admin entry in another seed file is ignored. If `ADMIN_PASSWORD` is unset, the seed generates one, prints it once, and keeps it on later runs.

Times are real: stops close for ordering at their cut-off, so in the evening most of the day's buses are past ordering. Pick a bus that departs later, or check the cut-off tags on the Trip screen.

### Dish images

Each menu item shows `/static/dishes/<dish_id>.jpg`, served from `static/dishes/`. The current files are drawn illustrations (320×320). To use real photos, replace the files in `static/dishes/` keeping **the same file names** (e.g. `butter-chicken.jpg`); square JPEGs around 320×320 work best. No database change or re-seed is needed. A missing or broken image shows a neutral placeholder.

---

## Tests

```bash
pytest
```

149 tests covering the seed (counts, idempotency, passwords), bus lookup, arrival and cut-off maths, the Veg / Non-veg rules, order pricing and validation, the status machine, role guards, ads, and the dashboards. SQLite in-memory: the seed file is loaded once per run and each test gets its own copy. `respx` for the external APIs.

---

## API

| Endpoint | Role |
|---|---|
| `POST /auth/signup` · `POST /auth/login` | public |
| `GET /routes` · `/routes/{code}/buses` · `/buses/{bus_number}` · `/buses/{bus_number}/stops` | public (passenger) |
| `GET /stops/{id}/dhabas` · `/dhabas/{slug}/menu` · `/search` · `/ads` · `/config` | public (passenger) |
| `POST /ads/{id}/view` · `POST /ads/{id}/tap` | public (passenger) |
| `POST /orders` · `PATCH /orders/{id}/cancel` | passenger (own) |
| `GET /kitchen/orders` · `PATCH /kitchen/orders/{id}` | dhaba (own) |
| `GET /admin/operations` · `GET /admin/business` | admin |
| `PATCH /trips/{id}/delay` · `/last-passed-stop` · CRUD under `/admin/…` | admin |

Passenger requests take `?diet=all|veg|nonveg`. Money is whole rupees; a ₹7 convenience fee (`CONVENIENCE_FEE_INR`) is added to every order and a 12% commission (`DEFAULT_COMMISSION_PCT`, per dhaba) is taken on the food. Full interactive documentation at `/docs`, grouped by passenger, kitchen and admin.

---

## Project structure

```
app/
  main.py  config.py  database.py
  models/      Route Stop Bus Trip Dhaba MenuItem AdCampaign ReviewCache User Order OrderItem
  schemas/     Pydantic request and response models
  routers/     auth  passengers  buses  search  ads  kitchen  dhabas  trips  admin
  services/    bus  catalog  listing  order  dashboard  eta  places  gemini
  utils/       auth  security  errors
alembic/       migrations
scripts/       seed.py  fetch_place_ids.py
static/        index.html — the whole frontend · dishes/ — one image per dish
data/          dhabago_seed.json — the demo data the seed loads
tests/
```

---

## What is not built

- **No payment gateway.** Orders are placed, not paid for.
- **Bus position is operator-reported**, not GPS. ETAs come from a timetable plus a reported delay rather than live location.
- **Prep times are static** per dhaba, not learned from order history.
- **Reviews are not saved.** The rating dialog is there, but nothing stores what passengers write.
- **Ad spend has no daily ledger.** "Ad revenue today" is campaign spend over a 7-day window, divided by 7.

These are deliberate scope cuts, and each is the obvious next piece of work.

---

Built by [Ishan Singh](https://github.com/thakurishan9990-jpg) — BCA (AI & Data Science), Graphic Era Deemed to be University, Dehradun.
