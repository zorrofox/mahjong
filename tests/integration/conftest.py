"""Shared fixtures for integration tests."""

import sys
import os

# Ensure backend modules are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../backend'))

import pytest
from fastapi.testclient import TestClient
from main import app
from api.routes import room_manager
from api.websocket import _connections


@pytest.fixture(autouse=True)
def _clear_state():
    """Clear all rooms and WS connections before each test."""
    room_manager._rooms.clear()
    _connections.clear()
    yield
    room_manager._rooms.clear()
    _connections.clear()


@pytest.fixture
def client():
    """Provide a TestClient for the FastAPI app."""
    with TestClient(app) as c:
        yield c
