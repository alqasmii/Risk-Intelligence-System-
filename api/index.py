"""
Vercel Serverless Entry Point
==============================
Exposes the FastAPI ASGI app to Vercel's Python runtime.
All requests to /api/* are routed here via vercel.json rewrites.

Environment variables required on Vercel:
  DATABASE_URL   — PostgreSQL connection string (Neon, Supabase, Railway)
  FRONTEND_URL   — Your Vercel deployment URL
  DEBUG          — false in production
"""
import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_startup_error: str | None = None

try:
    from app.main import app  # noqa: F401
except Exception:
    _startup_error = traceback.format_exc()
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI(title="Risk Intelligence System — Startup Error")

    @app.api_route("/{path:path}", methods=["GET", "POST", "PATCH", "DELETE", "PUT", "OPTIONS"])
    async def _startup_error_handler(path: str = ""):
        return JSONResponse(
            status_code=503,
            content={
                "error": "Application failed to start",
                "traceback": _startup_error,
                "hint": "Check DATABASE_URL and other env vars in Vercel settings.",
            },
        )
