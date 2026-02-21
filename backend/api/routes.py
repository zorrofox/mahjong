"""
routes.py - REST API endpoints for the Mahjong game.

Endpoints:
  GET  /api/rooms                  - List all rooms
  POST /api/rooms                  - Create a new room
  POST /api/rooms/{room_id}/join   - Join an existing room
  POST /api/rooms/{room_id}/start  - Start the game (deals tiles, fills AI seats)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from game.room_manager import RoomManager

router = APIRouter()

# ---------------------------------------------------------------------------
# Shared singleton – imported by websocket.py as well
# ---------------------------------------------------------------------------
room_manager = RoomManager()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class CreateRoomRequest(BaseModel):
    name: Optional[str] = None


class JoinRoomRequest(BaseModel):
    player_id: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/rooms")
def list_rooms():
    """Return a list of all rooms with summary information."""
    rooms = room_manager.get_rooms()
    return [r.to_dict() for r in rooms]


@router.post("/rooms", status_code=201)
def create_room(body: CreateRoomRequest = CreateRoomRequest()):
    """Create a new room and return its info."""
    room = room_manager.create_room(name=body.name)
    return room.to_dict()


@router.post("/rooms/{room_id}/join")
def join_room(room_id: str, body: JoinRoomRequest):
    """
    Join an existing room.

    If the room is full the player is automatically redirected to a new room.
    Returns the room the player actually joined.
    """
    try:
        room, was_redirected = room_manager.join_room(room_id, body.player_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    # Determine the player's seat index
    player_idx = room.human_players.index(body.player_id)

    return {
        "room_id": room.id,
        "player_idx": player_idx,
        "was_redirected": was_redirected,
        "room": room.to_dict(),
    }


@router.post("/rooms/{room_id}/start")
def start_game(room_id: str):
    """
    Start the game for the given room.

    Empty seats are filled with AI players and initial tiles are dealt.
    """
    room = room_manager.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail=f"Room '{room_id}' not found.")

    try:
        game_state = room_manager.start_game(room_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "room_id": room_id,
        "status": room.status,
        "players": [
            {"index": i, "id": p.id, "is_ai": p.is_ai}
            for i, p in enumerate(game_state.players)
        ],
    }
