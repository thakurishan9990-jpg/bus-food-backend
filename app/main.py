import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import admin, ads, auth, buses, dhabas, kitchen, passengers, search, trips

logger = logging.getLogger(__name__)

# Resolved from this file rather than the CWD so the mount works the same under
# `uvicorn app.main:app` and the Vercel serverless function.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(
    title="DhabaGo API",
    description=(
        "Pre-order food from dhabas at upcoming bus stops.\n\n"
        "**Passenger** browsing endpoints are public; placing an order needs a passenger login. "
        "**Kitchen** endpoints need a dhaba login, **admin** endpoints an admin login. "
        "Use *Authorize* with the phone number as the username."
    ),
    version="0.2.0",
    openapi_tags=[
        {"name": "passenger", "description": "Routes, buses, stops, dhabas, menus, search, ads, and ordering."},
        {"name": "kitchen", "description": "Dhaba staff: their own orders and menu."},
        {"name": "admin", "description": "Operations and Business dashboards, delays, and catalogue CRUD."},
        {"name": "auth", "description": "Sign up and log in."},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(passengers.router)
app.include_router(buses.router)
app.include_router(search.router)
app.include_router(ads.router)
app.include_router(kitchen.router)
app.include_router(dhabas.router)
app.include_router(trips.router)
app.include_router(admin.router)


@app.get("/health", tags=["health"])
def health_check() -> dict:
    """Basic liveness check."""
    return {"status": "ok"}


# Printed rather than logged at INFO so it always shows up in the Vercel function
# logs and the uvicorn console, making it obvious whether static/ shipped.
print(
    f"[startup] static dir: {STATIC_DIR} "
    f"(exists={STATIC_DIR.is_dir()}, index.html found={(STATIC_DIR / 'index.html').is_file()})",
    flush=True,
)

# Mounted last: Starlette matches routes in registration order, so every API
# route above is still checked first. "/static" serves assets such as
# /static/dishes/<dish_id>.jpg; "/" serves static/index.html for "/" and other
# unmatched paths once nothing above has claimed them.
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
else:
    logger.warning(
        "Static directory %s not found; the frontend will not be served at '/'. "
        "Check that static/** is bundled with the deployment.",
        STATIC_DIR,
    )
