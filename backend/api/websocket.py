"""
websocket.py - WebSocket endpoint for real-time Mahjong gameplay.

Endpoint:
  WS /ws/{room_id}/{player_id}

Client → Server messages:
  {"type": "discard",    "tile": "<TILE>"}
  {"type": "pung"}
  {"type": "chow",       "tiles": ["<T1>", "<T2>"]}
  {"type": "kong",       "tile": "<TILE>"}   # tile for self-kong; omit for claimed kong
  {"type": "win"}
  {"type": "skip"}
  {"type": "start_game"}

Server → Client messages:
  {"type": "game_state",     "state": {...}}
  {"type": "action_required","player_idx": N, "actions": [...]}
  {"type": "claim_window",   "tile": "<TILE>", "actions": [...]}
  {"type": "game_over",      "winner_idx": N, "winner_id": "...", "scores": {...}}
  {"type": "error",          "message": "..."}
  {"type": "room_update",    "rooms": [...]}
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from game.game_state import GameState
from game.ai_player import AIPlayer
from game.room_manager import Room, INITIAL_CHIPS
# Import the singleton room_manager from routes
from api.routes import room_manager

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Connection registry
# {room_id: {player_id: WebSocket}}
# ---------------------------------------------------------------------------
_connections: dict[str, dict[str, WebSocket]] = {}

# Tracks rooms that currently have a running _handle_claim_window coroutine.
# Used by the skip handler to avoid starting a duplicate handler.
_claim_window_active: set[str] = set()

# Shared AI instance (stateless heuristics; safe to reuse)
_ai = AIPlayer()

# Claim-window timeout in seconds (shown as countdown in the UI)
CLAIM_TIMEOUT = 30.0

# Maximum chip unit per hand (caps at 64 = 7 fan). Each fan doubles the unit:
# 1 fan → 1 chip, 2 → 2, 3 → 4, 4 → 8, 5 → 16, 6 → 32, 7+ → 64.
CHIP_CAP = 64

# AI action delay range (seconds) – makes AI feel natural
AI_DELAY_MIN = 0.2
AI_DELAY_MAX = 0.6


# ---------------------------------------------------------------------------
# Helper: send / broadcast utilities
# ---------------------------------------------------------------------------

async def _send(ws: WebSocket, payload: dict) -> None:
    """Send a JSON payload to a single WebSocket, ignoring closed connections."""
    try:
        await ws.send_json(payload)
    except Exception:
        pass  # Connection may already be closed


async def _broadcast(room_id: str, payload: dict, exclude: Optional[str] = None) -> None:
    """Broadcast a payload to all connected players in a room."""
    room_conns = _connections.get(room_id, {})
    for pid, ws in list(room_conns.items()):
        if pid == exclude:
            continue
        await _send(ws, payload)


async def _broadcast_game_state(room_id: str) -> None:
    """
    Send each connected player their personalised view of the game state.
    Other players' hands are hidden.
    """
    room = room_manager.get_room(room_id)
    if room is None or room.game_state is None:
        return

    gs = room.game_state
    room_conns = _connections.get(room_id, {})

    for pid, ws in list(room_conns.items()):
        player_idx = _player_index(gs, pid)
        state_dict = gs.to_dict(viewing_player_idx=player_idx)
        state_dict["cumulative_scores"] = dict(room.cumulative_scores)
        state_dict["round_number"] = room.round_number
        await _send(ws, {"type": "game_state", "state": state_dict})


async def _broadcast_room_update() -> None:
    """Notify all connected clients in every room about room list changes."""
    rooms_payload = [r.to_dict() for r in room_manager.get_rooms()]
    for room_id, room_conns in _connections.items():
        for ws in list(room_conns.values()):
            await _send(ws, {"type": "room_update", "rooms": rooms_payload})


async def _send_action_required(room_id: str, player_idx: int) -> None:
    """Tell the current player what actions are available to them."""
    room = room_manager.get_room(room_id)
    if room is None or room.game_state is None:
        return

    gs = room.game_state
    player = gs.players[player_idx]
    actions = gs.get_available_actions(player_idx)

    ws = _connections.get(room_id, {}).get(player.id)
    if ws:
        msg: dict = {
            "type": "action_required",
            "player_idx": player_idx,
            "actions": actions,
        }
        # Include the most recently drawn tile so the frontend can pre-select it.
        if gs.last_drawn_tile and "discard" in actions:
            msg["drawn_tile"] = gs.last_drawn_tile
        await _send(ws, msg)


async def _send_claim_window(room_id: str, tile: str) -> None:
    """
    Send a claim_window message to every non-discarder in the room,
    listing the actions available to each individual player.
    """
    room = room_manager.get_room(room_id)
    if room is None or room.game_state is None:
        return

    gs = room.game_state
    discarder_idx = gs.last_discard_player

    for i, player in enumerate(gs.players):
        if i == discarder_idx:
            continue
        actions = gs.get_available_actions(i)
        # Don't send claim_window to players with nothing to do
        if not actions:
            continue
        ws = _connections.get(room_id, {}).get(player.id)
        if ws:
            await _send(ws, {
                "type": "claim_window",
                "tile": tile,
                "actions": actions,
                "timeout": int(CLAIM_TIMEOUT),
            })


# ---------------------------------------------------------------------------
# Helper: look up player index by player_id
# ---------------------------------------------------------------------------

def _player_index(gs: GameState, player_id: str) -> Optional[int]:
    for i, p in enumerate(gs.players):
        if p.id == player_id:
            return i
    return None


# ---------------------------------------------------------------------------
# AI automation
# ---------------------------------------------------------------------------

async def _run_ai_turn(room_id: str) -> None:
    """
    Drive AI actions until it is a human player's turn (or the game ends).

    Called after any state-changing action so that a chain of AI turns
    can proceed automatically.
    """
    room = room_manager.get_room(room_id)
    if room is None or room.game_state is None:
        return

    gs = room.game_state

    # Safety: keep looping while it is an AI player's turn
    while True:
        if gs.phase == "ended":
            await _handle_game_over(room_id)
            return

        if gs.phase in ("drawing", "discarding"):
            current_player = gs.players[gs.current_turn]
            if not current_player.is_ai:
                # Auto-draw for human player (no manual draw button in UI),
                # then send action_required so they can discard / win / kong.
                if gs.phase == "drawing":
                    try:
                        drawn = gs.draw_tile(gs.current_turn)
                    except ValueError as e:
                        logger.warning("Human auto-draw failed: %s", e)
                        return
                    await _broadcast_game_state(room_id)
                    if gs.phase == "ended":
                        await _handle_game_over(room_id)
                        return
                await _send_action_required(room_id, gs.current_turn)
                return

            # --- AI draw phase ---
            if gs.phase == "drawing":
                await asyncio.sleep(random.uniform(AI_DELAY_MIN, AI_DELAY_MAX))
                try:
                    gs.draw_tile(gs.current_turn)
                except ValueError as e:
                    logger.warning("AI draw failed: %s", e)
                    return
                await _broadcast_game_state(room_id)

                if gs.phase == "ended":
                    await _handle_game_over(room_id)
                    return

            # --- AI discard phase ---
            if gs.phase == "discarding":
                await asyncio.sleep(random.uniform(AI_DELAY_MIN, AI_DELAY_MAX))
                ai_idx = gs.current_turn
                player = gs.players[ai_idx]

                # Check self-draw win
                if _ai.should_declare_win(player.hand_without_bonus(), player.melds):
                    try:
                        result = gs.declare_win(ai_idx)
                        await _broadcast_game_state(room_id)
                        await _handle_game_over(room_id)
                        return
                    except ValueError:
                        pass

                # Check self-drawn kong (concealed 暗杠 or extend-pung 加杠)
                from collections import Counter
                counts = Counter(player.hand_without_bonus())
                # Prefer concealed kong (4-of-a-kind in hand) first
                kong_tile = next((t for t, c in counts.items() if c >= 4), None)
                # Fall back to extend-pung (1 copy in hand matching a pung meld)
                if not kong_tile:
                    pung_tiles = {m[0] for m in player.melds
                                  if len(m) == 3 and m[0] == m[1] == m[2]}
                    kong_tile = next((t for t in pung_tiles if counts.get(t, 0) >= 1), None)
                if kong_tile:
                    try:
                        gs.claim_kong(ai_idx, kong_tile)
                        await _broadcast_game_state(room_id)
                        if gs.phase == "ended":
                            await _handle_game_over(room_id)
                            return
                        if gs.phase == "claiming":
                            # Extend-pung opened a rob-kong window
                            if room_id not in _claim_window_active:
                                asyncio.create_task(_handle_claim_window(room_id))
                            return
                        continue  # concealed kong: loop again to discard
                    except ValueError:
                        pass

                # Discard
                tile_to_discard = _ai.choose_discard(player.hand_without_bonus(), player.melds)
                try:
                    gs.discard_tile(ai_idx, tile_to_discard)
                except ValueError as e:
                    logger.warning("AI discard failed: %s", e)
                    return

                await _broadcast_game_state(room_id)

                if gs.phase == "ended":
                    await _handle_game_over(room_id)
                    return

                # After an AI discard, handle the claim window
                if gs.phase == "claiming":
                    await _handle_claim_window(room_id)
                    return  # _handle_claim_window will resume the loop
                # If no claim window (shouldn't normally happen), continue
                continue

        elif gs.phase == "claiming":
            # Claim window: handled by _handle_claim_window
            return

        else:
            return


async def _handle_claim_window(room_id: str) -> None:
    """
    Manage the claim window after a discard.

    1. Broadcast claim_window to all eligible players.
    2. AI players decide immediately (no delay needed for claim decisions).
    3. Human players have CLAIM_TIMEOUT seconds to respond.
    4. After all have responded (or timeout), the game state resolves.
    5. Resume AI automation if needed.
    """
    room = room_manager.get_room(room_id)
    if room is None or room.game_state is None:
        return

    gs = room.game_state
    if gs.phase != "claiming":
        return

    _claim_window_active.add(room_id)
    try:
        tile = gs.last_discard
        discarder_idx = gs.last_discard_player

        # Auto-skip humans who have no real choice (only "skip" available).
        # This avoids the full CLAIM_TIMEOUT wait for unclaimable tiles.
        for i, player in enumerate(gs.players):
            if i == discarder_idx or player.is_ai:
                continue
            if gs.phase != "claiming" or i not in gs._pending_claims:
                continue
            available = gs.get_available_actions(i)
            if set(available) <= {"skip"}:
                try:
                    gs.skip_claim(i)
                except ValueError:
                    pass

        # Broadcast claim window only to humans who still have a real choice
        if gs.phase == "claiming":
            await _send_claim_window(room_id, tile)

        # Collect AI claim decisions and introduce a simulated human delay
        ai_decisions = []
        for i, player in enumerate(gs.players):
            if i == discarder_idx or not player.is_ai:
                continue
            if gs.phase != "claiming" or i not in gs._pending_claims:
                continue

            available = gs.get_available_actions(i)

            if "win" in available and _ai.decide_claim(player.hand_without_bonus(), player.melds, tile, "win"):
                ai_decisions.append((i, "win", None))
                continue

            if "kong" in available and _ai.decide_claim(player.hand_without_bonus(), player.melds, tile, "kong"):
                ai_decisions.append((i, "kong", tile))
                continue

            if "pung" in available and _ai.decide_claim(player.hand_without_bonus(), player.melds, tile, "pung"):
                ai_decisions.append((i, "pung", None))
                continue

            if "chow" in available and _ai.decide_claim(player.hand_without_bonus(), player.melds, tile, "chow"):
                from game.hand import can_chow
                possible_chows = can_chow(player.hand_without_bonus(), tile)
                if possible_chows:
                    best_chow = possible_chows[0]
                    hand_tiles = [t for t in best_chow if t != tile]
                    ai_decisions.append((i, "chow", hand_tiles))
                    continue

            ai_decisions.append((i, "skip", None))

        # Add random delay to simulate human reaction time for claims
        if any(d[1] != "skip" for d in ai_decisions):
            await asyncio.sleep(random.uniform(1.2, 2.5))
        elif ai_decisions:
            # Slight delay even if all AI just skip, to avoid instantaneous closing
            await asyncio.sleep(random.uniform(0.3, 0.8))

        # Now apply the AI decisions
        for i, action, data in ai_decisions:
            if gs.phase != "claiming" or i not in gs._pending_claims:
                continue
            try:
                if action == "win":
                    gs.declare_win(i)
                    break # A win resolves or short-circuits further lower priority claims
                elif action == "kong": gs.claim_kong(i, data)
                elif action == "pung": gs.claim_pung(i)
                elif action == "chow": gs.claim_chow(i, data)
                elif action == "skip": gs.skip_claim(i)
            except ValueError:
                pass

        # If a win was claimed during the AI processing loop, skip all remaining pending
        # claims immediately.  Without this, the loop breaks early (after the winning AI's
        # declare_win) leaving other players in _pending_claims, causing the code below
        # to wait the full CLAIM_TIMEOUT (~30 s) before the window resolves.
        if gs.phase == "claiming" and gs._best_claim is not None and gs._best_claim.get("type") == "win":
            for _i in list(gs._pending_claims):
                if _i not in gs._skipped_claims:
                    try:
                        gs.skip_claim(_i)
                    except ValueError:
                        pass

        # If the claim window is still open, wait for human responses with a timeout
        if gs.phase == "claiming":
            try:
                await asyncio.wait_for(_wait_for_claim_window(room_id), timeout=CLAIM_TIMEOUT)
            except asyncio.TimeoutError:
                # Force-skip ALL remaining pending claims (human or temporarily-AI-marked).
                # Skipping only "not is_ai" players would miss players who disconnected
                # mid-window and were temporarily marked as AI, leaving the window stuck.
                if gs.phase == "claiming":
                    for i in list(gs._pending_claims):
                        if i not in gs._skipped_claims:
                            try:
                                gs.skip_claim(i)
                            except ValueError:
                                pass

        # Safety net: if claim window is still open after all handling, force-resolve.
        # This guards against unexpected states (e.g. all pending players were AI-marked).
        if gs.phase == "claiming":
            logger.warning(
                "Claim window still open after handling in room %s; force-resolving.", room_id
            )
            for i in list(gs._pending_claims):
                if i not in gs._skipped_claims:
                    try:
                        gs.skip_claim(i)
                    except ValueError:
                        pass
    finally:
        # Always clear the active flag so future claim windows can be handled.
        _claim_window_active.discard(room_id)

    # Broadcast updated state after resolution
    await _broadcast_game_state(room_id)

    if gs.phase == "ended":
        await _handle_game_over(room_id)
        return

    if gs.phase == "claiming":
        # Still stuck after all attempts — log and bail to avoid infinite loop.
        logger.error(
            "Claim window could not be resolved in room %s; giving up.", room_id
        )
        return

    # Continue AI automation for the next player's turn
    asyncio.create_task(_run_ai_turn(room_id))


async def _wait_for_claim_window(room_id: str) -> None:
    """Busy-wait (polling) until the claim window closes."""
    while True:
        room = room_manager.get_room(room_id)
        if room is None or room.game_state is None:
            return
        if room.game_state.phase != "claiming":
            return
        await asyncio.sleep(0.1)


async def _handle_game_over(room_id: str) -> None:
    """Broadcast game_over, settle chips, and update room status."""
    room = room_manager.get_room(room_id)
    if room is None or room.game_state is None:
        return

    # Idempotency guard: when a human wins in a claim window, both the win
    # handler and _handle_claim_window detect phase=="ended" and call this
    # function.  The first call must complete chip settlement and broadcast;
    # the second call must be a no-op to avoid double-settling chips.
    if room.status == "ended":
        return

    gs = room.game_state
    room.status = "ended"

    winner_id = gs.winner
    winner_idx = None
    scores = {}
    for i, p in enumerate(gs.players):
        scores[p.id] = p.score
        if p.id == winner_id:
            winner_idx = i

    # ----------------------------------------------------------------
    # Dealer rotation
    # ----------------------------------------------------------------
    # Dealer (庄家) keeps their seat if they win; otherwise passes to the
    # next seat clockwise.  A draw (no winner) also advances the dealer.
    if winner_idx is not None and winner_idx == gs.dealer_idx:
        pass  # dealer wins — 连庄, no rotation
    else:
        room.dealer_idx = (gs.dealer_idx + 1) % len(gs.players)  # 换庄
        room.dealer_advances += 1
        # Every 4 dealer changes complete one wind round (East→South→West→North)
        if room.dealer_advances % 4 == 0:
            room.round_wind_idx = (room.round_wind_idx + 1) % 4

    # ----------------------------------------------------------------
    # Chip settlement — Han-based, zero-sum
    # ----------------------------------------------------------------
    # unit = min(CHIP_CAP, 2^(han_total-1))  →  1 fan=1, 2=2, 3=4 … 7+=64
    #
    # Dealer (player 0 / gs.dealer_idx) always pays/receives 2× unit;
    # non-dealers pay/receive 1× unit.
    #
    # Self-draw (自摸):
    #   Non-dealer wins: dealer pays 2×unit, each non-dealer pays 1×unit  → winner +4×unit
    #   Dealer wins:     each non-dealer pays 2×unit                       → winner +6×unit
    #
    # Ron (荣和, discard win):
    #   Discarder pays the combined tsumo amount (sum of what all losers would owe).
    #   Non-dealer wins: 2+1+1 = 4×unit from discarder
    #   Dealer wins:     2+2+2 = 6×unit from discarder
    #
    # Kong payments (杠钱):
    #   Each kong declaration costs each non-konger 1 chip immediately.
    #   Accumulated in gs.kong_chip_transfers; applied first below.
    #
    # Draw (流局): no chip transfer.
    # ----------------------------------------------------------------

    # 1. Apply accumulated kong chip transfers
    for pid, delta in gs.kong_chip_transfers.items():
        room.cumulative_scores[pid] = (
            room.cumulative_scores.get(pid, INITIAL_CHIPS) + delta
        )

    # 2. Han-based win payment
    if winner_idx is not None and gs.han_total > 0:
        unit = min(CHIP_CAP, 2 ** (gs.han_total - 1))
        dealer_idx = gs.dealer_idx

        def _pay(payer_idx: int) -> int:
            """Chips that payer_idx owes in a tsumo scenario for this winner.

            Rule:
              - Dealer wins   → every non-dealer loser pays 2×unit.
              - Non-dealer wins → dealer pays 2×unit; each non-dealer pays 1×unit.

            Note: when the dealer wins, winner_idx == dealer_idx, so dealer_idx is
            excluded from the summation; all remaining payers are non-dealers and
            each pays 2×unit (giving 3×2u = 6u total to the dealer winner).
            """
            if winner_idx == dealer_idx:
                # Dealer wins: every loser (all non-dealer) pays double
                return 2 * unit
            # Non-dealer wins: dealer pays double, other non-dealers pay single
            return 2 * unit if payer_idx == dealer_idx else unit

        if gs.win_ron and gs.win_discarder_idx is not None:
            # Ron: discarder alone pays the combined tsumo total.
            # Non-dealer win: 2u + u + u = 4u   Dealer win: 2u + 2u + 2u = 6u
            full = sum(
                _pay(i) for i in range(len(gs.players)) if i != winner_idx
            )
            discarder_id = gs.players[gs.win_discarder_idx].id
            room.cumulative_scores[winner_id] = (
                room.cumulative_scores.get(winner_id, INITIAL_CHIPS) + full
            )
            room.cumulative_scores[discarder_id] = (
                room.cumulative_scores.get(discarder_id, INITIAL_CHIPS) - full
            )
        elif gs.win_ron is False:
            # Tsumo: each loser pays their individual share
            for i, p in enumerate(gs.players):
                if i != winner_idx:
                    pay = _pay(i)
                    room.cumulative_scores[winner_id] = (
                        room.cumulative_scores.get(winner_id, INITIAL_CHIPS) + pay
                    )
                    room.cumulative_scores[p.id] = (
                        room.cumulative_scores.get(p.id, INITIAL_CHIPS) - pay
                    )

    payload = {
        "type": "game_over",
        "winner_idx": winner_idx,
        "winner_id": winner_id,
        "scores": scores,
        "cumulative_scores": dict(room.cumulative_scores),
        "round_number": room.round_number,
        "han_breakdown": gs.han_breakdown if gs else [],
        "han_total": gs.han_total if gs else 0,
        "next_dealer_idx": room.dealer_idx,  # already updated by dealer-rotation logic above
    }
    await _broadcast(room_id, payload)
    await _broadcast_room_update()


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@router.websocket("/ws/{room_id}/{player_id}")
async def websocket_endpoint(ws: WebSocket, room_id: str, player_id: str):
    await ws.accept()

    # Register connection
    if room_id not in _connections:
        _connections[room_id] = {}
    _connections[room_id][player_id] = ws

    logger.info("WS connected: room=%s player=%s", room_id, player_id)

    # Send current game state if a game is already running
    room = room_manager.get_room(room_id)
    if room and room.game_state:
        gs = room.game_state
        player_idx = _player_index(gs, player_id)

        # Restore human control when a player reconnects after disconnect.
        # On disconnect the finally block sets is_ai=True so the AI can fill
        # in; here we reverse that for the real human player (identified by
        # a non-AI player_id, i.e. not "ai_player_1/2/3").
        if player_idx is not None and not player_id.startswith("ai_player_"):
            if gs.players[player_idx].is_ai:
                gs.players[player_idx].is_ai = False
                logger.info(
                    "Player %s reconnected; seat %d restored to human control",
                    player_id, player_idx,
                )

        # New human player joining a game already in progress: assign them to
        # an available AI seat so they can actually play instead of spectating.
        # This allows multiple human players to join at different times —
        # each takes over the next available AI-controlled seat.
        if player_idx is None and not player_id.startswith("ai_player_") and room.status == "playing":
            for i, p in enumerate(gs.players):
                if p.is_ai and p.id.startswith("ai_player_"):
                    p.id = player_id
                    p.is_ai = False
                    player_idx = i
                    if player_id not in room.human_players:
                        room.human_players.append(player_id)
                    logger.info(
                        "Player %s joined in-progress game; took over AI seat %d",
                        player_id, i,
                    )
                    break

        state_dict = gs.to_dict(viewing_player_idx=player_idx)
        await _send(ws, {"type": "game_state", "state": state_dict})

        if gs.phase != "ended":
            if gs.current_turn is not None:
                current = gs.players[gs.current_turn]
                if current.id == player_id:
                    # If reconnecting mid-draw, auto-draw before prompting
                    if gs.phase == "drawing":
                        asyncio.create_task(_run_ai_turn(room_id))
                    else:
                        await _send_action_required(room_id, gs.current_turn)
                elif gs.phase == "claiming":
                    if player_idx is not None and player_idx in gs._pending_claims:
                        actions = gs.get_available_actions(player_idx)
                        await _send(ws, {
                            "type": "claim_window",
                            "tile": gs.last_discard,
                            "actions": actions,
                        })

    await _broadcast_room_update()

    try:
        while True:
            data = await ws.receive_json()
            await _handle_message(room_id, player_id, ws, data)
    except WebSocketDisconnect:
        logger.info("WS disconnected: room=%s player=%s", room_id, player_id)
    except Exception as e:
        logger.exception("WS error: room=%s player=%s error=%s", room_id, player_id, e)
    finally:
        # Unregister
        if room_id in _connections:
            _connections[room_id].pop(player_id, None)
            if not _connections[room_id]:
                del _connections[room_id]

        # If game in progress, mark the player's seat as AI-controlled
        room = room_manager.get_room(room_id)
        if room and room.game_state and room.status == "playing":
            gs = room.game_state
            pidx = _player_index(gs, player_id)
            if pidx is not None:
                gs.players[pidx].is_ai = True
                logger.info(
                    "Player %s disconnected mid-game; seat %d is now AI-controlled",
                    player_id, pidx,
                )
                # If it was this player's turn, continue with AI
                if gs.phase != "ended":
                    asyncio.create_task(_run_ai_turn(room_id))

        await _broadcast_room_update()


# ---------------------------------------------------------------------------
# Message dispatcher
# ---------------------------------------------------------------------------

async def _handle_message(
    room_id: str, player_id: str, ws: WebSocket, data: dict
) -> None:
    msg_type = data.get("type")

    room = room_manager.get_room(room_id)
    if room is None:
        await _send(ws, {"type": "error", "message": "Room not found."})
        return

    # ---- start_game -------------------------------------------------------
    if msg_type == "start_game":
        if room.status != "waiting":
            await _send(ws, {"type": "error", "message": "Game already started."})
            return
        try:
            room_manager.start_game(room_id)
        except Exception as e:
            await _send(ws, {"type": "error", "message": str(e)})
            return

        await _broadcast_game_state(room_id)
        await _broadcast_room_update()

        gs = room.game_state
        # If the current player (dealer) is AI, kick off AI turns
        if gs.players[gs.current_turn].is_ai:
            asyncio.create_task(_run_ai_turn(room_id))
        else:
            await _send_action_required(room_id, gs.current_turn)
        return

    # ---- restart_game -----------------------------------------------------
    if msg_type == "restart_game":
        if room.status != "ended":
            await _send(ws, {"type": "error", "message": "Game has not ended yet."})
            return
        try:
            room_manager.start_game(room_id)  # resets status "ended"→"waiting"→"playing"
        except Exception as e:
            await _send(ws, {"type": "error", "message": str(e)})
            return

        await _broadcast_game_state(room_id)
        await _broadcast_room_update()

        gs = room.game_state
        if gs.players[gs.current_turn].is_ai:
            asyncio.create_task(_run_ai_turn(room_id))
        else:
            await _send_action_required(room_id, gs.current_turn)
        return

    # All subsequent messages require an active game
    if room.game_state is None or room.status != "playing":
        await _send(ws, {"type": "error", "message": "Game is not active."})
        return

    gs = room.game_state
    player_idx = _player_index(gs, player_id)

    if player_idx is None:
        await _send(ws, {"type": "error", "message": "Player not found in game."})
        return

    # ---- discard ----------------------------------------------------------
    if msg_type == "discard":
        tile = data.get("tile")
        if not tile:
            await _send(ws, {"type": "error", "message": "Missing 'tile' field."})
            return
        try:
            gs.discard_tile(player_idx, tile)
        except ValueError as e:
            await _send(ws, {"type": "error", "message": str(e)})
            return

        await _broadcast_game_state(room_id)

        if gs.phase == "ended":
            await _handle_game_over(room_id)
            return

        if gs.phase == "claiming":
            asyncio.create_task(_handle_claim_window(room_id))
        return

    # ---- win --------------------------------------------------------------
    if msg_type == "win":
        try:
            gs.declare_win(player_idx)
        except ValueError as e:
            await _send(ws, {"type": "error", "message": str(e)})
            return

        # If the win is recorded in a claim window but other human players still
        # have pending claims (e.g. they had a pung option and haven't responded),
        # force-skip them immediately.  Win has the highest priority — there is no
        # reason to wait for other players to pung/chow/skip before resolving the
        # window.  Without this, the game stalls for CLAIM_TIMEOUT (~30 s) when
        # multiple humans share a claim window and one of them wins.
        # (The same force-skip already exists for AI wins in _handle_claim_window.)
        if gs.phase == "claiming" and gs._best_claim and gs._best_claim.get("type") == "win":
            for i in list(gs._pending_claims):
                if i not in gs._skipped_claims:
                    try:
                        gs.skip_claim(i)
                    except ValueError:
                        pass

        await _broadcast_game_state(room_id)

        if gs.phase == "ended":
            await _handle_game_over(room_id)
        return

    # ---- pung -------------------------------------------------------------
    if msg_type == "pung":
        if gs.phase != "claiming":
            await _send(ws, {"type": "error", "message": "Not in claiming phase."})
            return
        try:
            success = gs.claim_pung(player_idx)
        except ValueError as e:
            await _send(ws, {"type": "error", "message": str(e)})
            return

        if not success:
            await _send(ws, {"type": "error", "message": "Cannot pung that tile."})
            return

        await _broadcast_game_state(room_id)

        if gs.phase == "ended":
            await _handle_game_over(room_id)
            return

        # If claim window closed, handle next turn
        if gs.phase != "claiming":
            asyncio.create_task(_run_ai_turn(room_id))
        return

    # ---- chow -------------------------------------------------------------
    if msg_type == "chow":
        tiles = data.get("tiles", [])
        if gs.phase != "claiming":
            await _send(ws, {"type": "error", "message": "Not in claiming phase."})
            return
        try:
            success = gs.claim_chow(player_idx, tiles)
        except ValueError as e:
            await _send(ws, {"type": "error", "message": str(e)})
            return

        if not success:
            await _send(ws, {"type": "error", "message": "Cannot chow with those tiles."})
            return

        await _broadcast_game_state(room_id)

        if gs.phase == "ended":
            await _handle_game_over(room_id)
            return

        if gs.phase != "claiming":
            asyncio.create_task(_run_ai_turn(room_id))
        return

    # ---- kong -------------------------------------------------------------
    if msg_type == "kong":
        tile = data.get("tile")
        try:
            if tile:
                # Self-kong (tile specified) or claimed kong
                gs.claim_kong(player_idx, tile)
            else:
                # Claimed kong: tile is the last discard
                if gs.phase != "claiming":
                    await _send(ws, {"type": "error", "message": "Not in claiming phase."})
                    return
                gs.claim_kong(player_idx, gs.last_discard)
        except ValueError as e:
            await _send(ws, {"type": "error", "message": str(e)})
            return

        await _broadcast_game_state(room_id)

        if gs.phase == "ended":
            await _handle_game_over(room_id)
            return

        if gs.phase == "claiming":
            # Extend-pung (加杠) opened a rob-kong window.
            # Without this, the window sits unhandled forever and the player
            # never receives action_required — "no actions after kong" bug.
            if room_id not in _claim_window_active:
                asyncio.create_task(_handle_claim_window(room_id))
        else:
            asyncio.create_task(_run_ai_turn(room_id))
        return

    # ---- skip -------------------------------------------------------------
    if msg_type == "skip":
        if gs.phase != "claiming":
            await _send(ws, {"type": "error", "message": "Not in claiming phase."})
            return
        try:
            gs.skip_claim(player_idx)
        except ValueError as e:
            await _send(ws, {"type": "error", "message": str(e)})
            return

        await _broadcast_game_state(room_id)

        if gs.phase == "ended":
            await _handle_game_over(room_id)
            return

        if gs.phase != "claiming":
            # Claim window resolved. If _handle_claim_window is still running it
            # will also create _run_ai_turn when _wait_for_claim_window wakes up;
            # only kick off our own task when no handler is active to avoid races.
            if room_id not in _claim_window_active:
                asyncio.create_task(_run_ai_turn(room_id))
        else:
            # Window still open (shouldn't happen in single-human play, but guard
            # against it: restart the handler if it's no longer active).
            if room_id not in _claim_window_active:
                asyncio.create_task(_handle_claim_window(room_id))
        return

    # ---- unknown ----------------------------------------------------------
    await _send(ws, {"type": "error", "message": f"Unknown message type: {msg_type!r}"})
