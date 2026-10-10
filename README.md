# Bus Food Pre-Ordering — Backend

Pre-order food from real highway dhabas at upcoming bus stops, for intercity buses in India.
No frontend yet — **FastAPI's `/docs` (Swagger UI) is the demo.**

## Stack

Python 3.11+, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, PostgreSQL, JWT auth
(python-jose + passlib), Google Places API, Gemini API, pytest.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Fill in GOOGLE_PLACES_API_KEY and GEMINI_API_KEY if you want live reviews.
# Without them, dhaba listings still work — ai_summary/rating just come back null/fallback.

docker-compose up -d db
alembic upgrade head

python -m scripts.seed
# Optional, needs GOOGLE_PLACES_API_KEY: python -m scripts.fetch_place_ids

uvicorn app.main:app --reload
```

Open **http://localhost:8000/docs**.

Run tests any time with:
```bash
pytest
```

## Seeded demo data

Route: Delhi ISBT Kashmere Gate → Dehradun ISBT (NH-334), with 5 stops (Meerut, Khatauli,
Muzaffarnagar, Roorkee, Chhutmalpur), 2-3 dhabas per stop, 3-5 menu items each, and one
active trip (`UP15-AB-1234`) departing "now" at seed time.

Three demo accounts (all share the password from `SEED_USER_PASSWORD` in `.env`, default `password123`):

| Role | Phone | Name |
|---|---|---|
| passenger | 9876543210 | Amit |
| dhaba | 9876543211 | Rajesh (staff at Sharma Dhaba, Meerut) |
| admin | 9876543212 | Admin |

## `/docs` walkthrough

Swagger's lock-icon **Authorize** button accepts a phone number as "username" — this lets
you log in as all three roles side by side without leaving the page.

1. **Authorize as passenger** — `Authorize` → username `9876543210`, password `password123`.
   (Or try `POST /auth/signup` with a new phone number instead — it also returns a token.)
2. `GET /routes` — note the route id.
3. `GET /routes/{route_id}/trips` — note the trip id (`UP15-AB-1234`).
4. `GET /trips/{trip_id}/upcoming-stops` — see ETAs for every stop ahead of the bus.
5. `GET /stops/{stop_id}/dhabas` — dhabas at a stop, with rating + AI summary (or fallback
   text if API keys aren't set).
6. `GET /dhabas/{dhaba_id}/menu` — note a `menu_item_id`.
7. `POST /orders` — place an order with `trip_id`, `stop_id`, `dhaba_id`, and
   `items: [{menu_item_id, quantity}]`. If the bus is too close to that stop relative to the
   dhaba's prep time, this returns `409` with a message like
   *"Too late to order, bus arrives in 8 min but prep needs 20 min"*.
8. `GET /passengers/{passenger_id}/orders` — see your order (use your own user id — a
   passenger can't view anyone else's).
9. `PATCH /orders/{order_id}/cancel` — works while `placed`/`accepted`, 409s after.

10. **Re-authorize as dhaba staff** — username `9876543211`, password `password123`.
11. `GET /dhabas/{dhaba_id}/incoming-orders` — orders for Rajesh's own dhaba only
    (another dhaba's id returns 403).
12. `PATCH /orders/{order_id}/status` — advance one step at a time:
    `placed → accepted → preparing → ready → picked_up`. Skipping a step returns 400.

13. **Re-authorize as admin** — username `9876543212`, password `password123`.
14. `PATCH /trips/{trip_id}/delay` with `{"current_delay_minutes": 20}` — every active
    order's `expected_arrival_time` shifts accordingly (check step 8's endpoint again).
15. `PATCH /trips/{trip_id}/last-passed-stop`, and the `/admin/*` CRUD endpoints for
    routes/stops/dhabas/menu-items.

## Design notes

- **Passenger = User.** There's no separate `Passenger` table — a passenger is just a
  `User` with `role=passenger`. `Order.passenger_id` points at `users.id`.
- **Price snapshotting.** `OrderItem.unit_price` is copied from `MenuItem.price` at order
  time, so a later menu price change never rewrites history.
- **Review cache.** Served if `fetched_at` is <24h old; otherwise refreshed via Google
  Places → Gemini → upserted. Any API failure falls back to the existing cache row, or a
  static message if there's never been one — this path never hard-errors.
- **Trip/stop management is admin-only.** The RBAC spec defines passenger/dhaba/admin —
  there's no separate "operator" role, so `PATCH /trips/{id}/delay` and
  `PATCH /trips/{id}/last-passed-stop` require `role=admin`.
