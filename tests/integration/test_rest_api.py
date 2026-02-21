"""Integration tests for the REST API endpoints."""

import pytest


class TestListRooms:
    def test_empty_initially(self, client):
        resp = client.get("/api/rooms")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_shows_created_room(self, client):
        client.post("/api/rooms")
        resp = client.get("/api/rooms")
        assert resp.status_code == 200
        rooms = resp.json()
        assert len(rooms) == 1


class TestCreateRoom:
    def test_creates_room_default_name(self, client):
        resp = client.post("/api/rooms")
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert "name" in data
        assert data["status"] == "waiting"
        assert data["player_count"] == 0
        assert data["max_players"] == 4

    def test_creates_room_custom_name(self, client):
        resp = client.post("/api/rooms", json={"name": "My Room"})
        assert resp.status_code == 201
        assert resp.json()["name"] == "My Room"

    def test_creates_multiple_rooms(self, client):
        r1 = client.post("/api/rooms").json()
        r2 = client.post("/api/rooms").json()
        assert r1["id"] != r2["id"]
        rooms = client.get("/api/rooms").json()
        assert len(rooms) == 2


class TestJoinRoom:
    def test_join_room(self, client):
        room_id = client.post("/api/rooms").json()["id"]
        resp = client.post(f"/api/rooms/{room_id}/join", json={"player_id": "p1"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["room_id"] == room_id
        assert data["player_idx"] == 0
        assert data["was_redirected"] is False

    def test_join_room_multiple_players(self, client):
        room_id = client.post("/api/rooms").json()["id"]
        for i in range(4):
            resp = client.post(f"/api/rooms/{room_id}/join", json={"player_id": f"p{i}"})
            assert resp.status_code == 200
            assert resp.json()["player_idx"] == i

    def test_join_room_idempotent(self, client):
        room_id = client.post("/api/rooms").json()["id"]
        client.post(f"/api/rooms/{room_id}/join", json={"player_id": "p1"})
        resp = client.post(f"/api/rooms/{room_id}/join", json={"player_id": "p1"})
        assert resp.status_code == 200
        assert resp.json()["player_idx"] == 0

    def test_join_full_room_redirects(self, client):
        room_id = client.post("/api/rooms").json()["id"]
        for i in range(4):
            client.post(f"/api/rooms/{room_id}/join", json={"player_id": f"p{i}"})
        # 5th player triggers redirect
        resp = client.post(f"/api/rooms/{room_id}/join", json={"player_id": "p_extra"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["was_redirected"] is True
        assert data["room_id"] != room_id

    def test_join_nonexistent_room(self, client):
        resp = client.post("/api/rooms/fake-id/join", json={"player_id": "p1"})
        assert resp.status_code == 404


class TestStartGame:
    def test_start_game(self, client):
        room_id = client.post("/api/rooms").json()["id"]
        client.post(f"/api/rooms/{room_id}/join", json={"player_id": "p1"})
        resp = client.post(f"/api/rooms/{room_id}/start")
        assert resp.status_code == 200
        data = resp.json()
        assert data["room_id"] == room_id
        assert data["status"] == "playing"
        players = data["players"]
        assert len(players) == 4
        # First player is human
        assert players[0]["id"] == "p1"
        assert players[0]["is_ai"] is False
        # Remaining are AI
        for p in players[1:]:
            assert p["is_ai"] is True

    def test_start_game_already_started(self, client):
        room_id = client.post("/api/rooms").json()["id"]
        client.post(f"/api/rooms/{room_id}/join", json={"player_id": "p1"})
        client.post(f"/api/rooms/{room_id}/start")
        resp = client.post(f"/api/rooms/{room_id}/start")
        assert resp.status_code == 400

    def test_start_nonexistent_room(self, client):
        resp = client.post("/api/rooms/fake-id/start")
        assert resp.status_code == 404

    def test_room_status_updates_after_start(self, client):
        room_id = client.post("/api/rooms").json()["id"]
        client.post(f"/api/rooms/{room_id}/join", json={"player_id": "p1"})
        # Before start
        rooms = client.get("/api/rooms").json()
        assert rooms[0]["status"] == "waiting"
        # After start
        client.post(f"/api/rooms/{room_id}/start")
        rooms = client.get("/api/rooms").json()
        assert rooms[0]["status"] == "playing"
