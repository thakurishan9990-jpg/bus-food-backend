import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routers import admin, auth, dhabas, passengers, trips

logger = logging.getLogger(__name__)

# Resolved from this file rather than the CWD so the mount works the same under
# `uvicorn app.main:app` and the Vercel serverless handler (api/index.py).
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(
    title="Bus Food Pre-Ordering API",
    description="Pre-order food from dhabas at upcoming bus stops.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(passengers.router)
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
# route above is still checked first. This only serves static/index.html for
# "/" and other unmatched paths once nothing above has claimed them.
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
else:
    logger.warning(
        "Static directory %s not found; the frontend will not be served at '/'. "
        "Check that static/** is bundled with the deployment.",
        STATIC_DIR,
    )
