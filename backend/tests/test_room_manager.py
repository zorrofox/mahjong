"""Tests for game/room_manager.py — room lifecycle and player management."""

import pytest
from game.room_manager import RoomManager, Room, MAX_PLAYERS


@pytest.fixture
def rm():
    return RoomManager()


class TestCreateRoom:
    def test_create_room_returns_room(self, rm):
        room = rm.create_room()
        assert isinstance(room, Room)

    def test_create_room_unique_ids(self, rm):
        r1 = rm.create_room()
        r2 = rm.create_room()
        assert r1.id != r2.id

    def test_create_room_custom_name(self, rm):
        room = rm.create_room(name="Test Room")
        assert room.name == "Test Room"

    def test_create_room_default_name(self, rm):
        room = rm.create_room()
        assert room.name.startswith("Room ")

    def test_create_room_status_waiting(self, rm):
        room = rm.create_room()
        assert room.status == "waiting"


class TestGetRoom:
    def test_get_existing_room(self, rm):
        room = rm.create_room()
        found = rm.get_room(room.id)
        assert found is room

    def test_get_nonexistent_room(self, rm):
        assert rm.get_room("nonexistent") is None


class TestGetRooms:
    def test_get_rooms_empty(self, rm):
        assert rm.get_rooms() == []

    def test_get_rooms_returns_all(self, rm):
        rm.create_room()
        rm.create_room()
        assert len(rm.get_rooms()) == 2


class TestJoinRoom:
    def test_join_room_normal(self, rm):
        room = rm.create_room()
        result_room, was_redirected = rm.join_room(room.id, "player1")
        assert result_room.id == room.id
        assert was_redirected is False
        assert "player1" in result_room.human_players

    def test_join_room_already_in_room(self, rm):
        room = rm.create_room()
        rm.join_room(room.id, "player1")
        result_room, was_redirected = rm.join_room(room.id, "player1")
        assert was_redirected is False
        assert result_room.human_players.count("player1") == 1

    def test_join_room_full_redirects(self, rm):
        room = rm.create_room()
        for i in range(MAX_PLAYERS):
            rm.join_room(room.id, f"player{i}")
        # Room is now full; next player should be redirected
        result_room, was_redirected = rm.join_room(room.id, "player_extra")
        assert was_redirected is True
        assert result_room.id != room.id
        assert "player_extra" in result_room.human_players

    def test_join_nonexistent_room_raises(self, rm):
        with pytest.raises(KeyError, match="does not exist"):
            rm.join_room("nonexistent", "player1")

    def test_join_room_multiple_players(self, rm):
        room = rm.create_room()
        rm.join_room(room.id, "p1")
        rm.join_room(room.id, "p2")
        rm.join_room(room.id, "p3")
        assert room.player_count == 3


class TestRemovePlayer:
    def test_remove_in_waiting_phase(self, rm):
        room = rm.create_room()
        rm.join_room(room.id, "player1")
        rm.remove_player(room.id, "player1")
        assert "player1" not in room.human_players

    def test_remove_in_playing_phase_keeps_slot(self, rm):
        room = rm.create_room()
        rm.join_room(room.id, "player1")
        room.status = "playing"
        rm.remove_player(room.id, "player1")
        # Slot is kept during active game
        assert "player1" in room.human_players

    def test_remove_from_nonexistent_room(self, rm):
        # Should not raise
        rm.remove_player("nonexistent", "player1")

    def test_remove_nonexistent_player(self, rm):
        room = rm.create_room()
        # Should not raise
        rm.remove_player(room.id, "nonexistent_player")


class TestRoomProperties:
    def test_player_count(self, rm):
        room = rm.create_room()
        assert room.player_count == 0
        rm.join_room(room.id, "p1")
        assert room.player_count == 1

    def test_is_full(self, rm):
        room = rm.create_room()
        assert room.is_full is False
        for i in range(MAX_PLAYERS):
            rm.join_room(room.id, f"p{i}")
        assert room.is_full is True

    def test_to_dict(self, rm):
        room = rm.create_room(name="Test")
        d = room.to_dict()
        assert d["id"] == room.id
        assert d["name"] == "Test"
        assert d["player_count"] == 0
        assert d["status"] == "waiting"
        assert d["max_players"] == MAX_PLAYERS
        assert "created_at" in d


class TestStartGame:
    def test_start_game_fills_ai(self, rm):
        room = rm.create_room()
        rm.join_room(room.id, "human1")
        gs = rm.start_game(room.id)
        assert len(gs.players) == 4
        # 1 human + 3 AI
        ai_count = sum(1 for p in gs.players if p.is_ai)
        assert ai_count == 3

    def test_start_game_status_playing(self, rm):
        room = rm.create_room()
        rm.join_room(room.id, "human1")
        rm.start_game(room.id)
        assert room.status == "playing"

    def test_start_game_deals_tiles(self, rm):
        room = rm.create_room()
        rm.join_room(room.id, "human1")
        gs = rm.start_game(room.id)
        # All players should have tiles
        for p in gs.players:
            assert len(p.hand) > 0

    def test_start_game_already_started_raises(self, rm):
        room = rm.create_room()
        rm.join_room(room.id, "human1")
        rm.start_game(room.id)
        with pytest.raises(ValueError, match="not in waiting"):
            rm.start_game(room.id)

    def test_start_game_nonexistent_room_raises(self, rm):
        with pytest.raises(KeyError, match="does not exist"):
            rm.start_game("nonexistent")

    def test_start_game_full_room_no_ai(self, rm):
        room = rm.create_room()
        for i in range(MAX_PLAYERS):
            rm.join_room(room.id, f"human{i}")
        gs = rm.start_game(room.id)
        ai_count = sum(1 for p in gs.players if p.is_ai)
        assert ai_count == 0

    def test_start_game_assigns_game_state(self, rm):
        room = rm.create_room()
        rm.join_room(room.id, "human1")
        gs = rm.start_game(room.id)
        assert room.game_state is gs
