"""Integration tests verifying hand tile ordering from the server.

The server returns tiles in draw/discard history order (not sorted).
These tests confirm:
  1. The server does NOT sort tiles (it is the client's responsibility).
  2. A deliberately shuffled hand is returned as-is, giving the client
     data it must sort before display.
  3. After a pung/chow claim the newly-added tiles appear at arbitrary
     positions, confirming the client still needs to sort.

The actual visual sort is implemented in frontend/js/game.js
sortHandTiles(), tested thoroughly in frontend/tests/game.test.js.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../backend'))

from api.routes import room_manager


# ---------------------------------------------------------------------------
# Helpers (shared with test_claim_window.py)
# ---------------------------------------------------------------------------

def _create_and_start(client, player_id="hand_order_player"):
    room_id = client.post("/api/rooms").json()["id"]
    client.post(f"/api/rooms/{room_id}/join", json={"player_id": player_id})
    client.post(f"/api/rooms/{room_id}/start")
    return room_id


def _set_hand(room_id, player_idx, tiles):
    """Replace a player's hand with the given tile list (preserves order)."""
    room = room_manager.get_room(room_id)
    room.game_state.players[player_idx].hand = list(tiles)


def _get_hand_tiles_from_state(state, player_idx):
    """Extract the tiles list from a game_state dict for the given player."""
    hand = state["players"][player_idx]["hand"]
    assert hand["hidden"] is False, "Expected visible hand for this player"
    return hand["tiles"]


def _drain_until(ws, target_type, max_msgs=8):
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
        f"Expected '{target_type}' not found in {len(received)} messages. Got: {types}"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHandOrderFromServer:
    def test_server_returns_tiles_in_insertion_order(self, client):
        """Server sends tiles in the order they were added (not sorted).

        We set a deliberately reverse-sorted hand and confirm the server
        returns it in exactly that order, i.e. *the server does not sort*.
        The client is responsible for sorting before display.
        """
        pid = "order_check"
        room_id = _create_and_start(client, pid)

        # Set a reverse-order hand (9 down to 1)
        reverse_hand = [
            "BAMBOO_9", "BAMBOO_8", "BAMBOO_7",
            "BAMBOO_6", "BAMBOO_5", "BAMBOO_4",
            "BAMBOO_3", "BAMBOO_2", "BAMBOO_1",
            "EAST", "SOUTH", "WEST", "NORTH",
        ]
        _set_hand(room_id, 0, reverse_hand)

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            state_msg = _drain_until(ws, "game_state")

        tiles = _get_hand_tiles_from_state(state_msg["state"], 0)
        # Server must preserve insertion order (not sort)
        assert tiles == reverse_hand, (
            f"Expected server to return tiles unsorted.\n"
            f"Got: {tiles}"
        )

    def test_server_returns_mixed_suit_hand_unsorted(self, client):
        """A hand with mixed suits arrives in the server's storage order."""
        pid = "mixed_order"
        room_id = _create_and_start(client, pid)

        mixed_hand = [
            "EAST", "CIRCLES_3", "BAMBOO_7", "CHARACTERS_1",
            "RED", "BAMBOO_2", "CIRCLES_9", "CHARACTERS_5",
            "WEST", "BAMBOO_5", "CIRCLES_1", "CHARACTERS_9",
            "NORTH",
        ]
        _set_hand(room_id, 0, mixed_hand)

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            state_msg = _drain_until(ws, "game_state")

        tiles = _get_hand_tiles_from_state(state_msg["state"], 0)
        assert tiles == mixed_hand

    def test_pung_appends_tile_to_arbitrary_position(self, client):
        """After pung, the discard tile is appended then the meld removed;
        remaining tiles are NOT sorted by the server."""
        pid = "pung_order"
        room_id = _create_and_start(client, pid)

        gs = room_manager.get_room(room_id).game_state

        # Give player 0 two CIRCLES_5 and some other tiles
        hand_before = ["EAST", "BAMBOO_9", "CIRCLES_5", "CIRCLES_5", "CHARACTERS_1"]
        gs.players[0].hand = list(hand_before)
        gs.discards[1].append("CIRCLES_5")
        gs.last_discard = "CIRCLES_5"
        gs.last_discard_player = 1
        gs.current_turn = 1
        gs.phase = "claiming"
        gs._pending_claims = {0, 2, 3}
        gs._skipped_claims = {2, 3}
        gs._best_claim = None

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            _drain_until(ws, "game_state")
            _drain_until(ws, "claim_window")

            ws.send_json({"type": "pung"})
            state_msg = _drain_until(ws, "game_state")

        state = state_msg["state"]
        assert state["phase"] == "discarding"

        # Pung meld formed
        melds = state["players"][0]["melds"]
        assert len(melds) == 1
        assert sorted(melds[0]) == ["CIRCLES_5", "CIRCLES_5", "CIRCLES_5"]

        # Remaining hand: EAST, BAMBOO_9, CHARACTERS_1 (order not guaranteed)
        remaining = state["players"][0]["hand"]["tiles"]
        assert sorted(remaining) == sorted(["EAST", "BAMBOO_9", "CHARACTERS_1"]), (
            f"Unexpected remaining hand: {remaining}"
        )


class TestClientSortingLogic:
    """Verify that the sort order produced by sortHandTiles() (JS) is correct
    by replicating the same algorithm in Python and checking representative
    hands.  This acts as a cross-language sanity check.
    """

    # Replication of the JS TILE_MAP suit field and SUIT_ORDER
    _SUIT_ORDER = {"B": 0, "C": 1, "M": 2}
    _TILE_SUIT = {}  # populated in _setup

    @classmethod
    def _build_tile_suit_map(cls):
        suits = {"BAMBOO": "B", "CIRCLES": "C", "CHARACTERS": "M"}
        for prefix, suit in suits.items():
            for n in range(1, 10):
                cls._TILE_SUIT[f"{prefix}_{n}"] = suit

    @classmethod
    def _sort_key(cls, tile):
        suit = cls._TILE_SUIT.get(tile)
        suit_priority = cls._SUIT_ORDER.get(suit, 3) if suit else 3
        label = tile  # for honors/flowers we use the tile string itself
        if suit:
            # label is like "B1", "C5", "M9" — use number part for ordering
            label = suit + tile.split("_")[1]
        return (suit_priority, label)

    @classmethod
    def _sort(cls, hand):
        cls._build_tile_suit_map()
        return sorted(hand, key=cls._sort_key)

    def test_bamboo_before_circles_before_characters(self):
        hand = ["CHARACTERS_1", "CIRCLES_1", "BAMBOO_1"]
        assert self._sort(hand) == ["BAMBOO_1", "CIRCLES_1", "CHARACTERS_1"]

    def test_numbers_within_suit_ascending(self):
        hand = ["BAMBOO_9", "BAMBOO_1", "BAMBOO_5", "BAMBOO_3"]
        assert self._sort(hand) == ["BAMBOO_1", "BAMBOO_3", "BAMBOO_5", "BAMBOO_9"]

    def test_honors_after_suits(self):
        hand = ["EAST", "BAMBOO_3", "RED", "CIRCLES_7"]
        result = self._sort(hand)
        bamboo_idx = result.index("BAMBOO_3")
        circles_idx = result.index("CIRCLES_7")
        east_idx = result.index("EAST")
        red_idx = result.index("RED")
        assert bamboo_idx < east_idx
        assert circles_idx < red_idx

    def test_full_realistic_hand(self):
        hand = [
            "EAST", "BAMBOO_7", "CIRCLES_3", "CHARACTERS_1",
            "BAMBOO_2", "CIRCLES_9", "CHARACTERS_5", "RED",
            "BAMBOO_5", "CIRCLES_1", "CHARACTERS_9", "NORTH",
            "FLOWER_1",
        ]
        result = self._sort(hand)
        # All bamboo tiles come first
        bamboo = [t for t in result if t.startswith("BAMBOO")]
        circles = [t for t in result if t.startswith("CIRCLES")]
        chars   = [t for t in result if t.startswith("CHARACTERS")]
        first_bamboo = result.index(bamboo[0])
        last_bamboo  = result.index(bamboo[-1])
        first_circle = result.index(circles[0])
        last_circle  = result.index(circles[-1])
        first_char   = result.index(chars[0])
        assert last_bamboo < first_circle
        assert last_circle < first_char
