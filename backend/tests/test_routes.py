"""Tests for api/routes.py — REST API endpoints using FastAPI TestClient."""

import pytest
from fastapi.testclient import TestClient
from api.routes import router, room_manager
from fastapi import FastAPI


@pytest.fixture(autouse=True)
def clean_rooms():
    """Clear rooms before each test."""
    room_manager._rooms.clear()
    yield
    room_manager._rooms.clear()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


class TestListRooms:
    def test_empty_rooms(self, client):
        resp = client.get("/api/rooms")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_rooms_after_creation(self, client):
        client.post("/api/rooms")
        resp = client.get("/api/rooms")
        assert resp.status_code == 200
        rooms = resp.json()
        assert len(rooms) == 1
        assert "id" in rooms[0]
        assert "name" in rooms[0]


class TestCreateRoom:
    def test_create_room_success(self, client):
        resp = client.post("/api/rooms")
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["status"] == "waiting"

    def test_create_room_with_name(self, client):
        resp = client.post("/api/rooms", json={"name": "My Room"})
        assert resp.status_code == 201
        assert resp.json()["name"] == "My Room"

    def test_create_room_default_name(self, client):
        resp = client.post("/api/rooms")
        assert resp.status_code == 201
        assert resp.json()["name"].startswith("Room ")


class TestJoinRoom:
    def test_join_room_success(self, client):
        create_resp = client.post("/api/rooms")
        room_id = create_resp.json()["id"]
        resp = client.post(f"/api/rooms/{room_id}/join", json={"player_id": "p1"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["room_id"] == room_id
        assert data["was_redirected"] is False
        assert data["player_idx"] == 0

    def test_join_nonexistent_room_404(self, client):
        resp = client.post("/api/rooms/nonexistent/join", json={"player_id": "p1"})
        assert resp.status_code == 404

    def test_join_full_room_redirect(self, client):
        create_resp = client.post("/api/rooms")
        room_id = create_resp.json()["id"]
        for i in range(4):
            client.post(f"/api/rooms/{room_id}/join", json={"player_id": f"p{i}"})
        # 5th player should be redirected
        resp = client.post(f"/api/rooms/{room_id}/join", json={"player_id": "p_extra"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["was_redirected"] is True
        assert data["room_id"] != room_id

    def test_join_room_second_player(self, client):
        create_resp = client.post("/api/rooms")
        room_id = create_resp.json()["id"]
        client.post(f"/api/rooms/{room_id}/join", json={"player_id": "p1"})
        resp = client.post(f"/api/rooms/{room_id}/join", json={"player_id": "p2"})
        assert resp.status_code == 200
        assert resp.json()["player_idx"] == 1


class TestStartGame:
    def test_start_game_success(self, client):
        create_resp = client.post("/api/rooms")
        room_id = create_resp.json()["id"]
        client.post(f"/api/rooms/{room_id}/join", json={"player_id": "p1"})
        resp = client.post(f"/api/rooms/{room_id}/start")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "playing"
        assert len(data["players"]) == 4

    def test_start_nonexistent_room_404(self, client):
        resp = client.post("/api/rooms/nonexistent/start")
        assert resp.status_code == 404

    def test_start_already_started_400(self, client):
        create_resp = client.post("/api/rooms")
        room_id = create_resp.json()["id"]
        client.post(f"/api/rooms/{room_id}/join", json={"player_id": "p1"})
        client.post(f"/api/rooms/{room_id}/start")
        resp = client.post(f"/api/rooms/{room_id}/start")
        assert resp.status_code == 400

    def test_start_game_has_ai_players(self, client):
        create_resp = client.post("/api/rooms")
        room_id = create_resp.json()["id"]
        client.post(f"/api/rooms/{room_id}/join", json={"player_id": "p1"})
        resp = client.post(f"/api/rooms/{room_id}/start")
        data = resp.json()
        ai_players = [p for p in data["players"] if p["is_ai"]]
        assert len(ai_players) == 3
