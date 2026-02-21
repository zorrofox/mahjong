"""Integration tests for the WebSocket claim window (pung, chow, kong, skip, win).

Strategy
--------
After starting a game via REST, we directly manipulate ``room.game_state`` to
put it into a controlled claiming state with known hands.  This avoids relying
on the non-deterministic AI turn loop.

On WS connect during claiming phase, the server synchronously sends:
  1. game_state
  2. claim_window   (iff player_idx in _pending_claims)
  3. room_update    (broadcast)

The test then sends a claim action and verifies the subsequent game_state.

Note: ``asyncio.create_task`` callbacks (AI turns) do NOT execute in
Starlette's synchronous TestClient.
"""

import pytest
from api.routes import room_manager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_and_start(client, player_id="claim_player"):
    """Create a room, join as player_id, start via REST; return room_id."""
    room_id = client.post("/api/rooms").json()["id"]
    client.post(f"/api/rooms/{room_id}/join", json={"player_id": player_id})
    client.post(f"/api/rooms/{room_id}/start")
    return room_id


def _setup_claiming(room_id, player_hand, discard_tile, discarder_idx=1):
    """
    Directly put the game into claiming phase with a controlled hand for
    player 0 (the human).

    All non-discarder, non-player-0 seats (AI players) are pre-added to
    _skipped_claims, so that player 0's response alone closes the window.
    """
    room = room_manager.get_room(room_id)
    gs = room.game_state
    gs.players[0].hand = list(player_hand)
    gs.discards[discarder_idx].append(discard_tile)
    gs.last_discard = discard_tile
    gs.last_discard_player = discarder_idx
    gs.current_turn = discarder_idx
    gs.phase = "claiming"
    gs._pending_claims = {i for i in range(4) if i != discarder_idx}
    # Pre-skip every seat except the human (0) and the discarder
    gs._skipped_claims = {i for i in range(4) if i not in (0, discarder_idx)}
    gs._best_claim = None


def _drain_until(ws, target_type, max_msgs=8):
    """
    Read WebSocket messages until one whose ``type`` equals *target_type* is
    found, then return it.  Raises AssertionError if not found within
    *max_msgs* messages.
    """
    received = []
    for _ in range(max_msgs):
        try:
            msg = ws.receive_json()
            received.append(msg)
            if msg.get("type") == target_type:
                return msg
        except Exception:
            break
    types = [m.get("type") for m in received]
    raise AssertionError(
        f"Expected message type '{target_type}' not found in "
        f"{len(received)} messages.  Got: {types}"
    )


# ---------------------------------------------------------------------------
# Pung
# ---------------------------------------------------------------------------


class TestClaimPung:
    def test_pung_offered_in_claim_window(self, client):
        """claim_window includes 'pung' when player holds two matching tiles."""
        pid = "pung_offer"
        room_id = _create_and_start(client, pid)
        _setup_claiming(
            room_id,
            ["BAMBOO_1", "BAMBOO_1", "CIRCLES_3", "CIRCLES_4"],
            discard_tile="BAMBOO_1",
            discarder_idx=1,
        )

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            cw = _drain_until(ws, "claim_window")

        assert cw["tile"] == "BAMBOO_1"
        assert "pung" in cw["actions"]
        assert "skip" in cw["actions"]

    def test_pung_forms_meld_and_enters_discard(self, client):
        """Successful pung: meld appears, phase becomes discarding."""
        pid = "pung_claim"
        room_id = _create_and_start(client, pid)
        _setup_claiming(
            room_id,
            ["BAMBOO_1", "BAMBOO_1", "CIRCLES_3", "CIRCLES_4"],
            discard_tile="BAMBOO_1",
            discarder_idx=1,
        )

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "claim_window")

            ws.send_json({"type": "pung"})
            state_msg = _drain_until(ws, "game_state")

        state = state_msg["state"]
        assert state["phase"] == "discarding"
        assert state["current_turn"] == 0
        my_melds = state["players"][0]["melds"]
        assert len(my_melds) == 1
        assert sorted(my_melds[0]) == ["BAMBOO_1", "BAMBOO_1", "BAMBOO_1"]

    def test_pung_removes_tiles_from_hand(self, client):
        """After pung the two paired tiles leave the hand."""
        pid = "pung_hand"
        room_id = _create_and_start(client, pid)
        _setup_claiming(
            room_id,
            ["BAMBOO_1", "BAMBOO_1", "CIRCLES_2"],
            discard_tile="BAMBOO_1",
            discarder_idx=1,
        )

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "claim_window")
            ws.send_json({"type": "pung"})
            state_msg = _drain_until(ws, "game_state")

        hand = state_msg["state"]["players"][0]["hand"]
        assert hand["hidden"] is False
        # Both BAMBOO_1 tiles moved to meld; none remain in hand
        assert "BAMBOO_1" not in hand["tiles"]
        # Unrelated tile is still there
        assert "CIRCLES_2" in hand["tiles"]


# ---------------------------------------------------------------------------
# Chow
# ---------------------------------------------------------------------------


class TestClaimChow:
    def test_chow_offered_from_left_player(self, client):
        """claim_window includes 'chow' when discarder is to player 0's left."""
        pid = "chow_offer"
        room_id = _create_and_start(client, pid)
        # Chow requires last_discard_player == (0 - 1) % 4 == 3
        _setup_claiming(
            room_id,
            ["BAMBOO_3", "BAMBOO_4", "CIRCLES_1"],
            discard_tile="BAMBOO_5",
            discarder_idx=3,
        )

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            cw = _drain_until(ws, "claim_window")

        assert cw["tile"] == "BAMBOO_5"
        assert "chow" in cw["actions"]

    def test_chow_not_offered_from_non_left_player(self, client):
        """'chow' is absent when the discarder is not to player 0's immediate left."""
        pid = "chow_wrong"
        room_id = _create_and_start(client, pid)
        # Discarder=1: (0-1)%4 == 3 ≠ 1 → chow not available
        _setup_claiming(
            room_id,
            ["BAMBOO_3", "BAMBOO_4", "CIRCLES_1"],
            discard_tile="BAMBOO_5",
            discarder_idx=1,
        )

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            cw = _drain_until(ws, "claim_window")

        assert "chow" not in cw["actions"]

    def test_chow_forms_meld_and_enters_discard(self, client):
        """Successful chow: sequence meld formed, phase becomes discarding."""
        pid = "chow_claim"
        room_id = _create_and_start(client, pid)
        _setup_claiming(
            room_id,
            ["BAMBOO_3", "BAMBOO_4", "CIRCLES_1"],
            discard_tile="BAMBOO_5",
            discarder_idx=3,
        )

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "claim_window")

            ws.send_json({"type": "chow", "tiles": ["BAMBOO_3", "BAMBOO_4"]})
            state_msg = _drain_until(ws, "game_state")

        state = state_msg["state"]
        assert state["phase"] == "discarding"
        assert state["current_turn"] == 0
        my_melds = state["players"][0]["melds"]
        assert len(my_melds) == 1
        assert sorted(my_melds[0]) == ["BAMBOO_3", "BAMBOO_4", "BAMBOO_5"]

    def test_chow_removes_hand_tiles(self, client):
        """After chow, the two hand tiles used are gone from the hand."""
        pid = "chow_hand"
        room_id = _create_and_start(client, pid)
        _setup_claiming(
            room_id,
            ["BAMBOO_3", "BAMBOO_4", "CIRCLES_1"],
            discard_tile="BAMBOO_5",
            discarder_idx=3,
        )

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "claim_window")
            ws.send_json({"type": "chow", "tiles": ["BAMBOO_3", "BAMBOO_4"]})
            state_msg = _drain_until(ws, "game_state")

        hand_tiles = state_msg["state"]["players"][0]["hand"]["tiles"]
        assert "BAMBOO_3" not in hand_tiles
        assert "BAMBOO_4" not in hand_tiles
        # Unrelated tile stays
        assert "CIRCLES_1" in hand_tiles


# ---------------------------------------------------------------------------
# Kong (claimed)
# ---------------------------------------------------------------------------


class TestClaimKong:
    def test_kong_offered_when_holding_three(self, client):
        """claim_window includes 'kong' when player holds three matching tiles."""
        pid = "kong_offer"
        room_id = _create_and_start(client, pid)
        _setup_claiming(
            room_id,
            ["CIRCLES_5", "CIRCLES_5", "CIRCLES_5", "BAMBOO_2"],
            discard_tile="CIRCLES_5",
            discarder_idx=1,
        )

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            cw = _drain_until(ws, "claim_window")

        assert cw["tile"] == "CIRCLES_5"
        assert "kong" in cw["actions"]

    def test_kong_forms_quad_meld(self, client):
        """Claimed kong: four-tile meld appears and player enters discarding."""
        pid = "kong_claim"
        room_id = _create_and_start(client, pid)
        _setup_claiming(
            room_id,
            ["CIRCLES_5", "CIRCLES_5", "CIRCLES_5", "BAMBOO_2"],
            discard_tile="CIRCLES_5",
            discarder_idx=1,
        )

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "claim_window")

            # Claimed kong: no tile field → server uses last_discard
            ws.send_json({"type": "kong"})
            state_msg = _drain_until(ws, "game_state")

        state = state_msg["state"]
        assert state["phase"] == "discarding"
        assert state["current_turn"] == 0
        my_melds = state["players"][0]["melds"]
        assert len(my_melds) == 1
        assert sorted(my_melds[0]) == [
            "CIRCLES_5", "CIRCLES_5", "CIRCLES_5", "CIRCLES_5"
        ]

    def test_kong_player_draws_replacement_tile(self, client):
        """After a claimed kong the player receives a replacement tile."""
        pid = "kong_replacement"
        room_id = _create_and_start(client, pid)
        initial_hand = ["CIRCLES_5", "CIRCLES_5", "CIRCLES_5", "BAMBOO_2"]
        _setup_claiming(
            room_id, initial_hand, discard_tile="CIRCLES_5", discarder_idx=1
        )

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "claim_window")
            ws.send_json({"type": "kong"})
            state_msg = _drain_until(ws, "game_state")

        hand_tiles = state_msg["state"]["players"][0]["hand"]["tiles"]
        # Hand had 4 tiles; 4 moved to meld; 1 replacement drawn → 1 remaining
        # (BAMBOO_2 stays; CIRCLES_5 × 4 moved to meld; replacement added)
        assert "BAMBOO_2" in hand_tiles
        assert "CIRCLES_5" not in hand_tiles


# ---------------------------------------------------------------------------
# Skip
# ---------------------------------------------------------------------------


class TestClaimSkip:
    def test_skip_advances_to_next_draw(self, client):
        """Skipping when pung is available advances turn without creating a meld."""
        pid = "skip_claim"
        room_id = _create_and_start(client, pid)
        _setup_claiming(
            room_id,
            ["BAMBOO_1", "BAMBOO_1", "CIRCLES_3"],
            discard_tile="BAMBOO_1",
            discarder_idx=1,
        )

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            cw = _drain_until(ws, "claim_window")
            assert "pung" in cw["actions"]  # could pung, but will skip

            ws.send_json({"type": "skip"})
            state_msg = _drain_until(ws, "game_state")

        state = state_msg["state"]
        assert state["phase"] == "drawing"
        assert state["players"][0]["melds"] == []

    def test_skip_only_when_no_claim_possible(self, client):
        """When player holds unrelated tiles, claim_window offers only 'skip'."""
        pid = "skip_only"
        room_id = _create_and_start(client, pid)
        _setup_claiming(
            room_id,
            ["EAST", "SOUTH", "WEST"],
            discard_tile="BAMBOO_9",
            discarder_idx=1,
        )

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            cw = _drain_until(ws, "claim_window")

        assert cw["actions"] == ["skip"]
        assert "pung" not in cw["actions"]
        assert "chow" not in cw["actions"]
        assert "kong" not in cw["actions"]


# ---------------------------------------------------------------------------
# Win (ron)
# ---------------------------------------------------------------------------


class TestClaimWin:
    def test_win_in_claiming_phase_ends_game(self, client):
        """Declaring win on a completing discard ends the game."""
        pid = "win_claim"
        room_id = _create_and_start(client, pid)
        # 13-tile near-complete hand; EAST completes it as the pair
        near_complete = [
            "BAMBOO_1", "BAMBOO_2", "BAMBOO_3",
            "BAMBOO_4", "BAMBOO_5", "BAMBOO_6",
            "BAMBOO_7", "BAMBOO_8", "BAMBOO_9",
            "CIRCLES_1", "CIRCLES_1", "CIRCLES_1",
            "EAST",
        ]
        _setup_claiming(
            room_id, near_complete, discard_tile="EAST", discarder_idx=1
        )

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            cw = _drain_until(ws, "claim_window")
            assert "win" in cw["actions"]

            ws.send_json({"type": "win"})

            state_msg = _drain_until(ws, "game_state")
            game_over_msg = _drain_until(ws, "game_over")

        assert state_msg["state"]["phase"] == "ended"
        assert game_over_msg["winner_id"] == pid
        assert game_over_msg["winner_idx"] == 0
        assert game_over_msg["scores"][pid] > 0

    def test_win_not_offered_for_non_winning_hand(self, client):
        """'win' is absent from claim_window when hand + discard is not complete."""
        pid = "win_no_offer"
        room_id = _create_and_start(client, pid)
        _setup_claiming(
            room_id,
            ["BAMBOO_1", "BAMBOO_2", "BAMBOO_9"],
            discard_tile="BAMBOO_5",
            discarder_idx=1,
        )

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            cw = _drain_until(ws, "claim_window")

        assert "win" not in cw["actions"]

    def test_invalid_win_returns_error(self, client):
        """Manually sending win when hand is invalid returns an error message."""
        pid = "bad_win"
        room_id = _create_and_start(client, pid)
        # Force player into pending_claims with a non-winning hand
        _setup_claiming(
            room_id,
            ["BAMBOO_1", "BAMBOO_2", "BAMBOO_9"],
            discard_tile="BAMBOO_5",
            discarder_idx=1,
        )

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "claim_window")

            ws.send_json({"type": "win"})
            err = _drain_until(ws, "error")

        assert "winning" in err["message"].lower() or "not" in err["message"].lower()
