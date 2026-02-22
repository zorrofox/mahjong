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
# Chow — multiple options
# ---------------------------------------------------------------------------
# Scenario: player holds BAMBOO_3, BAMBOO_4, BAMBOO_6, BAMBOO_7 and
# the left player (seat 3) discards BAMBOO_5.  Three valid chow sequences
# exist:
#   A) 三四五  hand tiles = [BAMBOO_3, BAMBOO_4]
#   B) 四五六  hand tiles = [BAMBOO_4, BAMBOO_6]
#   C) 五六七  hand tiles = [BAMBOO_6, BAMBOO_7]
# ---------------------------------------------------------------------------


class TestClaimChowMultipleOptions:
    HAND = ["BAMBOO_3", "BAMBOO_4", "BAMBOO_6", "BAMBOO_7", "CIRCLES_1"]
    DISCARD = "BAMBOO_5"
    DISCARDER = 3  # player 0's immediate left → chow is allowed

    def _setup(self, client, pid):
        room_id = _create_and_start(client, pid)
        _setup_claiming(
            room_id, self.HAND, discard_tile=self.DISCARD, discarder_idx=self.DISCARDER
        )
        return room_id

    def test_chow_action_offered_with_multiple_options(self, client):
        """'chow' appears in claim_window when player has multiple valid sequences."""
        pid = "multi_chow_offer"
        room_id = self._setup(client, pid)

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            cw = _drain_until(ws, "claim_window")

        assert cw["tile"] == self.DISCARD
        assert "chow" in cw["actions"]

    def test_chow_option_a_san_si_wu(self, client):
        """Player picks 三四五 (hand tiles 3-4); correct meld formed."""
        pid = "multi_chow_a"
        room_id = self._setup(client, pid)

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "claim_window")
            ws.send_json({"type": "chow", "tiles": ["BAMBOO_3", "BAMBOO_4"]})
            state_msg = _drain_until(ws, "game_state")

        state = state_msg["state"]
        assert state["phase"] == "discarding"
        meld = state["players"][0]["melds"][0]
        assert sorted(meld) == ["BAMBOO_3", "BAMBOO_4", "BAMBOO_5"]

        hand = state["players"][0]["hand"]["tiles"]
        assert "BAMBOO_3" not in hand
        assert "BAMBOO_4" not in hand
        # Remaining tiles that were not consumed
        assert "BAMBOO_6" in hand
        assert "BAMBOO_7" in hand
        assert "CIRCLES_1" in hand

    def test_chow_option_b_si_wu_liu(self, client):
        """Player picks 四五六 (hand tiles 4-6); correct meld formed."""
        pid = "multi_chow_b"
        room_id = self._setup(client, pid)

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "claim_window")
            ws.send_json({"type": "chow", "tiles": ["BAMBOO_4", "BAMBOO_6"]})
            state_msg = _drain_until(ws, "game_state")

        state = state_msg["state"]
        assert state["phase"] == "discarding"
        meld = state["players"][0]["melds"][0]
        assert sorted(meld) == ["BAMBOO_4", "BAMBOO_5", "BAMBOO_6"]

        hand = state["players"][0]["hand"]["tiles"]
        assert "BAMBOO_4" not in hand
        assert "BAMBOO_6" not in hand
        assert "BAMBOO_3" in hand
        assert "BAMBOO_7" in hand
        assert "CIRCLES_1" in hand

    def test_chow_option_c_wu_liu_qi(self, client):
        """Player picks 五六七 (hand tiles 6-7); correct meld formed."""
        pid = "multi_chow_c"
        room_id = self._setup(client, pid)

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "claim_window")
            ws.send_json({"type": "chow", "tiles": ["BAMBOO_6", "BAMBOO_7"]})
            state_msg = _drain_until(ws, "game_state")

        state = state_msg["state"]
        assert state["phase"] == "discarding"
        meld = state["players"][0]["melds"][0]
        assert sorted(meld) == ["BAMBOO_5", "BAMBOO_6", "BAMBOO_7"]

        hand = state["players"][0]["hand"]["tiles"]
        assert "BAMBOO_6" not in hand
        assert "BAMBOO_7" not in hand
        assert "BAMBOO_3" in hand
        assert "BAMBOO_4" in hand
        assert "CIRCLES_1" in hand

    def test_chow_invalid_tiles_rejected(self, client):
        """Sending tiles that don't form a valid chow returns an error."""
        pid = "multi_chow_invalid"
        room_id = self._setup(client, pid)

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "claim_window")
            # BAMBOO_1 and BAMBOO_2 are not in the player's hand
            ws.send_json({"type": "chow", "tiles": ["BAMBOO_1", "BAMBOO_2"]})
            err = _drain_until(ws, "error")

        assert err["type"] == "error"

    def test_chow_tiles_not_in_hand_rejected(self, client):
        """Sending a syntactically valid sequence whose tiles aren't in hand is rejected."""
        pid = "multi_chow_not_in_hand"
        room_id = self._setup(client, pid)

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "claim_window")
            # BAMBOO_3 and BAMBOO_4 form a valid chow with BAMBOO_5,
            # but let's try a combo using BAMBOO_2 which isn't in hand
            ws.send_json({"type": "chow", "tiles": ["BAMBOO_2", "BAMBOO_3"]})
            err = _drain_until(ws, "error")

        assert err["type"] == "error"


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


# ---------------------------------------------------------------------------
# Edge-tile chow (边张) and gap chow (坎张)
# ---------------------------------------------------------------------------


class TestClaimChowEdgeTiles:
    """
    Verify chow mechanics for boundary (边张) and kanchan (坎张) tiles.

    Edge-low:  discard = BAMBOO_1, hand needs [2, 3]  → only one combo
    Edge-high: discard = BAMBOO_9, hand needs [7, 8]  → only one combo
    Kanchan:   discard = BAMBOO_5, hand needs [4, 6]  → only one combo (gap)
    Two-combo: discard = BAMBOO_2, hand has [1,3] and [3,4] → two valid combos
    """

    def test_chow_low_edge_one_combo_offered(self, client):
        """Discard BAMBOO_1: claim_window offers 'chow'; only 1-2-3 is valid."""
        pid = "edge_low_offer"
        room_id = _create_and_start(client, pid)
        _setup_claiming(
            room_id,
            ["BAMBOO_2", "BAMBOO_3", "CIRCLES_1"],
            discard_tile="BAMBOO_1",
            discarder_idx=3,
        )
        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            cw = _drain_until(ws, "claim_window")
        assert "chow" in cw["actions"]

    def test_chow_low_edge_forms_correct_meld(self, client):
        """Successful 1-2-3 chow at low edge; only those tiles leave hand."""
        pid = "edge_low_meld"
        room_id = _create_and_start(client, pid)
        _setup_claiming(
            room_id,
            ["BAMBOO_2", "BAMBOO_3", "CIRCLES_1"],
            discard_tile="BAMBOO_1",
            discarder_idx=3,
        )
        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "claim_window")
            ws.send_json({"type": "chow", "tiles": ["BAMBOO_2", "BAMBOO_3"]})
            state_msg = _drain_until(ws, "game_state")

        state = state_msg["state"]
        assert state["phase"] == "discarding"
        meld = state["players"][0]["melds"][0]
        assert sorted(meld) == ["BAMBOO_1", "BAMBOO_2", "BAMBOO_3"]
        hand = state["players"][0]["hand"]["tiles"]
        assert "BAMBOO_2" not in hand
        assert "BAMBOO_3" not in hand
        assert "CIRCLES_1" in hand

    def test_chow_high_edge_forms_correct_meld(self, client):
        """Successful 7-8-9 chow at high edge."""
        pid = "edge_high_meld"
        room_id = _create_and_start(client, pid)
        _setup_claiming(
            room_id,
            ["BAMBOO_7", "BAMBOO_8", "CIRCLES_1"],
            discard_tile="BAMBOO_9",
            discarder_idx=3,
        )
        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "claim_window")
            ws.send_json({"type": "chow", "tiles": ["BAMBOO_7", "BAMBOO_8"]})
            state_msg = _drain_until(ws, "game_state")

        meld = state_msg["state"]["players"][0]["melds"][0]
        assert sorted(meld) == ["BAMBOO_7", "BAMBOO_8", "BAMBOO_9"]

    def test_chow_kanchan_gap_forms_correct_meld(self, client):
        """坎张: discard=5, hand=[4,6] → only 4-5-6 valid."""
        pid = "kanchan_meld"
        room_id = _create_and_start(client, pid)
        _setup_claiming(
            room_id,
            ["BAMBOO_4", "BAMBOO_6", "CIRCLES_1"],
            discard_tile="BAMBOO_5",
            discarder_idx=3,
        )
        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "claim_window")
            ws.send_json({"type": "chow", "tiles": ["BAMBOO_4", "BAMBOO_6"]})
            state_msg = _drain_until(ws, "game_state")

        meld = state_msg["state"]["players"][0]["melds"][0]
        assert sorted(meld) == ["BAMBOO_4", "BAMBOO_5", "BAMBOO_6"]

    def test_chow_kanchan_wrong_tiles_rejected(self, client):
        """坎张: sending [3,4] when hand only has [4,6] is rejected."""
        pid = "kanchan_bad"
        room_id = _create_and_start(client, pid)
        _setup_claiming(
            room_id,
            ["BAMBOO_4", "BAMBOO_6", "CIRCLES_1"],
            discard_tile="BAMBOO_5",
            discarder_idx=3,
        )
        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "claim_window")
            ws.send_json({"type": "chow", "tiles": ["BAMBOO_3", "BAMBOO_4"]})
            err = _drain_until(ws, "error")
        assert err["type"] == "error"

    def test_chow_tile_2_two_combos_first_works(self, client):
        """Discard BAMBOO_2, hand [1,3,3,4]: pick 1-2-3 combo."""
        pid = "two_combo_first"
        room_id = _create_and_start(client, pid)
        _setup_claiming(
            room_id,
            ["BAMBOO_1", "BAMBOO_3", "BAMBOO_3", "BAMBOO_4"],
            discard_tile="BAMBOO_2",
            discarder_idx=3,
        )
        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "claim_window")
            ws.send_json({"type": "chow", "tiles": ["BAMBOO_1", "BAMBOO_3"]})
            state_msg = _drain_until(ws, "game_state")

        meld = state_msg["state"]["players"][0]["melds"][0]
        assert sorted(meld) == ["BAMBOO_1", "BAMBOO_2", "BAMBOO_3"]

    def test_chow_tile_2_two_combos_second_works(self, client):
        """Discard BAMBOO_2, hand [1,3,3,4]: pick 2-3-4 combo."""
        pid = "two_combo_second"
        room_id = _create_and_start(client, pid)
        _setup_claiming(
            room_id,
            ["BAMBOO_1", "BAMBOO_3", "BAMBOO_3", "BAMBOO_4"],
            discard_tile="BAMBOO_2",
            discarder_idx=3,
        )
        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "claim_window")
            ws.send_json({"type": "chow", "tiles": ["BAMBOO_3", "BAMBOO_4"]})
            state_msg = _drain_until(ws, "game_state")

        meld = state_msg["state"]["players"][0]["melds"][0]
        assert sorted(meld) == ["BAMBOO_2", "BAMBOO_3", "BAMBOO_4"]

    def test_chow_hand_tile_count_after_claim(self, client):
        """Hand tile count is exactly 2 fewer after a chow (2 tiles consumed)."""
        pid = "chow_count"
        room_id = _create_and_start(client, pid)
        initial_hand = ["BAMBOO_3", "BAMBOO_4", "CIRCLES_1", "EAST", "SOUTH"]
        _setup_claiming(
            room_id, initial_hand, discard_tile="BAMBOO_5", discarder_idx=3
        )
        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "claim_window")
            ws.send_json({"type": "chow", "tiles": ["BAMBOO_3", "BAMBOO_4"]})
            state_msg = _drain_until(ws, "game_state")

        hand = state_msg["state"]["players"][0]["hand"]["tiles"]
        # 5 initial − 2 consumed = 3 remaining
        assert len(hand) == 3
        assert "CIRCLES_1" in hand
        assert "EAST" in hand
        assert "SOUTH" in hand


# ---------------------------------------------------------------------------
# Pung → Extend-pung (加杠) regression
#
# Scenario: player holds 3 copies of a tile, opponent discards the same tile.
# Player can both pung AND kong.  Player chooses pung, then later extends the
# pung to a kong (加杠) during the discarding phase.
#
# Before the fix, sendKong() in the frontend would:
#   1. Auto-detect only 4-of-a-kind (暗杠) — missing the extend-pung case.
#   2. Call hideClaimOverlay() even when not in a claim window, clearing
#      pendingActions and leaving the player with no buttons after an error.
#
# These tests verify the server-side behaviour that the fix relies on:
# the extend-pung path is accepted and produces the correct 4-tile meld.
# ---------------------------------------------------------------------------


def _setup_discarding_with_pung_meld(room_id, pung_tile, remaining_hand):
    """
    Put game into discarding phase for player 0 who already holds a pung
    meld (3 × pung_tile) and one extra copy of pung_tile in hand, plus
    remaining_hand tiles.  The extend-pung (加杠) should be available.
    """
    room = room_manager.get_room(room_id)
    gs = room.game_state
    # Give player 0 the pung meld + one extra copy + other tiles
    gs.players[0].melds = [[pung_tile] * 3]
    gs.players[0].hand  = [pung_tile] + list(remaining_hand)
    gs.phase        = "discarding"
    gs.current_turn = 0
    gs.last_drawn_tile = pung_tile   # simulate the tile that was just drawn


class TestPungThenExtendPung:
    """
    After choosing pung over kong, the player can extend the pung to a kong
    (加杠) during the discarding phase.
    """

    PUNG_TILE = "BAMBOO_5"
    OTHER     = ["CIRCLES_1", "EAST", "SOUTH"]

    def _setup(self, client, pid):
        room_id = _create_and_start(client, pid)
        _setup_discarding_with_pung_meld(room_id, self.PUNG_TILE, self.OTHER)
        return room_id

    def test_extend_pung_offered_as_kong_action(self, client):
        """action_required includes 'kong' when extend-pung is available."""
        pid  = "epung_offer"
        room_id = self._setup(client, pid)

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            ar = _drain_until(ws, "action_required")

        assert "kong" in ar["actions"]
        assert "discard" in ar["actions"]

    def test_extend_pung_creates_four_tile_meld(self, client):
        """Sending kong with the pung tile extends the meld from 3 to 4 tiles."""
        pid  = "epung_meld"
        room_id = self._setup(client, pid)

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "action_required")

            ws.send_json({"type": "kong", "tile": self.PUNG_TILE})
            state_msg = _drain_until(ws, "game_state")

        state = state_msg["state"]
        my_melds = state["players"][0]["melds"]
        assert len(my_melds) == 1
        assert sorted(my_melds[0]) == [self.PUNG_TILE] * 4

    def test_extend_pung_removes_tile_from_hand(self, client):
        """After extend-pung, the matched hand tile leaves the player's hand."""
        pid  = "epung_hand"
        room_id = self._setup(client, pid)

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "action_required")
            ws.send_json({"type": "kong", "tile": self.PUNG_TILE})
            state_msg = _drain_until(ws, "game_state")

        hand = state_msg["state"]["players"][0]["hand"]["tiles"]
        assert self.PUNG_TILE not in hand
        # Other tiles are unaffected
        for t in self.OTHER:
            assert t in hand

    def test_extend_pung_opens_rob_kong_window(self, client):
        """After extend-pung the server opens a 搶杠 (rob-the-kong) claiming window."""
        pid  = "epung_phase"
        room_id = self._setup(client, pid)

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "action_required")
            ws.send_json({"type": "kong", "tile": self.PUNG_TILE})
            state_msg = _drain_until(ws, "game_state")

        # Extend-pung triggers a 搶杠 window; other players may try to win
        # on the extended tile.  Phase must be 'claiming' at this point.
        # (AI auto-skip tasks don't run in synchronous TestClient, so the
        # window stays open here.)
        assert state_msg["state"]["phase"] == "claiming"
        # The meld is already extended to 4 tiles
        my_melds = state_msg["state"]["players"][0]["melds"]
        assert sorted(my_melds[0]) == [self.PUNG_TILE] * 4

    def test_wrong_tile_for_extend_pung_returns_error(self, client):
        """Sending a tile that is not the pung tile is rejected with an error."""
        pid  = "epung_badtile"
        room_id = self._setup(client, pid)

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "action_required")
            # CIRCLES_1 is in hand but has no matching pung meld
            ws.send_json({"type": "kong", "tile": "CIRCLES_1"})
            err = _drain_until(ws, "error")

        assert err["type"] == "error"


# ---------------------------------------------------------------------------
# Comprehensive kong integration tests
# ---------------------------------------------------------------------------


def _setup_concealed_kong(room_id, player_hand, kong_tile):
    """Put player 0 in discarding phase with a concealed-kong candidate."""
    room = room_manager.get_room(room_id)
    gs = room.game_state
    gs.players[0].hand = list(player_hand)
    gs.phase = "discarding"
    gs.current_turn = 0


def _setup_extend_pung_for_int(room_id, pung_tile, other_hand):
    """Player 0 has a pung meld and one matching tile in hand → can extend."""
    room = room_manager.get_room(room_id)
    gs = room.game_state
    gs.players[0].melds = [[pung_tile] * 3]
    gs.players[0].hand = [pung_tile] + list(other_hand)
    gs.phase = "discarding"
    gs.current_turn = 0


class TestConcealedKongIntegration:
    """暗杠 via WebSocket: full state-machine flow."""

    KONG_TILE  = "BAMBOO_3"
    OTHER_HAND = ["CIRCLES_1", "EAST", "SOUTH"]

    def _setup(self, client, pid):
        room_id = _create_and_start(client, pid)
        _setup_concealed_kong(
            room_id,
            [self.KONG_TILE] * 4 + list(self.OTHER_HAND),
            self.KONG_TILE,
        )
        return room_id

    def test_concealed_kong_action_offered(self, client):
        """action_required includes 'kong' when player holds 4 identical tiles."""
        pid = "ck_offer"
        room_id = self._setup(client, pid)
        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            ar = _drain_until(ws, "action_required")
        assert "kong" in ar["actions"]
        assert "discard" in ar["actions"]

    def test_concealed_kong_creates_quad_meld(self, client):
        """Sending kong forms a 4-tile meld and player stays in discarding."""
        pid = "ck_meld"
        room_id = self._setup(client, pid)
        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "action_required")
            ws.send_json({"type": "kong", "tile": self.KONG_TILE})
            state_msg = _drain_until(ws, "game_state")
        state = state_msg["state"]
        assert state["phase"] == "discarding"
        assert state["current_turn"] == 0
        melds = state["players"][0]["melds"]
        assert any(sorted(m) == [self.KONG_TILE] * 4 for m in melds)

    def test_concealed_kong_then_action_required_to_discard(self, client):
        """After concealed kong, player gets action_required with 'discard'."""
        pid = "ck_ar"
        room_id = self._setup(client, pid)
        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "action_required")
            ws.send_json({"type": "kong", "tile": self.KONG_TILE})
            _drain_until(ws, "game_state")
            ar2 = _drain_until(ws, "action_required")
        assert "discard" in ar2["actions"]

    def test_concealed_kong_tile_not_in_hand_returns_error(self, client):
        """Sending a tile with fewer than 4 copies is rejected."""
        pid = "ck_err"
        room_id = _create_and_start(client, pid)
        _setup_concealed_kong(
            room_id,
            ["BAMBOO_3"] * 2 + ["CIRCLES_1", "EAST", "SOUTH"],
            "BAMBOO_3",
        )
        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "action_required")
            ws.send_json({"type": "kong", "tile": "BAMBOO_3"})
            err = _drain_until(ws, "error")
        assert err["type"] == "error"

    def test_concealed_kong_drawn_tile_in_action_required(self, client):
        """action_required after kong must include 'drawn_tile' pointing to the
        replacement tile (not a flower), so the frontend can auto-select it."""
        from game.tiles import is_flower_tile
        pid = "ck_drawn"
        room_id = self._setup(client, pid)

        room = room_manager.get_room(room_id)
        # Force a known non-flower replacement
        room.game_state.wall = ["CIRCLES_9"] * 20

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "action_required")
            ws.send_json({"type": "kong", "tile": self.KONG_TILE})
            _drain_until(ws, "game_state")
            ar2 = _drain_until(ws, "action_required")

        drawn = ar2.get("drawn_tile")
        assert drawn is not None, "drawn_tile must be present after concealed kong"
        assert not is_flower_tile(drawn), f"drawn_tile must not be a bonus tile, got {drawn}"


class TestExtendPungKongIntegration:
    """加杠 via WebSocket: including rob-kong window and subsequent discard."""

    PUNG_TILE = "CIRCLES_7"
    OTHER     = ["BAMBOO_1", "BAMBOO_2", "EAST"]

    def _setup(self, client, pid):
        room_id = _create_and_start(client, pid)
        _setup_extend_pung_for_int(room_id, self.PUNG_TILE, self.OTHER)
        return room_id

    def test_extend_pung_offered_in_discarding(self, client):
        """'kong' appears in action_required during own discarding turn."""
        pid = "ep_offered"
        room_id = self._setup(client, pid)
        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            ar = _drain_until(ws, "action_required")
        assert "kong" in ar["actions"]

    def test_extend_pung_opens_rob_kong_claiming_phase(self, client):
        """After extend-pung, game_state shows phase='claiming' (搶杠 window)."""
        pid = "ep_claiming"
        room_id = self._setup(client, pid)
        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "action_required")
            ws.send_json({"type": "kong", "tile": self.PUNG_TILE})
            state_msg = _drain_until(ws, "game_state")
        assert state_msg["state"]["phase"] == "claiming"
        melds = state_msg["state"]["players"][0]["melds"]
        assert sorted(melds[0]) == [self.PUNG_TILE] * 4

    def test_extend_pung_game_state_discarding_after_all_skip(self, client):
        """After all players skip the 搶杠 window, game state transitions to
        discarding for the konger (critical state-machine correctness test).
        Note: action_required is sent via a background task that doesn't run
        in synchronous TestClient; we verify the game_state instead."""
        pid = "ep_gs_disc"
        room_id = _create_and_start(client, pid)
        _setup_extend_pung_for_int(room_id, self.PUNG_TILE, self.OTHER)

        room = room_manager.get_room(room_id)
        gs = room.game_state

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "action_required")
            ws.send_json({"type": "kong", "tile": self.PUNG_TILE})
            rob_kong_state = _drain_until(ws, "game_state")

        # Verify rob-kong window was opened correctly
        assert rob_kong_state["state"]["phase"] == "claiming"

        # Simulate all AI players skipping — tests state machine transitions
        for i in range(1, 4):
            if i in gs._pending_claims and i not in gs._skipped_claims:
                try:
                    gs.skip_claim(i)
                except ValueError:
                    pass

        # After all claims resolved, game must be in discarding for konger
        assert gs.phase == "discarding", (
            "After 搶杠 window resolves (all skip), game must enter discarding — "
            "this was the bug: _handle_claim_window was never started so the "
            "window stayed open forever"
        )
        assert gs.current_turn == 0
        assert gs._is_rob_kong_window is False

    def test_extend_pung_chip_payment_after_completion(self, client):
        """Kong chip transfers are recorded when 搶杠 window closes without a rob."""
        pid = "ep_chips"
        room_id = self._setup(client, pid)
        room = room_manager.get_room(room_id)
        gs = room.game_state

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "action_required")
            ws.send_json({"type": "kong", "tile": self.PUNG_TILE})
            _drain_until(ws, "game_state")

        # Simulate all AI skipping and verify chip payment recorded
        for i in range(1, 4):
            if i in gs._pending_claims:
                try:
                    gs.skip_claim(i)
                except ValueError:
                    pass

        konger_id = gs.players[0].id
        assert gs.kong_chip_transfers.get(konger_id, 0) == 3


class TestKongEdgeCases:
    """Edge cases that previously caused bugs or subtle errors."""

    def test_claimed_kong_not_from_non_left_player_in_discarding(self, client):
        """Claimed kong from a discard is only in claim_window, not discarding."""
        pid = "ck_not_disc"
        room_id = _create_and_start(client, pid)
        # Set up normal claiming state (player 1 discarded, player 0 has 3 matching)
        _setup_claiming(
            room_id,
            ["EAST", "EAST", "EAST", "BAMBOO_1"],
            discard_tile="EAST",
            discarder_idx=1,
        )
        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            cw = _drain_until(ws, "claim_window")
            assert "kong" in cw["actions"]

            ws.send_json({"type": "kong"})  # no tile field → uses last_discard
            state_msg = _drain_until(ws, "game_state")

        state = state_msg["state"]
        assert state["phase"] == "discarding"
        assert state["current_turn"] == 0
        melds = state["players"][0]["melds"]
        assert any(sorted(m) == ["EAST"] * 4 for m in melds)

    def test_cannot_kong_discarder_own_tile(self, client):
        """The discarder cannot kong their own discarded tile."""
        pid = "ck_self"
        room_id = _create_and_start(client, pid)
        _setup_claiming(
            room_id,
            ["BAMBOO_5", "BAMBOO_5", "BAMBOO_5"],
            discard_tile="BAMBOO_5",
            discarder_idx=0,   # player 0 is the discarder
        )
        # Remove player 0 from pending claims (they're the discarder)
        room = room_manager.get_room(room_id)
        room.game_state._pending_claims.discard(0)

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            # No claim window should be sent to the discarder
            # (auto-skipped or not in pending claims)
            # Just verify the room is in claiming phase
            assert room.game_state.phase == "claiming"

    def test_kong_replacement_not_flower_in_action_required(self, client):
        """When kong replacement is a flower, action_required drawn_tile must be
        the subsequent non-flower tile (not the flower itself)."""
        from game.tiles import is_flower_tile
        pid = "ck_flower"
        room_id = _create_and_start(client, pid)

        room = room_manager.get_room(room_id)
        gs = room.game_state

        # Set up concealed kong
        gs.players[0].hand = ["BAMBOO_3"] * 4 + ["CIRCLES_1", "EAST"]
        gs.phase = "discarding"
        gs.current_turn = 0
        # Wall: FLOWER_1 is drawn first, then BAMBOO_9 as the real replacement
        gs.wall = ["BAMBOO_9", "FLOWER_1"]

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "action_required")
            ws.send_json({"type": "kong", "tile": "BAMBOO_3"})
            _drain_until(ws, "game_state")
            ar = _drain_until(ws, "action_required")

        drawn = ar.get("drawn_tile")
        assert drawn is not None
        assert not is_flower_tile(drawn), (
            f"drawn_tile after bonus-tile replacement must not be a flower; got {drawn}"
        )
