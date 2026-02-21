"""Integration tests for the WebSocket game protocol.

Note: Starlette's TestClient WebSocket runs synchronously. Async tasks
created with asyncio.create_task (like AI turns) do NOT execute in this
context.  We therefore test only the synchronous message flow:

  - On connect to a started game: game_state is sent immediately.
  - start_game via WS: game_state is broadcast.
  - Invalid actions produce error messages.
  - Hand visibility is correct per player.

We avoid tests that depend on AI async loops (discard/claim cycles).
"""

import threading
import pytest


def _create_and_start(client, player_id="test_player"):
    """Helper: create a room, join with one player, start the game via REST."""
    room_id = client.post("/api/rooms").json()["id"]
    client.post(f"/api/rooms/{room_id}/join", json={"player_id": player_id})
    client.post(f"/api/rooms/{room_id}/start")
    return room_id


def _recv_expect(ws, expected_type, max_msgs=5):
    """Receive up to max_msgs messages, returning the first one matching
    expected_type.  Raises AssertionError if not found.

    We know the exact number of synchronous sends on connect:
      1. game_state (always, for started games)
      2. possibly action_required or claim_window (synchronous sends)
      3. room_update (broadcast on connect)

    So max_msgs=5 is generous enough.
    """
    received = []
    for _ in range(max_msgs):
        try:
            msg = ws.receive_json()
            received.append(msg)
            if msg.get("type") == expected_type:
                return msg
        except Exception:
            break
    types = [m.get("type") for m in received]
    raise AssertionError(
        f"Expected message type '{expected_type}' not found in {len(received)} "
        f"messages. Got types: {types}"
    )


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


class TestWebSocketConnect:
    def test_connect_receives_game_state(self, client):
        """Connecting to a started game should yield a game_state message."""
        player_id = "ws_player_1"
        room_id = _create_and_start(client, player_id)

        with client.websocket_connect(f"/ws/{room_id}/{player_id}") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "game_state"
            state = msg["state"]
            assert "players" in state
            assert "phase" in state
            assert "wall_remaining" in state
            assert len(state["players"]) == 4

    def test_game_state_structure(self, client):
        """Verify the game_state message has all expected fields."""
        player_id = "ws_struct"
        room_id = _create_and_start(client, player_id)

        with client.websocket_connect(f"/ws/{room_id}/{player_id}") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "game_state"
            state = msg["state"]
            # Top-level fields
            assert state["room_id"] == room_id
            assert state["phase"] in ("drawing", "discarding", "claiming", "ended")
            assert isinstance(state["current_turn"], int)
            assert isinstance(state["wall_remaining"], int)
            assert state["wall_remaining"] > 0
            assert isinstance(state["discards"], list)
            assert len(state["discards"]) == 4
            # Player structure
            p = state["players"][0]
            assert "id" in p
            assert "hand" in p
            assert "melds" in p
            assert "flowers" in p
            assert "score" in p
            assert "is_ai" in p

    def test_game_state_hides_opponent_hands(self, client):
        """The viewing player should see their own tiles but not opponents'."""
        player_id = "ws_vis"
        room_id = _create_and_start(client, player_id)

        with client.websocket_connect(f"/ws/{room_id}/{player_id}") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "game_state"
            players = msg["state"]["players"]
            # Player 0 is us (the human)
            my_hand = players[0]["hand"]
            assert my_hand["hidden"] is False
            assert "tiles" in my_hand
            assert len(my_hand["tiles"]) > 0
            # Other players' hands should be hidden
            for p in players[1:]:
                assert p["hand"]["hidden"] is True
                assert "count" in p["hand"]


class TestWebSocketStartGame:
    def test_start_game_via_ws(self, client):
        """Sending start_game via WS should start the game and return game_state."""
        player_id = "ws_starter"
        room_id = client.post("/api/rooms").json()["id"]
        client.post(f"/api/rooms/{room_id}/join", json={"player_id": player_id})
        # Do NOT start via REST; start via WS instead
        with client.websocket_connect(f"/ws/{room_id}/{player_id}") as ws:
            # On connect to a waiting room, we get room_update but no game_state
            ws.send_json({"type": "start_game"})
            # After start_game, server broadcasts game_state
            msg = ws.receive_json()
            # Could be room_update or game_state; find game_state
            msgs = [msg]
            while msg.get("type") != "game_state":
                msg = ws.receive_json()
                msgs.append(msg)
                if len(msgs) > 5:
                    break
            gs = next((m for m in msgs if m.get("type") == "game_state"), None)
            assert gs is not None, f"Expected game_state, got: {[m['type'] for m in msgs]}"
            assert len(gs["state"]["players"]) == 4

    def test_start_game_twice_via_ws(self, client):
        """Starting a game that's already started should return an error."""
        player_id = "ws_double_start"
        room_id = _create_and_start(client, player_id)

        with client.websocket_connect(f"/ws/{room_id}/{player_id}") as ws:
            # Drain initial game_state
            ws.receive_json()
            ws.send_json({"type": "start_game"})
            msg = ws.receive_json()
            # Should be an error since game already started
            # Could be room_update first, then error
            msgs = [msg]
            for _ in range(3):
                if any(m.get("type") == "error" for m in msgs):
                    break
                try:
                    msgs.append(ws.receive_json())
                except Exception:
                    break
            err = next((m for m in msgs if m.get("type") == "error"), None)
            assert err is not None
            assert "already" in err["message"].lower() or "started" in err["message"].lower()


class TestWebSocketInvalidAction:
    def test_invalid_message_type(self, client):
        """Sending an unknown message type should return an error."""
        player_id = "ws_invalid"
        room_id = _create_and_start(client, player_id)

        with client.websocket_connect(f"/ws/{room_id}/{player_id}") as ws:
            ws.receive_json()  # drain game_state
            ws.send_json({"type": "bogus_action"})
            msg = ws.receive_json()
            # Might get action_required or room_update first, then our response
            msgs = [msg]
            for _ in range(3):
                if any(m.get("type") == "error" for m in msgs):
                    break
                try:
                    msgs.append(ws.receive_json())
                except Exception:
                    break
            err = next((m for m in msgs if m.get("type") == "error"), None)
            assert err is not None
            assert "unknown" in err["message"].lower() or "Unknown" in err["message"]

    def test_game_not_active_error(self, client):
        """Sending game actions before game starts should error."""
        player_id = "ws_no_game"
        room_id = client.post("/api/rooms").json()["id"]
        client.post(f"/api/rooms/{room_id}/join", json={"player_id": player_id})

        with client.websocket_connect(f"/ws/{room_id}/{player_id}") as ws:
            ws.send_json({"type": "discard", "tile": "BAMBOO_1"})
            msg = ws.receive_json()
            msgs = [msg]
            for _ in range(3):
                if any(m.get("type") == "error" for m in msgs):
                    break
                try:
                    msgs.append(ws.receive_json())
                except Exception:
                    break
            err = next((m for m in msgs if m.get("type") == "error"), None)
            assert err is not None

    def test_skip_outside_claiming_phase(self, client):
        """Sending skip when not in claiming phase should error."""
        player_id = "ws_skip"
        room_id = _create_and_start(client, player_id)

        with client.websocket_connect(f"/ws/{room_id}/{player_id}") as ws:
            ws.receive_json()  # drain game_state
            ws.send_json({"type": "skip"})
            msg = ws.receive_json()
            msgs = [msg]
            for _ in range(3):
                if any(m.get("type") == "error" for m in msgs):
                    break
                try:
                    msgs.append(ws.receive_json())
                except Exception:
                    break
            err = next((m for m in msgs if m.get("type") == "error"), None)
            assert err is not None


class TestWebSocketTwoPlayers:
    def test_two_players_different_views(self, client):
        """Two human players should each see their own hand and not the other's."""
        p1 = "ws_two_p1"
        p2 = "ws_two_p2"
        room_id = client.post("/api/rooms").json()["id"]
        client.post(f"/api/rooms/{room_id}/join", json={"player_id": p1})
        client.post(f"/api/rooms/{room_id}/join", json={"player_id": p2})
        client.post(f"/api/rooms/{room_id}/start")

        # Test p1's view
        with client.websocket_connect(f"/ws/{room_id}/{p1}") as ws1:
            msg1 = ws1.receive_json()
            assert msg1["type"] == "game_state"
            players1 = msg1["state"]["players"]
            assert players1[0]["hand"]["hidden"] is False  # p1 sees own hand
            assert players1[1]["hand"]["hidden"] is True   # p1 can't see p2

        # Test p2's view
        with client.websocket_connect(f"/ws/{room_id}/{p2}") as ws2:
            msg2 = ws2.receive_json()
            assert msg2["type"] == "game_state"
            players2 = msg2["state"]["players"]
            assert players2[1]["hand"]["hidden"] is False  # p2 sees own hand
            assert players2[0]["hand"]["hidden"] is True   # p2 can't see p1


class TestRestartGame:
    """Verify that a finished game can be restarted via the restart_game WS message."""

    def _drain_until(self, ws, target_type, max_msgs=8):
        for _ in range(max_msgs):
            try:
                msg = ws.receive_json()
                if msg.get("type") == target_type:
                    return msg
            except Exception:
                break
        raise AssertionError(f"Message type '{target_type}' not received.")

    def test_restart_game_resets_state(self, client):
        """After game ends, sending restart_game starts a fresh game."""
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../backend'))
        from api.routes import room_manager

        pid = "restart_player"
        room_id = _create_and_start(client, pid)

        # Force the game into "ended" state
        room = room_manager.get_room(room_id)
        room.game_state.phase = "ended"
        room.status = "ended"

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            self._drain_until(ws, "game_state")
            ws.send_json({"type": "restart_game"})
            msg = self._drain_until(ws, "game_state")

        assert msg["state"]["phase"] in ("drawing", "discarding", "claiming")
        assert room.status == "playing"

    def test_restart_game_before_end_returns_error(self, client):
        """Sending restart_game while game is still active returns an error."""
        pid = "restart_early"
        room_id = _create_and_start(client, pid)

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            self._drain_until(ws, "game_state")
            ws.send_json({"type": "restart_game"})
            msg = self._drain_until(ws, "error")

        assert msg["type"] == "error"

    def test_restart_preserves_human_players(self, client):
        """After restart, the same human player occupies the same seat."""
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../backend'))
        from api.routes import room_manager

        pid = "restart_human"
        room_id = _create_and_start(client, pid)

        room = room_manager.get_room(room_id)
        room.game_state.phase = "ended"
        room.status = "ended"

        with client.websocket_connect(f"/ws/{room_id}/{pid}") as ws:
            self._drain_until(ws, "game_state")
            ws.send_json({"type": "restart_game"})
            msg = self._drain_until(ws, "game_state")

        players = msg["state"]["players"]
        human_ids = [p["id"] for p in players if not p.get("is_ai", True)]
        assert pid in human_ids
