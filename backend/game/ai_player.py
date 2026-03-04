"""
ai_player.py - Simple AI decision logic for Mahjong.

The AI uses a heuristic-based strategy:
  1. Always claim a winning hand.
  2. Claim pungs/kongs if they materially improve the hand.
  3. Claim chows only if they leave the hand closer to winning.
  4. When discarding:
     a. Discard bonus tiles first (they are auto-collected; this branch
        is a safety fallback since bonus tiles should be auto-collected
        by GameState).
     b. Discard isolated honor tiles (cannot form chows; need 2 more of
        the same to pung).
     c. Discard isolated suit tiles that are furthest from completing any
        meld, measured by minimum "distance" to the nearest potential meld.

Strategy metrics used internally:
  - "isolation score": how many adjacent suit tiles exist in the hand near
    a given tile (higher = less isolated = keep).
  - "meld completeness": how many tiles in the hand are already part of
    a pung, pair, or consecutive pair.
"""

from collections import Counter
from typing import Optional

from .tiles import (
    is_flower_tile,
    is_honor_tile,
    is_suit_tile,
    get_suit,
    get_number,
)
from .hand import (
    is_winning_hand,
    is_winning_hand_given_melds,
    is_winning_hand_dalian,
    can_pung,
    can_kong,
    can_chow,
    find_pairs,
)


class AIPlayer:
    """
    Heuristic-based AI player for Mahjong.

    This AI does not perform deep search; it uses fast greedy heuristics
    suitable for a casual game experience.
    """

    # ------------------------------------------------------------------ #
    # Discard strategy                                                     #
    # ------------------------------------------------------------------ #

    def choose_discard(
        self,
        hand: list[str],
        melds: list[list[str]],
        ruleset: str = "hk",
    ) -> str:
        """
        Choose the best tile to discard from the current hand.

        Priority order:
          1. Bonus tiles (flowers/seasons) — should already be auto-collected,
             but kept as a safety fallback.
          2. Isolated honor tiles (winds/dragons with no pair potential).
          3. Isolated suit tiles with the lowest connectivity score.

        Args:
            hand:    The player's current hand tiles.
            melds:   Already committed melds.
            ruleset: "hk" or "dalian" — affects scoring weights.

        Returns:
            The tile string to discard.

        Raises:
            ValueError: If the hand is empty.
        """
        if not hand:
            raise ValueError("Cannot choose discard from an empty hand.")

        playable = [t for t in hand if not is_flower_tile(t)]

        # Safety: if any bonus tiles remain, discard one (they should not
        # normally reach this point since GameState auto-collects them).
        bonus = [t for t in playable if is_flower_tile(t)]
        if bonus:
            return bonus[0]

        if not playable:
            raise ValueError("No non-bonus tiles available to discard.")

        # Score each tile; the tile with the LOWEST score is discarded.
        if ruleset == "dalian":
            scored = [(self._discard_score_dalian(tile, playable, melds), tile) for tile in playable]
        else:
            scored = [(self._discard_score(tile, playable), tile) for tile in playable]
        scored.sort(key=lambda x: (x[0], x[1]))  # deterministic tie-breaking
        return scored[0][1]

    def _discard_score(self, tile: str, hand: list[str]) -> float:
        """
        Compute a discard score for a tile (lower = better to discard).

        Scoring components (all negative contributions to keeping):
          - Bonus tiles:   -1000 (discard first)
          - Honor tiles:   -10 per copy in hand beyond the first
                            (1 copy = very isolated; 2 = pair potential; 3 = pung)
          - Suit tiles:    based on how many neighboring tiles exist in hand

        Args:
            tile: The tile being evaluated.
            hand: The full current hand (includes tile).

        Returns:
            Float score; lower means "prefer to discard this tile".
        """
        if is_flower_tile(tile):
            return -1000.0

        counts = Counter(hand)

        if is_honor_tile(tile):
            copies = counts[tile]
            # 1 copy: very isolated (score -10)
            # 2 copies: pair (score 20 — worth keeping)
            # 3 copies: almost-pung (score 50)
            if copies == 1:
                return -10.0
            elif copies == 2:
                return 20.0
            else:
                return 50.0

        if is_suit_tile(tile):
            return self._suit_tile_score(tile, hand, counts)

        return 0.0

    def _discard_score_dalian(
        self, tile: str, hand: list[str], melds: list[list[str]]
    ) -> float:
        """
        Discard scoring for Dalian Qionghu rules.

        Additional concerns vs HK:
        - 三色全: protect suits not already covered by declared melds
        - 幺九: keep at least one terminal or honor tile
        - 至少一刻: prefer tiles that can form pungs; keep pairs
        - 三元牌禁刻子: dragons (RED/GREEN/WHITE) can only be the PAIR
        """
        from collections import Counter as _Counter
        counts = _Counter(hand)
        _HONORS = ('EAST', 'SOUTH', 'WEST', 'NORTH', 'RED', 'GREEN', 'WHITE')
        _DRAGONS = ('RED', 'GREEN', 'WHITE')

        # ── dragons are pair-only: aggressively discard 3rd+ copy ──────────
        if tile in _DRAGONS:
            c = counts[tile]
            if c >= 3:
                return -200.0   # can't pung; 3rd copy is dead weight
            elif c == 2:
                return 10.0     # pair potential
            else:
                return -8.0     # single dragon; low value

        # ── base score from connectivity (reuse HK logic) ───────────────────
        score = self._discard_score(tile, hand)

        # ── 三色全: protect suits not already covered by declared melds ──────
        # A suit is "covered" if at least one declared meld belongs to it
        declared_suits = {get_suit(t) for m in melds for t in m[:3] if get_suit(t)}
        suit = get_suit(tile)
        if suit is not None and suit not in declared_suits:
            # This suit must appear in the hand; protect it when thin
            suit_tiles_in_hand = [t for t in hand if get_suit(t) == suit]
            suit_count = len(suit_tiles_in_hand)
            if suit_count <= 1:
                score += 80.0   # last tile of this suit — critical to keep
            elif suit_count <= 3:
                score += 30.0   # suit is thin
            elif suit_count <= 5:
                score += 10.0   # mild caution

        # ── 幺九: need at least one terminal (1 or 9) or any honor tile ──────
        num = get_number(tile)
        all_honors_in_hand = [t for t in hand if t in _HONORS]
        has_honor = len(all_honors_in_hand) > 0

        # Protect the last honor tile if we have no terminals either
        if tile in _HONORS and counts[tile] == 1:
            # This is a single honor tile in hand
            other_honors = [t for t in all_honors_in_hand if t != tile]
            if not other_honors:
                # Last honor — check if any terminal exists
                has_terminal = any(get_number(t) in (1, 9) for t in hand if get_number(t))
                if not has_terminal:
                    score += 25.0   # losing all honors with no terminal breaks 幺九

        if not has_honor and num in (1, 9):
            all_terminals = [t for t in hand if get_number(t) in (1, 9)]
            if len(all_terminals) <= 2:
                score += 30.0   # last terminals — protect 幺九

        # ── 至少一刻: protect pair/pung candidates ─────────────────────────
        if counts[tile] == 2:
            score += 10.0
        elif counts[tile] >= 3:
            score += 20.0

        return score

    def _suit_tile_score(
        self, tile: str, hand: list[str], counts: Counter
    ) -> float:
        """
        Score a suit tile based on its connectivity to other hand tiles.

        High score = well-connected = keep.
        Low/negative score = isolated = discard candidate.

        Connectivity factors:
          - Same tile (pung/pair potential): +15 per extra copy
          - Neighbor ±1 (chow potential):    +10 per neighbor tile
          - Neighbor ±2 (chow potential):    +5 per neighbor tile
        """
        suit = get_suit(tile)
        num = get_number(tile)
        if suit is None or num is None:
            return 0.0

        score = 0.0
        copies = counts[tile]

        # Pung/pair potential
        if copies == 2:
            score += 15.0
        elif copies >= 3:
            score += 30.0

        # Chow connectivity
        for offset in (1, -1):
            neighbor = f"{suit}_{num + offset}"
            if 1 <= num + offset <= 9:
                score += counts[neighbor] * 10.0

        for offset in (2, -2):
            neighbor = f"{suit}_{num + offset}"
            if 1 <= num + offset <= 9:
                score += counts[neighbor] * 5.0

        return score

    # ------------------------------------------------------------------ #
    # Claim decision                                                       #
    # ------------------------------------------------------------------ #

    def decide_claim(
        self,
        hand: list[str],
        melds: list[list[str]],
        tile: str,
        claim_type: str,
        ruleset: str = "hk",
    ) -> bool:
        """
        Decide whether to claim the given tile with the specified claim type.

        Args:
            hand:       The player's current hand (not including the tile).
            melds:      Already committed melds.
            tile:       The tile being offered.
            claim_type: One of "win", "pung", "kong", "chow".
            ruleset:    "hk" or "dalian".

        Returns:
            True if the AI should make the claim.
        """
        if claim_type == "win":
            return True  # Always win when possible (server validates)

        if claim_type == "pung":
            # Dalian: dragons cannot be punged
            if ruleset == "dalian" and tile in ('RED', 'GREEN', 'WHITE'):
                return False
            return self._should_claim_pung(hand, melds, tile)

        if claim_type == "kong":
            return self._should_claim_kong(hand, melds, tile)

        if claim_type == "chow":
            return self._should_claim_chow(hand, melds, tile)

        return False

    def _should_claim_pung(
        self, hand: list[str], melds: list[list[str]], tile: str
    ) -> bool:
        """
        Claim pung if it improves the hand.

        Strategy: Claim pung if the result brings the AI closer to a winning
        hand (fewer tiles needed), unless the remaining hand would be too
        fragmented to recover.
        """
        if not can_pung(hand, tile):
            return False

        # Simulate claiming the pung
        new_hand = list(hand)
        new_hand.remove(tile)
        new_hand.remove(tile)
        new_melds = melds + [[tile, tile, tile]]

        before_score = self._hand_progress_score(hand, melds)
        after_score = self._hand_progress_score(new_hand, new_melds)

        return after_score >= before_score

    def _should_claim_kong(
        self, hand: list[str], melds: list[list[str]], tile: str
    ) -> bool:
        """
        Claim kong if the AI holds 3 copies of the tile.

        Kong gives a replacement tile, which is generally beneficial.
        """
        return can_kong(hand, tile)

    def _should_claim_chow(
        self, hand: list[str], melds: list[list[str]], tile: str
    ) -> bool:
        """
        Claim chow only if it improves progress toward winning.

        The AI checks whether claiming the chow (with the best available
        combination from hand) leaves a hand closer to winning.
        """
        possible_chows = can_chow(hand, tile)
        if not possible_chows:
            return False

        best_after_score = float("-inf")
        for chow in possible_chows:
            # chow contains the 3 tiles including the discarded tile
            hand_tiles_in_chow = [t for t in chow if t != tile]
            if len(hand_tiles_in_chow) != 2:
                continue
            # Verify the hand contains these tiles
            try:
                new_hand = list(hand)
                for t in hand_tiles_in_chow:
                    new_hand.remove(t)
            except ValueError:
                continue

            new_melds = melds + [chow]
            score = self._hand_progress_score(new_hand, new_melds)
            if score > best_after_score:
                best_after_score = score

        before_score = self._hand_progress_score(hand, melds)
        return best_after_score > before_score

    # ------------------------------------------------------------------ #
    # Win detection                                                        #
    # ------------------------------------------------------------------ #

    def should_declare_win(
        self, hand: list[str], melds: list[list[str]], ruleset: str = "hk"
    ) -> bool:
        """
        Check if the current hand plus committed melds form a winning hand.

        Args:
            hand:    Current hand tiles (should exclude bonus tiles).
            melds:   Already committed melds.
            ruleset: "hk" or "dalian" — selects the appropriate win validator.

        Returns:
            True if the player should declare a win.
        """
        playable = [t for t in hand if not is_flower_tile(t)]

        if ruleset == "dalian":
            return is_winning_hand_dalian(playable, len(melds), melds)
        # Use is_winning_hand_given_melds so that declared meld tiles are
        # treated as fixed and are NOT recombined with the concealed hand.
        return is_winning_hand_given_melds(playable, len(melds))

    # ------------------------------------------------------------------ #
    # Internal hand evaluation                                            #
    # ------------------------------------------------------------------ #

    def _hand_progress_score(
        self, hand: list[str], melds: list[list[str]]
    ) -> float:
        """
        Estimate how close the hand is to winning (higher = better).

        Heuristic:
          - Each committed meld:    +30 points
          - Each complete pair:     +15 points
          - Each connected pair
            (two consecutive suit tiles): +8 points
          - Each suit tile with a neighbor ±1: +4 points
          - Each isolated tile:     -5 points

        Args:
            hand:  Current hand tiles.
            melds: Committed melds.

        Returns:
            Progress score.
        """
        playable = [t for t in hand if not is_flower_tile(t)]
        counts = Counter(playable)
        score: float = len(melds) * 30.0

        for tile, count in counts.items():
            if count >= 3:
                score += 25.0  # near-pung / pung in hand
            elif count == 2:
                score += 15.0  # pair
            else:
                # Isolated tile — check connectivity
                if is_suit_tile(tile):
                    suit = get_suit(tile)
                    num = get_number(tile)
                    connected = False
                    for offset in (1, -1, 2, -2):
                        neighbor = f"{suit}_{num + offset}"
                        if 1 <= num + offset <= 9 and counts[neighbor] > 0:
                            score += 4.0
                            connected = True
                    if not connected:
                        score -= 5.0
                else:
                    # Isolated honor tile
                    score -= 5.0

        return score
