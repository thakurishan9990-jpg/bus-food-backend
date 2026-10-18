"""Re-export of the FastAPI app for tooling that expects api/index.py.

Vercel does not route through this file: with the FastAPI framework preset it
auto-detects app/main.py (checked before api/index.py) and serves app.main:app
directly with the original request path. All app setup lives in app.main.
"""

from app.main import app  # noqa: F401
