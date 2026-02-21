"""
game_state.py - Mahjong GameState and PlayerState classes.

Manages the complete game state for a 4-player Mahjong game, including:
  - Wall management (drawing/replacement tiles)
  - Player hands, melds, and discard piles
  - Turn and phase tracking
  - Claim window resolution (win > pung/kong > chow)
  - Win declaration and scoring
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from .tiles import build_deck, shuffle_deck, is_flower_tile, is_suit_tile, get_suit
from .hand import (
    is_winning_hand,
    can_pung,
    can_kong,
    can_chow,
    calculate_han,
)

logger = logging.getLogger(__name__)

# Number of players in a standard Mahjong game
NUM_PLAYERS = 4

# Initial tile counts
DEALER_INITIAL_TILES = 14
NON_DEALER_INITIAL_TILES = 13


@dataclass
class PlayerState:
    """Represents the state of a single player."""

    id: str
    hand: list[str] = field(default_factory=list)
    melds: list[list[str]] = field(default_factory=list)  # claimed/declared melds
    flowers: list[str] = field(default_factory=list)      # collected bonus tiles
    score: int = 0
    is_ai: bool = False
    claims_pending: bool = False  # True while player is in the claim window

    def hand_without_bonus(self) -> list[str]:
        """Return hand tiles excluding flower/season bonus tiles."""
        return [t for t in self.hand if not is_flower_tile(t)]

    def full_tile_count(self) -> int:
        """Total tiles in hand (including bonus tiles not yet collected)."""
        return len(self.hand)

    def effective_tile_count(self) -> int:
        """Hand tile count excluding bonus tiles."""
        return len(self.hand_without_bonus())


class GameState:
    """
    Manages the full state of an in-progress Mahjong game.

    Game phases:
      "drawing"   - Current player's turn to draw a tile.
      "discarding"- Current player has drawn and must discard.
      "claiming"  - A tile was discarded; other players may claim it.
      "ended"     - The game has finished (win or draw).

    Claim priority (highest to lowest):
      1. Win (ron/hu)
      2. Pung or Kong
      3. Chow (only from the left player, i.e., previous turn player)

    After a claim, the claiming player starts their turn and must discard.
    A kong gives the player a replacement tile from the back of the wall.
    """

    def __init__(self, room_id: str, player_ids: list[str]) -> None:
        if len(player_ids) != NUM_PLAYERS:
            raise ValueError(f"Mahjong requires exactly {NUM_PLAYERS} players.")

        self.room_id: str = room_id
        self.players: list[PlayerState] = [
            PlayerState(id=pid) for pid in player_ids
        ]

        # The wall; dealt from the front, kong replacements from the back.
        wall = build_deck()
        self.wall: list[str] = shuffle_deck(wall)

        # Per-player discard piles (index matches player index)
        self.discards: list[list[str]] = [[] for _ in range(NUM_PLAYERS)]

        # Turn management
        self.current_turn: int = 0           # Index of the player whose turn it is
        self.last_discard: Optional[str] = None
        self.last_discard_player: Optional[int] = None

        # Phase tracking
        self.phase: str = "drawing"

        # Claim window tracking: set of player indices who still need to respond
        self._pending_claims: set[int] = set()

        # Tracks players who have explicitly skipped in the current claim window
        self._skipped_claims: set[int] = set()

        # Highest claim submitted during the current window
        # Format: {"player_idx": int, "type": "win"|"pung"|"kong"|"chow", "tiles": list[str]}
        self._best_claim: Optional[dict] = None

        # Dealer index (player 0 is always dealer in current implementation)
        self.dealer_idx: int = 0

        # Game result
        self.winner: Optional[str] = None  # player id of the winner
        self.win_ron: Optional[bool] = None  # True = discard win, False = self-draw
        self.win_discarder_idx: Optional[int] = None  # index of the discarder for ron wins
        self.han_breakdown: list[dict] = []   # [{'name_cn','name_en','fan'}, ...]
        self.han_total: int = 0

        # Accumulated chip transfers from kong declarations during the hand.
        # Applied at game end alongside the win payment.
        # Keys are player_id strings; values are net chip deltas (can be negative).
        self.kong_chip_transfers: dict[str, int] = {}

        logger.info("GameState created: room=%s players=%s", room_id, player_ids)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _draw_from_front(self) -> Optional[str]:
        """Draw a tile from the front of the wall. Returns None if wall is empty."""
        if not self.wall:
            return None
        return self.wall.pop(0)

    def _draw_from_back(self) -> Optional[str]:
        """Draw a replacement tile from the back of the wall (for kongs)."""
        if not self.wall:
            return None
        return self.wall.pop(-1)

    def _collect_bonus_tiles(self, player_idx: int) -> list[str]:
        """
        Move any flower/season tiles from the player's hand to their flowers list.
        Each bonus tile collected is replaced by drawing from the back of the wall.

        Returns:
            List of bonus tiles that were collected.
        """
        collected: list[str] = []
        player = self.players[player_idx]
        # Keep replacing until no more bonus tiles remain
        while True:
            bonus = [t for t in player.hand if is_flower_tile(t)]
            if not bonus:
                break
            for tile in bonus:
                player.hand.remove(tile)
                player.flowers.append(tile)
                collected.append(tile)
                replacement = self._draw_from_back()
                if replacement is not None:
                    player.hand.append(replacement)
                else:
                    logger.warning("Wall exhausted while replacing bonus tile.")
        return collected

    def _claim_priority(self, claim_type: str) -> int:
        """Return numeric priority for a claim type (higher = more priority)."""
        return {"win": 3, "kong": 2, "pung": 2, "chow": 1}.get(claim_type, 0)

    def _resolve_claims(self) -> None:
        """
        Resolve the current claim window once all responses are in.

        Priority: win > pung/kong > chow.
        If multiple players win simultaneously, the one with the highest
        priority seat (left of discarder, clockwise) wins.
        If no claim is accepted, resume normal play (next player draws).
        """
        if self._best_claim is None:
            # No claims; advance to the next player's draw turn
            self._advance_turn()
            return

        claim = self._best_claim
        claimer_idx: int = claim["player_idx"]
        claim_type: str = claim["type"]
        claim_tiles: list[str] = claim.get("tiles", [])

        discard_tile = self.last_discard
        discarder_idx = self.last_discard_player

        # Remove tile from discarder's discard pile
        if discard_tile and discarder_idx is not None:
            try:
                self.discards[discarder_idx].remove(discard_tile)
            except ValueError:
                pass  # Already removed or inconsistency

        claimer = self.players[claimer_idx]

        if claim_type == "win":
            # Add the claimed tile to the winner's hand, then finalize
            claimer.hand.append(discard_tile)
            self._finalize_win(claimer_idx, discard_tile, ron=True)
            # player.score is set inside _finalize_win (= han_total)

        elif claim_type in ("pung", "kong"):
            # Form the meld
            claimer.hand.append(discard_tile)
            if claim_type == "pung":
                meld = [discard_tile, discard_tile, discard_tile]
            else:
                meld = [discard_tile, discard_tile, discard_tile, discard_tile]
            # Remove meld tiles from hand
            for t in meld:
                claimer.hand.remove(t)
            claimer.melds.append(meld)

            if claim_type == "kong":
                # Record kong chip payment before drawing
                self.record_kong_payment(claimer_idx)
                # Draw replacement tile from back of wall
                replacement = self._draw_from_back()
                if replacement is not None:
                    claimer.hand.append(replacement)
                    self._collect_bonus_tiles(claimer_idx)
                else:
                    # Wall exhausted — game is a draw
                    self.phase = "ended"
                    return

            self.current_turn = claimer_idx
            self.last_discard = None
            self.last_discard_player = None
            self.phase = "discarding"

        elif claim_type == "chow":
            # claim_tiles contains the two tiles from hand that form the chow
            # with the discarded tile
            claimer.hand.append(discard_tile)
            chow_meld = sorted(claim_tiles + [discard_tile],
                               key=lambda t: (get_suit(t) or "", t))
            for t in chow_meld:
                claimer.hand.remove(t)
            claimer.melds.append(chow_meld)

            self.current_turn = claimer_idx
            self.last_discard = None
            self.last_discard_player = None
            self.phase = "discarding"

        self._best_claim = None
        self._pending_claims.clear()
        self._skipped_claims.clear()

    def _advance_turn(self) -> None:
        """Move to the next player's drawing turn."""
        self.current_turn = (self.current_turn + 1) % NUM_PLAYERS
        self.last_discard = None
        self.last_discard_player = None
        self.phase = "drawing"
        self._best_claim = None
        self._pending_claims.clear()
        self._skipped_claims.clear()

    def _finalize_win(self, player_idx: int, winning_tile: str, ron: bool = False) -> None:
        """Mark the game as ended with the given player as winner."""
        self.winner = self.players[player_idx].id
        self.win_ron = ron
        self.win_discarder_idx = self.last_discard_player if ron else None
        self.phase = "ended"
        logger.info(
            "Player %s wins! Room=%s tile=%s ron=%s",
            self.winner, self.room_id, winning_tile, ron
        )
        # Calculate Han breakdown
        player = self.players[player_idx]
        concealed = player.hand_without_bonus()
        result = calculate_han(concealed, player.melds, player.flowers, ron)
        self.han_breakdown = result['breakdown']
        self.han_total = result['total']
        # Store han total as the round score for display (replaces old _calculate_score)
        player.score = self.han_total

    def record_kong_payment(self, konger_idx: int) -> None:
        """
        Record an immediate kong payment: each of the other 3 players pays 1 chip
        to the konger.  Accumulated in kong_chip_transfers; applied at hand end.
        """
        konger_id = self.players[konger_idx].id
        self.kong_chip_transfers[konger_id] = (
            self.kong_chip_transfers.get(konger_id, 0) + 3
        )
        for i, p in enumerate(self.players):
            if i != konger_idx:
                self.kong_chip_transfers[p.id] = (
                    self.kong_chip_transfers.get(p.id, 0) - 1
                )

    def _open_claim_window(self) -> None:
        """Open a claim window for all players except the discarder."""
        discarder = self.last_discard_player
        self._pending_claims = {
            i for i in range(NUM_PLAYERS) if i != discarder
        }
        self._skipped_claims.clear()
        self._best_claim = None
        self.phase = "claiming"

    def _check_claim_window_closed(self) -> None:
        """
        Check if all non-discard players have responded (claimed or skipped).
        If so, resolve the claim.
        """
        responded = self._skipped_claims | (
            {self._best_claim["player_idx"]} if self._best_claim else set()
        )
        if self._pending_claims.issubset(responded):
            self._resolve_claims()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def deal_initial_tiles(self) -> None:
        """
        Deal the initial tiles:
          - Dealer (player 0) receives 14 tiles.
          - Other players receive 13 tiles each.

        After dealing, bonus tiles are auto-collected for all players.
        """
        for player_idx in range(NUM_PLAYERS):
            count = DEALER_INITIAL_TILES if player_idx == 0 else NON_DEALER_INITIAL_TILES
            for _ in range(count):
                tile = self._draw_from_front()
                if tile is not None:
                    self.players[player_idx].hand.append(tile)

        # Auto-collect bonus tiles for all players
        for player_idx in range(NUM_PLAYERS):
            self._collect_bonus_tiles(player_idx)

        # Dealer starts by discarding (they already have 14 tiles)
        self.current_turn = 0
        self.phase = "discarding"
        logger.info("Initial tiles dealt. Room=%s", self.room_id)

    def draw_tile(self, player_idx: int) -> Optional[str]:
        """
        Draw a tile from the wall for the given player.

        Can only be done during the "drawing" phase by the current turn player.

        Args:
            player_idx: Index of the player drawing.

        Returns:
            The drawn tile string, or None if the wall is empty (draw game).

        Raises:
            ValueError: If it is not the player's turn or wrong phase.
        """
        if self.phase != "drawing":
            raise ValueError(f"Cannot draw in phase '{self.phase}'.")
        if player_idx != self.current_turn:
            raise ValueError(f"It is not player {player_idx}'s turn.")

        tile = self._draw_from_front()
        if tile is None:
            # Wall is exhausted — draw game
            self.phase = "ended"
            logger.info("Wall exhausted — draw game. Room=%s", self.room_id)
            return None

        player = self.players[player_idx]
        player.hand.append(tile)
        self._collect_bonus_tiles(player_idx)
        self.phase = "discarding"

        # Check for self-drawn win
        # (Caller must explicitly call declare_win to confirm)
        return tile

    def discard_tile(self, player_idx: int, tile: str) -> None:
        """
        Discard a tile from the player's hand.

        Can only be done during the "discarding" phase by the current turn player.

        Args:
            player_idx: Index of the player discarding.
            tile:       The tile string to discard.

        Raises:
            ValueError: If wrong phase, not the player's turn, or tile not in hand.
        """
        if self.phase != "discarding":
            raise ValueError(f"Cannot discard in phase '{self.phase}'.")
        if player_idx != self.current_turn:
            raise ValueError(f"It is not player {player_idx}'s turn.")

        player = self.players[player_idx]
        if tile not in player.hand:
            raise ValueError(f"Tile '{tile}' is not in player {player_idx}'s hand.")
        if is_flower_tile(tile):
            raise ValueError(f"Cannot discard bonus tile '{tile}'; it is auto-collected.")

        player.hand.remove(tile)
        self.discards[player_idx].append(tile)
        self.last_discard = tile
        self.last_discard_player = player_idx

        self._open_claim_window()
        logger.debug("Player %d discarded '%s'. Room=%s", player_idx, tile, self.room_id)

    def claim_pung(self, player_idx: int) -> bool:
        """
        Submit a pung claim for the last discarded tile.

        The claim is recorded; it takes effect when the claim window closes.

        Args:
            player_idx: Index of the claiming player.

        Returns:
            True if the claim is valid and was recorded.

        Raises:
            ValueError: If not in claiming phase or player cannot claim.
        """
        if self.phase != "claiming":
            raise ValueError("Not in claiming phase.")
        if player_idx == self.last_discard_player:
            raise ValueError("The discarder cannot claim their own tile.")
        if player_idx not in self._pending_claims:
            raise ValueError(f"Player {player_idx} is not eligible to claim.")

        tile = self.last_discard
        player = self.players[player_idx]

        if not can_pung(player.hand, tile):
            return False

        new_priority = self._claim_priority("pung")
        current_priority = (
            self._claim_priority(self._best_claim["type"])
            if self._best_claim else -1
        )

        if new_priority >= current_priority:
            self._best_claim = {"player_idx": player_idx, "type": "pung", "tiles": []}

        self._skipped_claims.add(player_idx)
        self._check_claim_window_closed()
        return True

    def claim_kong(self, player_idx: int, tile: str) -> bool:
        """
        Submit a kong claim.

        Supports two kong types:
          - Claimed kong: The last discarded tile completes 4-of-a-kind.
          - Self-drawn kong: The player has 4-of-a-kind entirely in hand.
            In this case, tile is the quad tile and last_discard is None.

        Args:
            player_idx: Index of the claiming player.
            tile:       The tile forming the kong.

        Returns:
            True if the claim was recorded.

        Raises:
            ValueError: On invalid state.
        """
        player = self.players[player_idx]

        # Self-drawn kong (during discarding phase, player adds 4th from hand)
        if self.phase == "discarding" and player_idx == self.current_turn:
            if player.hand.count(tile) < 4:
                raise ValueError(f"Player {player_idx} does not have 4x '{tile}' for self-kong.")
            meld = [tile] * 4
            for t in meld:
                player.hand.remove(t)
            player.melds.append(meld)
            replacement = self._draw_from_back()
            if replacement is not None:
                player.hand.append(replacement)
                self._collect_bonus_tiles(player_idx)
            else:
                self.phase = "ended"
                return True
            # Record kong chip payment (each other player pays 1 chip)
            self.record_kong_payment(player_idx)
            # Player stays in discarding phase to discard again
            return True

        # Claimed kong (from discard)
        if self.phase != "claiming":
            raise ValueError("Not in claiming phase.")
        if player_idx == self.last_discard_player:
            raise ValueError("The discarder cannot claim their own tile.")
        if player_idx not in self._pending_claims:
            raise ValueError(f"Player {player_idx} is not eligible to claim.")
        if tile != self.last_discard:
            raise ValueError(f"Claimed tile '{tile}' does not match last discard.")

        if not can_kong(player.hand, tile):
            return False

        new_priority = self._claim_priority("kong")
        current_priority = (
            self._claim_priority(self._best_claim["type"])
            if self._best_claim else -1
        )

        if new_priority >= current_priority:
            self._best_claim = {"player_idx": player_idx, "type": "kong", "tiles": []}

        self._skipped_claims.add(player_idx)
        self._check_claim_window_closed()
        return True

    def claim_chow(self, player_idx: int, tiles: list[str]) -> bool:
        """
        Submit a chow claim using two tiles from the player's hand.

        Chow can only be claimed from the player to the left (i.e., the player
        whose index is (player_idx - 1) % NUM_PLAYERS, which is the previous turn).

        Args:
            player_idx: Index of the claiming player.
            tiles:      The two tiles from the player's hand that form the chow
                        together with the discarded tile.

        Returns:
            True if the claim was recorded.

        Raises:
            ValueError: On invalid state or ineligible claim.
        """
        if self.phase != "claiming":
            raise ValueError("Not in claiming phase.")
        if player_idx not in self._pending_claims:
            raise ValueError(f"Player {player_idx} is not eligible to claim.")

        # Chow is only from the left player (directly before current player)
        left_of_claimer = (player_idx - 1) % NUM_PLAYERS
        if self.last_discard_player != left_of_claimer:
            raise ValueError(
                f"Player {player_idx} can only chow from the player to their left."
            )

        tile = self.last_discard
        player = self.players[player_idx]
        possible_chows = can_chow(player.hand, tile)

        # Verify the requested tiles form a valid chow with the discarded tile
        requested_set = sorted(tiles + [tile])
        valid = any(sorted(chow) == requested_set for chow in possible_chows)
        if not valid:
            return False

        # Chow only accepted if no higher-priority claim exists
        current_priority = (
            self._claim_priority(self._best_claim["type"])
            if self._best_claim else -1
        )
        if self._claim_priority("chow") > current_priority:
            self._best_claim = {
                "player_idx": player_idx,
                "type": "chow",
                "tiles": tiles,
            }

        self._skipped_claims.add(player_idx)
        self._check_claim_window_closed()
        return True

    def declare_win(self, player_idx: int) -> dict:
        """
        Declare a win for the given player.

        Supported win types:
          - Self-draw (tsumo): During "discarding" phase (player just drew).
          - Ron (claimed tile win): During "claiming" phase.

        Args:
            player_idx: Index of the winning player.

        Returns:
            Score breakdown dict with keys: winner, winning_tile, ron, score, hand, melds.

        Raises:
            ValueError: If the hand is not a valid winning hand.
        """
        player = self.players[player_idx]
        ron = False
        winning_tile: Optional[str] = None

        if self.phase == "discarding" and player_idx == self.current_turn:
            # Self-draw win: the last tile drawn is in the hand already
            effective_hand = player.hand_without_bonus()
            meld_tiles = [t for meld in player.melds for t in meld[:3]]
            if not is_winning_hand(effective_hand + meld_tiles):
                raise ValueError(f"Player {player_idx}'s hand is not a winning hand.")
            winning_tile = effective_hand[-1]  # conventionally the last drawn tile
            ron = False

        elif self.phase == "claiming":
            if player_idx == self.last_discard_player:
                raise ValueError("The discarder cannot win on their own discarded tile.")
            if player_idx not in self._pending_claims:
                raise ValueError(f"Player {player_idx} cannot claim in this window.")

            tile = self.last_discard
            # Validate using a temporary copy — do NOT modify the real hand here.
            # _resolve_claims will add the tile and finalize when the window closes.
            effective_hand = player.hand_without_bonus() + [tile]
            meld_tiles = [t for meld in player.melds for t in meld[:3]]
            if not is_winning_hand(effective_hand + meld_tiles):
                raise ValueError(f"Player {player_idx}'s hand + '{tile}' is not a winning hand.")

            winning_tile = tile
            ron = True

            # Submit as the highest-priority claim
            self._best_claim = {
                "player_idx": player_idx,
                "type": "win",
                "tiles": [],
            }
            self._skipped_claims.add(player_idx)
            self._check_claim_window_closed()

            # _check_claim_window_closed may call _resolve_claims which sets phase to "ended"
            if self.phase != "ended":
                # Other players haven't responded yet; the win will be finalized later
                # Score and hand updates happen in _resolve_claims when the window closes.
                return {
                    "winner": player.id,
                    "winning_tile": winning_tile,
                    "ron": ron,
                    "score": 0,
                    "hand": player.hand_without_bonus(),
                    "melds": player.melds,
                    "pending": True,
                }

        else:
            raise ValueError(
                f"Cannot declare win in phase '{self.phase}' for player {player_idx}."
            )

        # For claiming wins that closed the window immediately, _resolve_claims already
        # called _finalize_win and updated the score — don't do it again.
        if self.phase == "ended" and ron:
            return {
                "winner": player.id,
                "winning_tile": winning_tile,
                "ron": ron,
                "score": player.score,
                "hand": player.hand_without_bonus(),
                "melds": player.melds,
                "pending": False,
            }

        self._finalize_win(player_idx, winning_tile, ron)
        # player.score is set inside _finalize_win (= han_total)

        return {
            "winner": player.id,
            "winning_tile": winning_tile,
            "ron": ron,
            "score": player.score,   # = han_total (set by _finalize_win)
            "hand": player.hand_without_bonus(),
            "melds": player.melds,
            "pending": False,
        }

    def skip_claim(self, player_idx: int) -> None:
        """
        Signal that the player passes on claiming the last discarded tile.

        Args:
            player_idx: Index of the player skipping.

        Raises:
            ValueError: If not in claiming phase.
        """
        if self.phase != "claiming":
            raise ValueError("Not in claiming phase.")
        if player_idx not in self._pending_claims:
            return  # Already responded; ignore

        self._skipped_claims.add(player_idx)
        self._check_claim_window_closed()

    # _calculate_score removed: chip settlement is now han-based (see websocket._handle_game_over)

    def get_available_actions(self, player_idx: int) -> list[str]:
        """
        Return a list of action strings available to the given player.

        Possible actions:
          "draw"        - Draw a tile from the wall.
          "discard"     - Discard a tile from hand.
          "win"         - Declare a winning hand.
          "pung"        - Claim a pung on the last discard.
          "kong"        - Claim a kong (self or discard).
          "chow"        - Claim a chow on the last discard.
          "skip"        - Pass on claiming the last discard.

        Args:
            player_idx: Index of the querying player.

        Returns:
            Sorted list of available action strings.
        """
        actions: list[str] = []
        player = self.players[player_idx]

        if self.phase == "ended":
            return []

        if self.phase == "drawing" and player_idx == self.current_turn:
            actions.append("draw")

        if self.phase == "discarding" and player_idx == self.current_turn:
            actions.append("discard")
            # Check self-draw win
            effective_hand = player.hand_without_bonus()
            meld_tiles = [t for meld in player.melds for t in meld[:3]]
            if len(effective_hand) + len(meld_tiles) == 14 and is_winning_hand(effective_hand + meld_tiles):
                actions.append("win")
            # Check self-drawn kong (4-of-a-kind in hand)
            from collections import Counter
            counts = Counter(player.hand_without_bonus())
            if any(c >= 4 for c in counts.values()):
                actions.append("kong")

        if self.phase == "claiming" and player_idx != self.last_discard_player:
            if player_idx in self._pending_claims and player_idx not in self._skipped_claims:
                tile = self.last_discard
                effective_hand = player.hand_without_bonus()

                # Check win
                meld_tiles = [t for meld in player.melds for t in meld[:3]]
                test_hand = effective_hand + [tile] + meld_tiles
                if is_winning_hand(test_hand):
                    actions.append("win")

                # Check pung
                if can_pung(effective_hand, tile):
                    actions.append("pung")

                # Check kong
                if can_kong(effective_hand, tile):
                    actions.append("kong")

                # Check chow (only from left player)
                left_of_player = (player_idx - 1) % NUM_PLAYERS
                if self.last_discard_player == left_of_player:
                    if can_chow(effective_hand, tile):
                        actions.append("chow")

                actions.append("skip")

        return sorted(set(actions))

    def to_dict(self, viewing_player_idx: Optional[int] = None) -> dict:
        """
        Serialize the game state to a JSON-compatible dictionary.

        If viewing_player_idx is provided, other players' hands are hidden
        (replaced with tile counts for privacy).

        Args:
            viewing_player_idx: The index of the player viewing the state,
                                or None to reveal all hands (e.g., for debugging).

        Returns:
            Dictionary representation of the game state.
        """
        players_data = []
        for i, player in enumerate(self.players):
            if viewing_player_idx is not None and i != viewing_player_idx:
                # Hide hand tiles for other players
                hand_data = {"hidden": True, "count": player.effective_tile_count()}
            else:
                hand_data = {"tiles": list(player.hand), "hidden": False}

            players_data.append({
                "index": i,
                "id": player.id,
                "hand": hand_data,
                "melds": [list(m) for m in player.melds],
                "flowers": list(player.flowers),
                "score": player.score,
                "is_ai": player.is_ai,
                "claims_pending": player.claims_pending,
            })

        return {
            "room_id": self.room_id,
            "phase": self.phase,
            "current_turn": self.current_turn,
            "last_discard": self.last_discard,
            "last_discard_player": self.last_discard_player,
            "wall_remaining": len(self.wall),
            "discards": [list(pile) for pile in self.discards],
            "players": players_data,
            "winner": self.winner,
            "available_actions": (
                self.get_available_actions(viewing_player_idx)
                if viewing_player_idx is not None
                else []
            ),
        }
