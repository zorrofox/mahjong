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
    is_winning_hand_given_melds,
    is_winning_hand_dalian,
    is_tenpai_dalian,
    can_pung,
    can_kong,
    can_chow,
    calculate_han,
    calculate_han_dalian,
)

logger = logging.getLogger(__name__)

# Number of players in a standard Mahjong game
NUM_PLAYERS = 4

# Initial tile counts
DEALER_INITIAL_TILES = 14
NON_DEALER_INITIAL_TILES = 13

MIN_HAN = 1  # Minimum fan required to declare a winning hand.
# Standard HK tournament rules use 3, but most casual/home games use 1
# (any structurally valid hand may win). Set to 3 to enforce the strict rule.


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

    def __init__(self, room_id: str, player_ids: list[str], dealer_idx: int = 0, round_wind_idx: int = 0, ruleset: str = "hk") -> None:
        if len(player_ids) != NUM_PLAYERS:
            raise ValueError(f"Mahjong requires exactly {NUM_PLAYERS} players.")

        self.room_id: str = room_id
        self.ruleset: str = ruleset
        self.players: list[PlayerState] = [
            PlayerState(id=pid) for pid in player_ids
        ]

        # The wall; dealt from the front, kong replacements from the back.
        wall = build_deck(ruleset)
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

        # Dealer seat index for this hand (rotates across rounds via Room.dealer_idx)
        self.dealer_idx: int = dealer_idx

        # Most recently drawn tile (set by draw_tile() and kong replacement draws).
        # Included in action_required so the frontend can pre-select it.
        self.last_drawn_tile: Optional[str] = None

        self.round_wind_idx: int = round_wind_idx  # 0=East, 1=South, 2=West, 3=North

        # True when the last tile drawn came from the back of the wall (kong replacement).
        # Enables the 嶺上開花 bonus when winning by self-draw on that tile.
        self.lingshang_pending: bool = False

        # Game result
        self.winner: Optional[str] = None  # player id of the winner
        self.winning_tile: Optional[str] = None  # the specific tile that completed the hand
        self.win_ron: Optional[bool] = None  # True = discard win, False = self-draw
        self.win_discarder_idx: Optional[int] = None  # index of the discarder for ron wins
        self.han_breakdown: list[dict] = []   # [{'name_cn','name_en','fan'}, ...]
        self.han_total: int = 0

        # Rob-the-kong (搶杠) state: set while an extend-pung window is open.
        # Only "win" claims are valid during this window.
        self._is_rob_kong_window: bool = False
        self._rob_kong_tile: Optional[str] = None       # the tile being extended
        self._rob_kong_player_idx: Optional[int] = None # the konger

        # HK only: accumulated chip transfers from kong declarations (immediate payments).
        # Applied at game end alongside the win payment.
        # Keys are player_id strings; values are net chip deltas (can be negative).
        self.kong_chip_transfers: dict[str, int] = {}

        # 大连专用：杠分记录（只有胡牌者才算）
        # 明杠(min)=1×底注/家，暗杠(an)=2×底注/家，不管自摸还是荣和，三家都付给胡牌者
        self.kong_log: list[dict] = []  # [{'player_idx': int, 'type': 'min'|'an'}]

        # ── 宝牌状态（大连穷胡专用）─────────────────────────────────
        self.bao_tile: Optional[str] = None        # 已确定的宝牌（None 表示未揭示）
        self.bao_declared: bool = False            # 是否已触发过宝牌
        self.bao_dice_roll: Optional[int] = None   # 骰子点数（展示用）
        self.tenpai_players: set[int] = set()      # 已进入听牌的玩家索引集合

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

    def _seat_distance(self, claimer_idx: int) -> int:
        """Clockwise distance from the discarder to claimer_idx (1–3).

        Used to break ties when two players submit the same-priority claim
        (e.g. pung vs pung, kong vs kong). The player closest clockwise to
        the discarder has priority (distance 1 beats distance 2 or 3).
        """
        n = len(self.players)
        return (claimer_idx - self.last_discard_player) % n

    def _resolve_claims(self) -> None:
        """
        Resolve the current claim window once all responses are in.

        Priority: win > pung/kong > chow.
        If multiple players win simultaneously, the one with the highest
        priority seat (left of discarder, clockwise) wins.
        If no claim is accepted, resume normal play (next player draws).
        """
        if self._best_claim is None:
            if self._is_rob_kong_window:
                # Nobody robbed the extend-pung kong — complete it now.
                self._complete_extend_kong()
                return
            # Normal: advance to the next player's draw turn
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
            _was_rob_kong = self._is_rob_kong_window
            if self._is_rob_kong_window:
                # Robbing the kong (搶杠胡): revert the konger's extended meld back to
                # a 3-tile pung before processing the win.
                konger_idx = self._rob_kong_player_idx
                if konger_idx is not None:
                    konger = self.players[konger_idx]
                    for meld in konger.melds:
                        if len(meld) == 4 and meld[0] == discard_tile:
                            meld.pop()  # 4-tile kong → 3-tile pung
                            break
                self._is_rob_kong_window = False
                self._rob_kong_tile = None
                self._rob_kong_player_idx = None

            # Add the claimed tile to the winner's hand, then finalize
            claimer.hand.append(discard_tile)
            if self.ruleset == "dalian":
                _pre_han = calculate_han_dalian(
                    claimer.hand_without_bonus(), claimer.melds, ron=True,
                    winning_tile=discard_tile,
                    bao_tile=self._effective_bao(claimer_idx),
                )
            else:
                _pre_han = calculate_han(
                    claimer.hand_without_bonus(), claimer.melds, claimer.flowers, ron=True
                )
            if _pre_han['total'] < MIN_HAN:
                # Insufficient fan — reject the win, advance to next turn
                claimer.hand.remove(discard_tile)
                logger.warning(
                    "Ron win claim by player %d rejected: %d fan < MIN_HAN %d",
                    claimer_idx, _pre_han['total'], MIN_HAN
                )
                self._advance_turn()
                return
            self._finalize_win(claimer_idx, discard_tile, ron=True, rob_kong=_was_rob_kong)
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
                # Record kong payment (明杠 from discard)
                self._record_kong(claimer_idx, 'min')
                # Draw replacement tile from back of wall
                replacement = self._draw_from_back()
                if replacement is not None:
                    claimer.hand.append(replacement)
                    self._collect_bonus_tiles(claimer_idx)
                    # replacement may itself be a flower; use hand[-1] to get
                    # the actual non-bonus tile that ended up in hand.
                    self.last_drawn_tile = claimer.hand[-1] if claimer.hand else replacement
                    self.lingshang_pending = True
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
        # 注：宝牌重摇检测由 websocket 层在调用 check_and_maybe_reroll_bao() 时完成

    def _advance_turn(self) -> None:
        """Move to the next player's drawing turn."""
        self.current_turn = (self.current_turn + 1) % NUM_PLAYERS
        self.last_discard = None
        self.last_discard_player = None
        self.phase = "drawing"
        self._best_claim = None
        self._pending_claims.clear()
        self._skipped_claims.clear()

    def _complete_extend_kong(self) -> None:
        """
        Finalise an extend-pung (加杠) kong after no one robbed it.

        The meld has already been extended from 3→4 tiles in claim_kong().
        Here we record the kong payment, draw the replacement tile, and
        return the konger to the discarding phase.
        """
        konger_idx = self._rob_kong_player_idx
        assert konger_idx is not None

        # Clear rob-kong state first
        self._is_rob_kong_window = False
        self._rob_kong_tile = None
        self._rob_kong_player_idx = None
        self._best_claim = None
        self._pending_claims.clear()
        self._skipped_claims.clear()

        # Record kong payment (加杠/extend-pung = 明杠)
        self._record_kong(konger_idx, 'min')

        # Draw replacement tile from back of wall
        replacement = self._draw_from_back()
        if replacement is not None:
            self.players[konger_idx].hand.append(replacement)
            self._collect_bonus_tiles(konger_idx)
            # replacement may itself be a bonus tile; use hand[-1] after collection
            hand = self.players[konger_idx].hand
            self.last_drawn_tile = hand[-1] if hand else replacement
            self.lingshang_pending = True
        else:
            self.phase = "ended"
            return

        self.current_turn = konger_idx
        self.last_discard = None
        self.last_discard_player = None
        self.phase = "discarding"

    def _effective_bao(self, player_idx: int) -> Optional[str]:
        """宝牌只对已上听（tenpai_players）的玩家生效。"""
        return self.bao_tile if player_idx in self.tenpai_players else None

    def _finalize_win(self, player_idx: int, winning_tile: str, ron: bool = False, rob_kong: bool = False) -> None:
        """Mark the game as ended with the given player as winner."""
        self.winner = self.players[player_idx].id
        self.winning_tile = winning_tile
        self.win_ron = ron
        self.win_discarder_idx = self.last_discard_player if ron else None
        self.phase = "ended"
        logger.info(
            "Player %s wins! Room=%s tile=%s ron=%s ruleset=%s",
            self.winner, self.room_id, winning_tile, ron, self.ruleset
        )
        # Calculate Han breakdown
        player = self.players[player_idx]
        concealed = player.hand_without_bonus()
        if self.ruleset == "dalian":
            result = calculate_han_dalian(
                concealed, player.melds, ron,
                player_seat=player_idx,
                round_wind_idx=self.round_wind_idx,
                ling_shang=self.lingshang_pending and not ron,
                is_dealer=(player_idx == self.dealer_idx),
                winning_tile=winning_tile,
                rob_kong=rob_kong,
                bao_tile=self._effective_bao(player_idx),
            )
        else:
            result = calculate_han(
                concealed, player.melds, player.flowers, ron,
                player_seat=player_idx,
                round_wind_idx=self.round_wind_idx,
                ling_shang=self.lingshang_pending and not ron,
            )
        self.lingshang_pending = False  # consumed
        self.han_breakdown = result['breakdown']
        self.han_total = result['total']
        # Store han total as the round score for display (replaces old _calculate_score)
        player.score = self.han_total

    def _record_kong(self, konger_idx: int, kong_type: str) -> None:
        """
        统一记录杠牌。
        - HK 规则：任何玩家杠牌立即从其他三家各收 1 筹码（kong_chip_transfers）
        - 大连规则：只有胡牌者的杠牌才算钱，记录到 kong_log 供结算时使用
          明杠(min)=1×底注/家, 暗杠(an)=2×底注/家

        Args:
            konger_idx: 杠牌玩家索引
            kong_type:  'min'（明杠：声索/加杠）或 'an'（暗杠：手中4张自摸）
        """
        if self.ruleset == "dalian":
            self.kong_log.append({'player_idx': konger_idx, 'type': kong_type})
        else:
            # HK: immediate 1-chip payment from each other player
            konger_id = self.players[konger_idx].id
            self.kong_chip_transfers[konger_id] = (
                self.kong_chip_transfers.get(konger_id, 0) + 3
            )
            for i, p in enumerate(self.players):
                if i != konger_idx:
                    self.kong_chip_transfers[p.id] = (
                        self.kong_chip_transfers.get(p.id, 0) - 1
                    )

    def record_kong_payment(self, konger_idx: int) -> None:
        """兼容旧接口，默认为明杠。"""
        self._record_kong(konger_idx, 'min')

    def check_and_trigger_bao(self) -> Optional[dict]:
        """
        检测所有玩家是否新进入听牌状态，并在首次听牌时掷骰子确定宝牌。

        关键设计：
        - 即使宝牌已揭示（bao_declared=True），仍继续扫描其余玩家是否达到听牌，
          以便后续玩家也能被加入 tenpai_players（获得听牌标识、看见宝牌）。
        - 只有第一位达到听牌的玩家才触发骰子选宝；后续玩家直接获知宝牌。

        Returns:
            {"player_idx": int, "dice": int, "bao_tile": str}  — 若本次首次触发宝牌
            None  — 无新变化（包含仅新增听牌玩家但宝牌已存在的情况）
        """
        if self.ruleset != "dalian":
            return None
        if not self.wall:
            return None

        bao_event: Optional[dict] = None

        for i, player in enumerate(self.players):
            if i in self.tenpai_players:
                continue
            hand = player.hand_without_bonus()
            # 听牌检测：手牌数须为 13 - 3*n_melds（摸牌前状态）
            expected_tenpai_count = 13 - 3 * len(player.melds)
            if len(hand) != expected_tenpai_count:
                continue
            # 结构性听牌检测（不传 bao_tile）避免宝牌野牌导致误判
            waits = is_tenpai_dalian(hand, len(player.melds), player.melds, bao_tile=None)
            if not waits:
                continue

            # 玩家新进入听牌
            self.tenpai_players.add(i)
            logger.info("Dalian: player %d reached tenpai room=%s", i, self.room_id)

            # 首次听牌触发骰子选宝
            if not self.bao_declared:
                import random
                dice = random.randint(1, 6)
                bao_idx = (dice - 1) % len(self.wall)
                self.bao_tile = self.wall[bao_idx]
                self.bao_declared = True
                self.bao_dice_roll = dice
                logger.info(
                    "Dalian: player %d tenpai → dice=%d bao_tile=%s room=%s",
                    i, dice, self.bao_tile, self.room_id
                )
                bao_event = {"player_idx": i, "dice": dice, "bao_tile": self.bao_tile}
                # 继续扫描，确保其他同时听牌的玩家也被记录

        return bao_event

    def _count_bao_revealed(self) -> int:
        """
        统计当前局中宝牌已被「明牌」的总数：
          - 弃牌堆中的宝牌（被打出但未被声索）
          - 各玩家副露（明牌）中的宝牌（碰/明杠/吃后进入副露）

        暗杠中的宝牌仍不可见，不计入此数。

        Returns:
            已明牌的宝牌总张数。
        """
        if not self.bao_declared or not self.bao_tile:
            return 0
        count = 0
        for i, player in enumerate(self.players):
            # 弃牌堆
            count += self.discards[i].count(self.bao_tile)
            # 副露中（明刻/明杠/顺子均统计前3张；暗杠 len==4 且所有牌相同时不计）
            for meld in player.melds:
                is_concealed_kong = (len(meld) == 4 and meld[0] == meld[1] == meld[2] == meld[3])
                if not is_concealed_kong:
                    count += meld.count(self.bao_tile)
        return count

    def check_and_maybe_reroll_bao(self) -> Optional[dict]:
        """
        检查宝牌明牌数是否已达到 3 张，若是则重摇。

        应在 discard_tile 和 _resolve_claims（碰/吃/明杠完成后）调用。

        Returns:
            {"dice": int, "bao_tile": str}  — 若发生重摇
            None  — 未达到条件
        """
        if self.ruleset != "dalian" or not self.bao_declared:
            return None
        if self._count_bao_revealed() >= 3:
            return self.reroll_bao()
        return None

    def reroll_bao(self) -> Optional[dict]:
        """
        重新掷骰子确定新宝牌。

        Returns:
            {"dice": int, "bao_tile": str}  — 新宝牌信息
            None  — 条件未满足（牌墙空）
        """
        if self.ruleset != "dalian" or not self.wall:
            return None
        import random
        dice = random.randint(1, 6)
        bao_idx = (dice - 1) % len(self.wall)
        self.bao_tile = self.wall[bao_idx]
        self.bao_dice_roll = dice
        logger.info(
            "Dalian: bao rerolled → dice=%d new_bao=%s room=%s",
            dice, self.bao_tile, self.room_id
        )
        return {"dice": dice, "bao_tile": self.bao_tile}

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
          - Dealer (self.dealer_idx) receives 14 tiles.
          - Other players receive 13 tiles each.

        After dealing, bonus tiles are auto-collected for all players.
        """
        for player_idx in range(NUM_PLAYERS):
            count = DEALER_INITIAL_TILES if player_idx == self.dealer_idx else NON_DEALER_INITIAL_TILES
            for _ in range(count):
                tile = self._draw_from_front()
                if tile is not None:
                    self.players[player_idx].hand.append(tile)

        # Auto-collect bonus tiles for all players (HK only; Dalian has no bonus tiles)
        if self.ruleset == "hk":
            for player_idx in range(NUM_PLAYERS):
                self._collect_bonus_tiles(player_idx)

        # Dealer starts by discarding (they already have 14 tiles)
        self.current_turn = self.dealer_idx
        self.phase = "discarding"
        logger.info("Initial tiles dealt. Room=%s dealer=%d ruleset=%s", self.room_id, self.dealer_idx, self.ruleset)

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

        # Dalian: 荒庄 when wall has ≤14 tiles (7 墩) remaining
        if self.ruleset == "dalian" and len(self.wall) <= 14:
            self.phase = "ended"
            logger.info("Dalian: wall ≤14 tiles — exhausted game. Room=%s", self.room_id)
            return None

        tile = self._draw_from_front()
        if tile is None:
            # Wall is exhausted — draw game
            self.phase = "ended"
            logger.info("Wall exhausted — draw game. Room=%s", self.room_id)
            return None

        player = self.players[player_idx]
        player.hand.append(tile)
        # HK only: auto-collect flower/season bonus tiles
        if self.ruleset == "hk":
            self._collect_bonus_tiles(player_idx)
        self.phase = "discarding"
        # last_drawn_tile must point to the actual non-bonus tile now in hand.
        self.last_drawn_tile = player.hand[-1] if player.hand else tile

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
        self.lingshang_pending = False  # player chose to discard; no longer ling shang
        if self.phase != "discarding":
            raise ValueError(f"Cannot discard in phase '{self.phase}'.")
        if player_idx != self.current_turn:
            raise ValueError(f"It is not player {player_idx}'s turn.")

        player = self.players[player_idx]
        if tile not in player.hand:
            raise ValueError(f"Tile '{tile}' is not in player {player_idx}'s hand.")
        if is_flower_tile(tile):
            raise ValueError(f"Cannot discard bonus tile '{tile}'; it is auto-collected.")

        # Dalian: 听牌者不能换听（discard must maintain tenpai）
        if self.ruleset == "dalian" and player_idx in self.tenpai_players:
            hand_after = list(player.hand_without_bonus())
            if tile in hand_after:
                hand_after.remove(tile)  # 只移除一张（不能用推导式，否则对子会被全删）
            # 不换听检测使用结构性听牌（不依赖宝牌野牌），防止 bao 误判导致错误限制
            waits_after = is_tenpai_dalian(hand_after, len(player.melds), player.melds,
                                            bao_tile=None)
            if not waits_after:
                # 安全阀：检查是否存在任何合法出牌（防止卡死）
                playable = player.hand_without_bonus()
                has_any_valid = False
                for t in set(playable):
                    tmp = list(playable)
                    tmp.remove(t)
                    if is_tenpai_dalian(tmp, len(player.melds), player.melds, bao_tile=None):
                        has_any_valid = True
                        break
                if has_any_valid:
                    raise ValueError(
                        f"Discarding '{tile}' would break tenpai for player {player_idx}. 不能换听。"
                    )
                else:
                    # 无合法出牌 → 可能误加入 tenpai_players，解除约束防止卡死
                    self.tenpai_players.discard(player_idx)
                    logger.warning(
                        "Dalian: player %d has no valid tenpai discard → removed from tenpai_players room=%s",
                        player_idx, self.room_id
                    )

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

        # Dalian: dragons (中/發/白) are pair-only and cannot be punged
        if self.ruleset == "dalian" and tile in ('RED', 'GREEN', 'WHITE'):
            return False

        if not can_pung(player.hand_without_bonus(), tile):
            return False

        new_priority = self._claim_priority("pung")
        current_priority = (
            self._claim_priority(self._best_claim["type"])
            if self._best_claim else -1
        )

        # Higher-priority claim always wins; for equal priority (pung vs pung)
        # the player closest clockwise to the discarder takes precedence.
        if new_priority > current_priority or (
            new_priority == current_priority
            and self._seat_distance(player_idx)
                < self._seat_distance(self._best_claim["player_idx"])
        ):
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

        # Self-drawn / extend-pung kong (during discarding phase)
        if self.phase == "discarding" and player_idx == self.current_turn:
            # ── Extend-pung (加杠): tile is in hand AND matches an existing pung ──
            extend_meld_idx = next(
                (i for i, m in enumerate(player.melds)
                 if len(m) == 3 and m[0] == m[1] == m[2] == tile),
                None,
            )
            if extend_meld_idx is not None and player.hand.count(tile) >= 1:
                player.hand.remove(tile)
                player.melds[extend_meld_idx].append(tile)  # 3-tile pung → 4-tile kong

                # Open a rob-the-kong (搶杠) claim window for all other players.
                # Only "win" claims are valid.
                self._is_rob_kong_window = True
                self._rob_kong_tile = tile
                self._rob_kong_player_idx = player_idx
                # Treat the kong tile as a pseudo-discard so declare_win / _resolve_claims
                # work through the existing claiming-phase machinery.
                self.last_discard = tile
                self.last_discard_player = player_idx
                self._pending_claims = {
                    i for i in range(NUM_PLAYERS) if i != player_idx
                }
                self._skipped_claims.clear()
                self._best_claim = None
                self.phase = "claiming"
                return True

            # ── Concealed kong (暗杠): 4-of-a-kind entirely in hand ──
            # 大连: 三元牌（中/發/白）只能做将，不能杠（暗杠/明杠均禁）
            if self.ruleset == "dalian" and tile in ('RED', 'GREEN', 'WHITE'):
                self.lingshang_pending = False
                raise ValueError(
                    f"Player {player_idx} cannot kong dragon tile '{tile}' in Dalian (三元牌只能做将)."
                )
            # 大连: 未开门的玩家不能暗杠
            if self.ruleset == "dalian" and not player.melds:
                self.lingshang_pending = False
                raise ValueError(
                    f"Player {player_idx} cannot declare concealed kong without any declared melds first (未开门不能暗杠)."
                )
            if player.hand.count(tile) < 4:
                # Clear any stale lingshang flag so it doesn't bleed into the
                # player's next discard after a failed kong attempt.
                self.lingshang_pending = False
                raise ValueError(
                    f"Player {player_idx} cannot declare kong with '{tile}': "
                    "no matching pung meld and fewer than 4 copies in hand."
                )
            meld = [tile] * 4
            for t in meld:
                player.hand.remove(t)
            player.melds.append(meld)
            replacement = self._draw_from_back()
            if replacement is not None:
                player.hand.append(replacement)
                self._collect_bonus_tiles(player_idx)
                # replacement may itself be a bonus tile; use hand[-1] after collection
                self.last_drawn_tile = player.hand[-1] if player.hand else replacement
                self.lingshang_pending = True
            else:
                self.phase = "ended"
                return True
            # Record kong payment (暗杠 = concealed kong)
            self._record_kong(player_idx, 'an')
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

        # 大连: 三元牌（中/發/白）只能做将，不能明杠
        if self.ruleset == "dalian" and tile in ('RED', 'GREEN', 'WHITE'):
            return False

        if not can_kong(player.hand_without_bonus(), tile):
            return False

        new_priority = self._claim_priority("kong")
        current_priority = (
            self._claim_priority(self._best_claim["type"])
            if self._best_claim else -1
        )

        # Higher-priority claim always wins; for equal priority (kong vs kong)
        # the player closest clockwise to the discarder takes precedence.
        if new_priority > current_priority or (
            new_priority == current_priority
            and self._seat_distance(player_idx)
                < self._seat_distance(self._best_claim["player_idx"])
        ):
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
        possible_chows = can_chow(player.hand_without_bonus(), tile)

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
            # Self-draw win: the last tile drawn is in the hand already.
            # Use is_winning_hand_given_melds so declared meld tiles are treated
            # as fixed and are NOT recombined with the concealed hand.
            effective_hand = player.hand_without_bonus()
            if self.ruleset == "dalian":
                if not is_winning_hand_dalian(effective_hand, len(player.melds), player.melds,
                                               bao_tile=self._effective_bao(player_idx)):
                    raise ValueError(f"Player {player_idx}'s hand is not a winning hand.")
                _pre_han = calculate_han_dalian(
                    effective_hand, player.melds, ron=False,
                    winning_tile=self.last_drawn_tile,
                    bao_tile=self._effective_bao(player_idx),
                )
            else:
                if not is_winning_hand_given_melds(effective_hand, len(player.melds)):
                    raise ValueError(f"Player {player_idx}'s hand is not a winning hand.")
                _pre_han = calculate_han(effective_hand, player.melds, player.flowers, ron=False)
            if _pre_han['total'] < MIN_HAN:
                raise ValueError(
                    f"Hand has only {_pre_han['total']} fan; minimum {MIN_HAN} required to win."
                )
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
            if self.ruleset == "dalian":
                if not is_winning_hand_dalian(effective_hand, len(player.melds), player.melds,
                                               bao_tile=self._effective_bao(player_idx)):
                    raise ValueError(f"Player {player_idx}'s hand + '{tile}' is not a winning hand.")
                _pre_han = calculate_han_dalian(effective_hand, player.melds, ron=True,
                                                winning_tile=tile,
                                                bao_tile=self._effective_bao(player_idx))
            else:
                if not is_winning_hand_given_melds(effective_hand, len(player.melds)):
                    raise ValueError(f"Player {player_idx}'s hand + '{tile}' is not a winning hand.")
                _pre_han = calculate_han(effective_hand, player.melds, player.flowers, ron=True)
            if _pre_han['total'] < MIN_HAN:
                raise ValueError(
                    f"Hand has only {_pre_han['total']} fan; minimum {MIN_HAN} required to win."
                )

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
            # Check self-draw win (declared melds are fixed — do NOT mix them
            # back into the concealed hand for validation).
            effective_hand = player.hand_without_bonus()
            if self.ruleset == "dalian":
                _can_win = is_winning_hand_dalian(effective_hand, len(player.melds), player.melds,
                                                   bao_tile=self._effective_bao(player_idx))
                _win_han = calculate_han_dalian(effective_hand, player.melds, ron=False,
                                                winning_tile=self.last_drawn_tile,
                                                bao_tile=self._effective_bao(player_idx)) if _can_win else None
            else:
                _can_win = is_winning_hand_given_melds(effective_hand, len(player.melds))
                _win_han = calculate_han(effective_hand, player.melds, player.flowers, ron=False) if _can_win else None
            if _can_win and _win_han and _win_han['total'] >= MIN_HAN:
                actions.append("win")
            # Check self-drawn kong — concealed (4-of-a-kind) or extend-pung (加杠)
            from collections import Counter
            counts = Counter(player.hand_without_bonus())
            _dalian_dragons = ('RED', 'GREEN', 'WHITE')
            # 大连：三元牌不能杠（只能做将）
            has_concealed_kong = any(
                c >= 4 and (self.ruleset != "dalian" or t not in _dalian_dragons)
                for t, c in counts.items()
            )
            pung_meld_tiles = {
                m[0] for m in player.melds
                if len(m) == 3 and m[0] == m[1] == m[2]
            }
            has_extend_pung = any(counts.get(t, 0) >= 1 for t in pung_meld_tiles)
            if has_concealed_kong or has_extend_pung:
                actions.append("kong")

        if self.phase == "claiming" and player_idx != self.last_discard_player:
            if player_idx in self._pending_claims and player_idx not in self._skipped_claims:
                tile = self.last_discard
                effective_hand = player.hand_without_bonus()

                if self._is_rob_kong_window:
                    # Rob-the-kong window (搶杠胡): ONLY win or skip allowed
                    if self.ruleset == "dalian":
                        _can_win_rob = is_winning_hand_dalian(effective_hand + [tile], len(player.melds), player.melds,
                                                              bao_tile=self._effective_bao(player_idx))
                        _rob_han = calculate_han_dalian(effective_hand + [tile], player.melds, ron=True,
                                                        winning_tile=tile, rob_kong=True,
                                                        bao_tile=self._effective_bao(player_idx)) if _can_win_rob else None
                    else:
                        _can_win_rob = is_winning_hand_given_melds(effective_hand + [tile], len(player.melds))
                        _rob_han = calculate_han(effective_hand + [tile], player.melds,
                                                 player.flowers, ron=True) if _can_win_rob else None
                    if _can_win_rob and _rob_han and _rob_han['total'] >= MIN_HAN:
                        actions.append("win")
                    actions.append("skip")
                    return sorted(set(actions))

                # Normal claim window ─────────────────────────────────────────
                # Check win (declared melds are fixed — do NOT mix them back).
                if self.ruleset == "dalian":
                    _can_win_claim = is_winning_hand_dalian(effective_hand + [tile], len(player.melds), player.melds,
                                                             bao_tile=self._effective_bao(player_idx))
                    _claim_han = calculate_han_dalian(effective_hand + [tile], player.melds, ron=True,
                                                      winning_tile=tile,
                                                      bao_tile=self._effective_bao(player_idx)) if _can_win_claim else None
                else:
                    _can_win_claim = is_winning_hand_given_melds(effective_hand + [tile], len(player.melds))
                    _claim_han = calculate_han(effective_hand + [tile], player.melds, player.flowers, ron=True) if _can_win_claim else None
                if _can_win_claim and _claim_han and _claim_han['total'] >= MIN_HAN:
                    actions.append("win")

                # Check pung (Dalian: cannot pung dragons)
                if self.ruleset == "dalian" and tile in ('RED', 'GREEN', 'WHITE'):
                    pass  # dragon pung not allowed in Dalian
                elif can_pung(effective_hand, tile):
                    actions.append("pung")

                # Check kong（大连：三元牌不能明杠）
                if can_kong(effective_hand, tile):
                    if not (self.ruleset == "dalian" and tile in ('RED', 'GREEN', 'WHITE')):
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
            if self.phase == "ended":
                # Game over: reveal every player's hand for the post-game display.
                hand_data = {"tiles": list(player.hand), "hidden": False}
            elif viewing_player_idx is not None and i != viewing_player_idx:
                # Hide hand tiles for other players during active play.
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
            "ruleset": self.ruleset,
            "phase": self.phase,
            "current_turn": self.current_turn,
            "dealer_idx": self.dealer_idx,
            "round_wind_idx": self.round_wind_idx,
            "last_discard": self.last_discard,
            "last_discard_player": self.last_discard_player,
            "wall_remaining": len(self.wall),
            "discards": [list(pile) for pile in self.discards],
            "players": players_data,
            "winner": self.winner,
            "winning_tile": self.winning_tile,
            # 宝牌可见规则：
            #   游戏进行中 → 只有已听牌的玩家（tenpai_players）可见（"别人不允许知道"）
            #   游戏结束后 → 公开揭示，所有玩家可见（结算弹窗展示本局宝牌）
            #   调试视角（None）→ 始终可见
            "bao_tile": (
                self.bao_tile
                if (viewing_player_idx is None
                    or self.phase == "ended"
                    or viewing_player_idx in self.tenpai_players)
                else None
            ),
            "bao_declared": self.bao_declared,
            "bao_dice_roll": self.bao_dice_roll if (
                viewing_player_idx is None or viewing_player_idx in self.tenpai_players
            ) else None,
            "bao_revealed_count": self._count_bao_revealed(),
            "tenpai_players": list(self.tenpai_players),
            "available_actions": (
                self.get_available_actions(viewing_player_idx)
                if viewing_player_idx is not None
                else []
            ),
        }
