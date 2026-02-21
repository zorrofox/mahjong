"""
main.py - FastAPI application entry point for the Mahjong game.

Run with:
  cd backend
  uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

import sys
import os

# Ensure the backend directory is on the Python path so that
# `from game.xxx import ...` and `from api.xxx import ...` work correctly.
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router as rest_router
from api.websocket import router as ws_router

app = FastAPI(title="Mahjong Game")

# ---------------------------------------------------------------------------
# CORS – allow all origins during development
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# REST API routes  →  /api/...
# ---------------------------------------------------------------------------
app.include_router(rest_router, prefix="/api")

# ---------------------------------------------------------------------------
# WebSocket routes  →  /ws/...
# ---------------------------------------------------------------------------
app.include_router(ws_router)

# ---------------------------------------------------------------------------
# Serve frontend static files  →  /
# ---------------------------------------------------------------------------
_frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(_frontend_dir):
    app.mount(
        "/",
        StaticFiles(directory=_frontend_dir, html=True),
        name="frontend",
    )
