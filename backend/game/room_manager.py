"""
room_manager.py - Manages Mahjong game rooms and player assignments.

A Room holds up to 4 human players. When a room is full, joining players
are redirected to a new room automatically. AI players fill empty seats
when the game starts.
"""

from __future__ import annotations

import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .game_state import GameState

logger = logging.getLogger(__name__)

MAX_PLAYERS = 4

# Starting chip balance for every player slot in a new room session
INITIAL_CHIPS = 1000


@dataclass
class Room:
    """Represents a game room."""

    id: str
    name: str
    human_players: list[str] = field(default_factory=list)  # player IDs (insertion order)
    game_state: Optional[GameState] = None
    status: str = "waiting"  # "waiting" | "playing" | "ended"
    created_at: datetime = field(default_factory=datetime.utcnow)
    # Cumulative chip balances across all rounds played in this room.
    # Keyed by player_id; values start at INITIAL_CHIPS and are updated after each game.
    cumulative_scores: dict = field(default_factory=dict)
    round_number: int = 0  # how many games have been completed (or started) in this room
    dealer_idx: int = 0    # seat index of the current dealer; rotates after each hand
    round_wind_idx: int = 0   # prevailing wind: 0=East, 1=South, 2=West, 3=North
    dealer_advances: int = 0  # total dealer changes; every 4 advances = one wind round

    @property
    def player_count(self) -> int:
        return len(self.human_players)

    @property
    def is_full(self) -> bool:
        return len(self.human_players) >= MAX_PLAYERS

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "player_count": self.player_count,
            "status": self.status,
            "max_players": MAX_PLAYERS,
            "created_at": self.created_at.isoformat(),
        }


class RoomManager:
    """
    Singleton-friendly manager for all game rooms.

    Thread safety: This implementation is designed for use with asyncio
    (single-threaded event loop), so no locking is applied.
    """

    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}

    # ------------------------------------------------------------------
    # Room lifecycle
    # ------------------------------------------------------------------

    def create_room(self, name: Optional[str] = None) -> Room:
        """
        Create a new room with a unique ID.

        Args:
            name: Optional display name for the room. Defaults to "Room <short-id>".

        Returns:
            The newly created Room.
        """
        room_id = str(uuid.uuid4())
        if name is None:
            name = f"Room {room_id[:8]}"
        room = Room(id=room_id, name=name)
        self._rooms[room_id] = room
        logger.info("Room created: id=%s name=%s", room_id, name)
        return room

    def get_room(self, room_id: str) -> Optional[Room]:
        """Return the room with the given ID, or None if not found."""
        return self._rooms.get(room_id)

    def get_rooms(self) -> list[Room]:
        """Return all rooms in creation order."""
        return list(self._rooms.values())

    # ------------------------------------------------------------------
    # Player management
    # ------------------------------------------------------------------

    def join_room(self, room_id: str, player_id: str) -> tuple[Room, bool]:
        """
        Add a player to the specified room.

        If the room is full (4 human players), a new room is created
        and the player joins that instead.

        Args:
            room_id:   Target room ID.
            player_id: The joining player's ID.

        Returns:
            (room, was_redirected) where was_redirected is True if the
            player ended up in a different room than requested.

        Raises:
            KeyError: If room_id does not exist.
        """
        room = self._rooms.get(room_id)
        if room is None:
            raise KeyError(f"Room '{room_id}' does not exist.")

        was_redirected = False

        # If the player is already in this room, return immediately.
        if player_id in room.human_players:
            return room, False

        # If the room is full, create a new room and join that.
        if room.is_full:
            room = self.create_room()
            was_redirected = True
            logger.info(
                "Room %s full; player %s redirected to new room %s",
                room_id, player_id, room.id,
            )

        room.human_players.append(player_id)
        logger.info("Player %s joined room %s", player_id, room.id)
        return room, was_redirected

    def remove_player(self, room_id: str, player_id: str) -> None:
        """
        Remove a player from a room.

        If the game is in progress the player's slot is left in the
        human_players list so their index remains stable; callers are
        responsible for switching that seat to AI control.

        Args:
            room_id:   The room ID.
            player_id: The player to remove.
        """
        room = self._rooms.get(room_id)
        if room is None:
            return
        if player_id in room.human_players:
            if room.status == "waiting":
                room.human_players.remove(player_id)
                logger.info("Player %s removed from waiting room %s", player_id, room_id)
            else:
                # During a game, keep the slot so player index stays stable.
                # Callers handle marking the seat as AI-controlled.
                logger.info(
                    "Player %s disconnected from active room %s (slot kept)", player_id, room_id
                )

    # ------------------------------------------------------------------
    # Game lifecycle
    # ------------------------------------------------------------------

    def start_game(self, room_id: str) -> GameState:
        """
        Start the game for a room.

        Empty seats (up to 4) are filled with AI players whose IDs follow
        the pattern ``ai_player_<N>`` where N is the seat index (0-based).
        A GameState is created with all 4 player IDs, initial tiles are
        dealt, and the room status is set to "playing".

        Args:
            room_id: The room to start.

        Returns:
            The newly created GameState.

        Raises:
            KeyError:    If the room does not exist.
            ValueError:  If the game has already started.
        """
        room = self._rooms.get(room_id)
        if room is None:
            raise KeyError(f"Room '{room_id}' does not exist.")
        if room.status == "ended":
            # Allow restarting a finished game with the same human players.
            room.status = "waiting"
        if room.status != "waiting":
            raise ValueError(f"Room '{room_id}' is not in waiting status (status={room.status}).")

        # Build the full 4-player list, filling empty seats with AI IDs.
        player_ids: list[str] = []
        for seat_idx in range(MAX_PLAYERS):
            if seat_idx < len(room.human_players):
                player_ids.append(room.human_players[seat_idx])
            else:
                player_ids.append(f"ai_player_{seat_idx}")

        game_state = GameState(
            room_id=room_id,
            player_ids=player_ids,
            dealer_idx=room.dealer_idx,
            round_wind_idx=room.round_wind_idx,
        )

        # Mark AI players
        for i, pid in enumerate(player_ids):
            if pid.startswith("ai_player_"):
                game_state.players[i].is_ai = True

        game_state.deal_initial_tiles()

        room.game_state = game_state
        room.status = "playing"
        room.round_number += 1

        # Initialise cumulative chip balance for any player not yet tracked.
        # Existing balances are kept intact (cross-game persistence).
        for pid in player_ids:
            room.cumulative_scores.setdefault(pid, INITIAL_CHIPS)

        logger.info(
            "Game started: room=%s players=%s round=%d", room_id, player_ids, room.round_number
        )
        return game_state
