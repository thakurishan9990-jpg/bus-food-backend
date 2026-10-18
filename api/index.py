"""Vercel serverless entrypoint.

Vercel's Python runtime looks for an ASGI app named `app` in this module.
All app setup lives in app.main; this file only re-exports it.
"""

from app.main import app  # noqa: F401
