"""
hand.py - Mahjong hand validation and meld detection.

Terminology:
  Meld:  A completed set of tiles used in a winning hand.
         - Pung (pong): 3 identical tiles, e.g. ["BAMBOO_5", "BAMBOO_5", "BAMBOO_5"]
         - Kong:        4 identical tiles (treated as a pung for hand structure)
         - Chow (seq):  3 consecutive suit tiles, e.g. ["BAMBOO_3","BAMBOO_4","BAMBOO_5"]
  Pair:  2 identical tiles forming the "eye" of a winning hand.

A standard winning hand consists of:
  4 melds (pung or chow) + 1 pair  (total 14 tiles, or 13 + claimed tile)

Flower/season tiles are bonus tiles that do not count toward the hand structure;
they should be removed before validation.
"""

from collections import Counter
from typing import Optional
from .tiles import get_suit, get_number, is_suit_tile, is_honor_tile, is_flower_tile


def _remove_tile(tiles: list[str], tile: str) -> list[str]:
    """Return a copy of tiles with the first occurrence of tile removed."""
    copy = list(tiles)
    copy.remove(tile)
    return copy


def _remove_tiles(tiles: list[str], to_remove: list[str]) -> list[str]:
    """Return a copy of tiles with all tiles in to_remove removed (one by one)."""
    copy = list(tiles)
    for t in to_remove:
        copy.remove(t)
    return copy


def find_pairs(tiles: list[str]) -> list[str]:
    """
    Find all tiles that appear at least twice (pair candidates).

    Args:
        tiles: List of tile strings.

    Returns:
        Sorted list of unique tile strings that can form a pair.
    """
    counts = Counter(tiles)
    return sorted(tile for tile, count in counts.items() if count >= 2)


def _is_pung(tiles: list[str]) -> bool:
    """Check if exactly 3 tiles form a pung."""
    return len(tiles) == 3 and tiles[0] == tiles[1] == tiles[2]


def _is_chow(tiles: list[str]) -> bool:
    """Check if exactly 3 tiles form a chow (consecutive suit sequence)."""
    if len(tiles) != 3:
        return False
    suits = [get_suit(t) for t in tiles]
    if not all(s is not None for s in suits):
        return False
    if len(set(suits)) != 1:
        return False
    numbers = sorted(get_number(t) for t in tiles)
    return numbers[2] - numbers[1] == 1 and numbers[1] - numbers[0] == 1


def _find_chows_containing(tiles: list[str], tile: str) -> list[list[str]]:
    """
    Find all possible chow combinations in tiles that include the given tile.

    Args:
        tiles:  The hand tiles (must include tile).
        tile:   The specific tile that must be part of each returned chow.

    Returns:
        List of possible chow triplets, each as a sorted list of 3 tile strings.
    """
    suit = get_suit(tile)
    num = get_number(tile)
    if suit is None or num is None:
        return []

    possible_chows: list[list[str]] = []
    # The tile can occupy position 1, 2, or 3 of a consecutive triple
    for offset in range(3):
        start = num - offset
        triplet = [f"{suit}_{start + i}" for i in range(3)]
        # Validate numbers are in range 1-9
        if any(get_number(t) < 1 or get_number(t) > 9 for t in triplet):
            continue
        # Check all three tiles exist in hand
        try:
            remaining = _remove_tiles(list(tiles), triplet)
            _ = remaining  # just to confirm removal succeeds
            possible_chows.append(sorted(triplet, key=lambda t: get_number(t)))
        except ValueError:
            continue

    # Deduplicate
    seen: set[tuple] = set()
    unique: list[list[str]] = []
    for chow in possible_chows:
        key = tuple(chow)
        if key not in seen:
            seen.add(key)
            unique.append(chow)
    return unique


def _try_extract_melds(tiles: list[str]) -> bool:
    """
    Recursively attempt to decompose tiles entirely into melds (pungs or chows).
    Returns True if tiles can be fully consumed as melds.

    Args:
        tiles: Sorted list of remaining tiles to decompose.
    """
    if not tiles:
        return True

    tile = tiles[0]  # Always try to eliminate the first tile

    # Try pung first
    if tiles.count(tile) >= 3:
        remaining = _remove_tiles(tiles, [tile, tile, tile])
        if _try_extract_melds(remaining):
            return True

    # Try chow (only for suit tiles)
    if is_suit_tile(tile):
        suit = get_suit(tile)
        num = get_number(tile)
        # tile must be the lowest in the chow (to avoid duplicate attempts)
        next1 = f"{suit}_{num + 1}"
        next2 = f"{suit}_{num + 2}"
        if num <= 7 and next1 in tiles and next2 in tiles:
            remaining = _remove_tiles(tiles, [tile, next1, next2])
            if _try_extract_melds(remaining):
                return True

    return False


def is_winning_hand(tiles: list[str]) -> bool:
    """
    Check if the given tiles form a valid winning hand.

    A winning hand requires exactly 14 tiles that can be structured as:
      4 melds (pung or chow) + 1 pair

    Bonus tiles (flowers/seasons) must be removed before calling this function.

    Args:
        tiles: List of 14 tile strings.

    Returns:
        True if the tiles form a winning hand.
    """
    # Filter out bonus tiles for safety
    hand = [t for t in tiles if not is_flower_tile(t)]

    if len(hand) != 14:
        return False

    sorted_tiles = sorted(hand)
    pair_candidates = find_pairs(sorted_tiles)

    for pair_tile in pair_candidates:
        # Remove the pair and try to form 4 melds from the rest
        remaining = _remove_tiles(sorted_tiles, [pair_tile, pair_tile])
        if _try_extract_melds(remaining):
            return True

    # Seven pairs (七對) — standard HK Mahjong rule
    if _is_seven_pairs(sorted_tiles):
        return True

    return False


def is_winning_hand_given_melds(
    concealed_tiles: list[str],
    n_declared_melds: int,
) -> bool:
    """
    Check if the player's concealed tiles form a valid winning hand structure,
    given that n_declared_melds melds have already been locked (pung/chow/kong).

    Unlike is_winning_hand(), the declared meld tiles are NOT included here —
    they are already fixed and must NOT be recombined with the concealed tiles.
    Only the concealed portion is validated.

    The concealed tiles must be able to form:
        1 pair  +  (4 - n_declared_melds) melds

    Seven pairs (七對) are only possible when n_declared_melds == 0
    (requires all 14 tiles to be concealed).

    Args:
        concealed_tiles:  Player's concealed hand including the winning tile,
                          with bonus tiles excluded. Expected length:
                          14 - 3 * n_declared_melds.
        n_declared_melds: Number of already-declared melds (pungs/chows/kongs).

    Returns:
        True if the concealed tiles can form the required pair + melds.
    """
    hand = [t for t in concealed_tiles if not is_flower_tile(t)]
    expected = 14 - 3 * n_declared_melds
    if len(hand) != expected:
        return False

    sorted_hand = sorted(hand)

    # Seven pairs only valid when no declared melds (all 14 tiles concealed)
    if n_declared_melds == 0 and _is_seven_pairs(sorted_hand):
        return True

    for pair_tile in find_pairs(sorted_hand):
        remaining = _remove_tiles(sorted_hand, [pair_tile, pair_tile])
        if _try_extract_melds(remaining):
            return True

    return False


def _extract_all_melds_recursive(
    tiles: list[str],
    current_melds: list[list[str]],
    all_results: list[list[list[str]]],
) -> None:
    """
    Enumerate all possible ways to extract melds from tiles.
    Populates all_results with each unique complete decomposition.
    """
    if not tiles:
        all_results.append([list(m) for m in current_melds])
        return

    tile = tiles[0]

    # Try pung
    if tiles.count(tile) >= 3:
        remaining = _remove_tiles(tiles, [tile, tile, tile])
        _extract_all_melds_recursive(
            remaining, current_melds + [[tile, tile, tile]], all_results
        )

    # Try chow (only suits, tile must be lowest)
    if is_suit_tile(tile):
        suit = get_suit(tile)
        num = get_number(tile)
        next1 = f"{suit}_{num + 1}"
        next2 = f"{suit}_{num + 2}"
        if num <= 7 and next1 in tiles and next2 in tiles:
            remaining = _remove_tiles(tiles, [tile, next1, next2])
            _extract_all_melds_recursive(
                remaining,
                current_melds + [[tile, next1, next2]],
                all_results,
            )


def find_melds(tiles: list[str]) -> list[list[str]]:
    """
    Find all possible melds in the hand by enumerating complete meld decompositions.

    This returns the union of all melds found across every valid decomposition.

    Args:
        tiles: List of tile strings (should exclude bonus tiles).

    Returns:
        List of unique melds (each meld is a list of 3 tile strings).
    """
    sorted_tiles = sorted(tiles)
    all_results: list[list[list[str]]] = []
    _extract_all_melds_recursive(sorted_tiles, [], all_results)

    # Collect unique melds across all decompositions
    seen: set[tuple] = set()
    unique_melds: list[list[str]] = []
    for decomposition in all_results:
        for meld in decomposition:
            key = tuple(sorted(meld))
            if key not in seen:
                seen.add(key)
                unique_melds.append(meld)
    return unique_melds


def can_pung(hand: list[str], tile: str) -> bool:
    """
    Check if the player can claim a pung with the given tile.

    A pung requires 2 copies of tile already in hand.

    Args:
        hand: The player's current hand (not including the claimed tile).
        tile: The tile being claimed.

    Returns:
        True if pung is possible.
    """
    return hand.count(tile) >= 2


def can_kong(hand: list[str], tile: str) -> bool:
    """
    Check if the player can claim a kong with the given tile.

    A kong requires 3 copies of tile already in hand (claimed kong),
    or 4 copies in hand (self-drawn kong).

    Args:
        hand: The player's current hand (not including the claimed tile for a claimed kong).
        tile: The tile being added.

    Returns:
        True if kong is possible (either claimed or self-drawn with 4 copies).
    """
    return hand.count(tile) >= 3


def can_chow(hand: list[str], tile: str) -> list[list[str]]:
    """
    Find all possible chow combinations using the given tile.

    Chow can only be formed with suit tiles.

    Args:
        hand: The player's current hand (not including the claimed tile).
        tile: The tile being claimed.

    Returns:
        List of possible chow triplets (each as a sorted list of 3 tile strings).
        Empty list if no chow is possible.
    """
    if not is_suit_tile(tile):
        return []

    # Include the tile in the combined pool for searching
    combined = list(hand) + [tile]
    return _find_chows_containing(combined, tile)


def _is_seven_pairs(tiles: list[str]) -> bool:
    """
    Check if tiles form a seven-pairs hand (7 different pairs).
    This is a special winning hand variant.
    """
    if len(tiles) != 14:
        return False
    counts = Counter(tiles)
    return len(counts) == 7 and all(v == 2 for v in counts.values())


# ============================================================
# Dalian Qionghu (大连穷胡) Rules
# ============================================================

_DALIAN_SUITS = frozenset({'BAMBOO', 'CIRCLES', 'CHARACTERS'})

# 所有大连规则下合法的牌种（34种，不含花牌）
_ALL_DALIAN_TILES = (
    [f"BAMBOO_{i}" for i in range(1, 10)]
    + [f"CIRCLES_{i}" for i in range(1, 10)]
    + [f"CHARACTERS_{i}" for i in range(1, 10)]
    + ['EAST', 'SOUTH', 'WEST', 'NORTH', 'RED', 'GREEN', 'WHITE']
)


def _extract_groups_rec_dalian(tiles: list[str], groups: list) -> bool:
    """Like _extract_groups_rec but dragons (RED/GREEN/WHITE) cannot form pungs — pair only."""
    if not tiles:
        return True
    tile = tiles[0]
    # Dragons are pair-only in Dalian rules; skip pung extraction for them
    is_dragon = tile in ('RED', 'GREEN', 'WHITE')
    # Try pung (only for non-dragons)
    if not is_dragon and tiles.count(tile) >= 3:
        remaining = _remove_tiles(tiles, [tile, tile, tile])
        groups.append({'type': 'pung', 'tiles': [tile, tile, tile]})
        if _extract_groups_rec_dalian(remaining, groups):
            return True
        groups.pop()
    # Try chow (tile must be lowest)
    if is_suit_tile(tile):
        suit = get_suit(tile)
        num = get_number(tile)
        n1 = f"{suit}_{num + 1}"
        n2 = f"{suit}_{num + 2}"
        if num <= 7 and n1 in tiles and n2 in tiles:
            remaining = _remove_tiles(tiles, [tile, n1, n2])
            groups.append({'type': 'chow', 'tiles': [tile, n1, n2]})
            if _extract_groups_rec_dalian(remaining, groups):
                return True
            groups.pop()
    return False


def decompose_winning_hand_dalian(concealed_tiles: list[str]) -> 'Optional[dict]':
    """
    Find one valid decomposition for Dalian Qionghu rules.
    Dragons (中/發/白) cannot form pungs — they may only serve as the pair.
    No seven-pairs in Dalian rules.
    """
    hand = sorted([t for t in concealed_tiles if not is_flower_tile(t)])

    for pair_tile in find_pairs(hand):
        remaining = _remove_tiles(hand, [pair_tile, pair_tile])
        groups: list = []
        if _extract_groups_rec_dalian(remaining, groups):
            return {
                'pair': pair_tile,
                'groups': groups,
                'seven_pairs': False,
            }
    return None


def _try_extract_melds_dalian(tiles: list[str]) -> bool:
    """Like _try_extract_melds but dragons cannot form pungs."""
    if not tiles:
        return True
    tile = tiles[0]
    is_dragon = tile in ('RED', 'GREEN', 'WHITE')
    # Try pung (skip for dragons)
    if not is_dragon and tiles.count(tile) >= 3:
        remaining = _remove_tiles(tiles, [tile, tile, tile])
        if _try_extract_melds_dalian(remaining):
            return True
    # Try chow (only suit tiles, tile must be lowest)
    if is_suit_tile(tile):
        suit = get_suit(tile)
        num = get_number(tile)
        next1 = f"{suit}_{num + 1}"
        next2 = f"{suit}_{num + 2}"
        if num <= 7 and next1 in tiles and next2 in tiles:
            remaining = _remove_tiles(tiles, [tile, next1, next2])
            if _try_extract_melds_dalian(remaining):
                return True
    return False


def is_winning_hand_dalian(
    concealed_tiles: list[str],
    n_declared_melds: int,
    declared_melds: list,
    bao_tile: Optional[str] = None,
) -> bool:
    """
    Check if a hand is a valid winning hand under Dalian Qionghu rules.

    Requirements:
    1. Basic structure: 1 pair + (4-n_melds) melds (no seven pairs; dragons pair-only)
    2. 禁止门清: must have at least one declared meld (开门) to win
    3. 三色全: tiles span all three suits (条/饼/万)
    4. 幺九: contains at least one terminal (1 or 9); exempted if hand has honors (winds/dragons)
    5. At least one pung (in declared melds or in concealed decomposition)
    6. 手把一禁手: n_declared_melds < 4

    If bao_tile is provided, the bao tile in hand may act as a wildcard substitute.
    """
    hand = [t for t in concealed_tiles if not is_flower_tile(t)]
    expected = 14 - 3 * n_declared_melds
    if len(hand) != expected:
        return False

    # 禁止门清: must have at least one declared meld (开门)
    if n_declared_melds == 0:
        return False

    # 禁手: 手把一 (all 4 melds declared = 手把一 is illegal in Dalian)
    if n_declared_melds >= 4:
        return False

    sorted_hand = sorted(hand)

    # Basic structure check (dragons pair-only)
    valid_structure = False
    for pair_tile in find_pairs(sorted_hand):
        remaining = _remove_tiles(sorted_hand, [pair_tile, pair_tile])
        if _try_extract_melds_dalian(remaining):
            valid_structure = True
            break

    if valid_structure:
        # Combine all tiles for further checks
        all_tiles = list(hand)
        for m in declared_melds:
            all_tiles.extend(m[:3])

        # 三色全: must span all three suits
        suits_present = {get_suit(t) for t in all_tiles if get_suit(t)}
        if _DALIAN_SUITS <= suits_present:
            # 幺九: must have at least one terminal (1 or 9), unless hand contains any honor tile
            has_honor = any(t in ('EAST', 'SOUTH', 'WEST', 'NORTH', 'RED', 'GREEN', 'WHITE') for t in all_tiles)
            yaojiu_ok = has_honor or any(get_number(t) in (1, 9) for t in all_tiles if get_number(t) is not None)
            if yaojiu_ok:
                # 至少一刻子: must have at least one pung (declared or in concealed decomposition)
                declared_pung_tiles = {
                    m[0] for m in declared_melds
                    if len(m) >= 3 and m[0] == m[1] == m[2]
                }
                if declared_pung_tiles:
                    return True  # has a declared pung

                # Check concealed decomposition for a pung
                for pair_tile in find_pairs(sorted_hand):
                    remaining = _remove_tiles(sorted_hand, [pair_tile, pair_tile])
                    groups: list = []
                    if _extract_groups_rec_dalian(remaining, groups):
                        if any(g['type'] == 'pung' for g in groups):
                            return True

    # ── 宝牌野牌替换（Dalian only）────────────────────────────────────
    # 若手牌中有宝牌，尝试将其替换为每种候选张，看替换后是否满足胡牌条件
    if bao_tile and bao_tile in [t for t in concealed_tiles if not is_flower_tile(t)]:
        hand_without_bao = list(concealed_tiles)
        hand_without_bao.remove(bao_tile)  # 移除一张宝牌
        for substitute in _ALL_DALIAN_TILES:
            if substitute == bao_tile:
                continue  # 替换为同种牌无意义
            test_hand = hand_without_bao + [substitute]
            # 递归调用时不传 bao_tile，避免无限递归
            if is_winning_hand_dalian(test_hand, n_declared_melds, declared_melds, bao_tile=None):
                return True

    return False


def is_tenpai_dalian(
    concealed_tiles: list[str],
    n_declared_melds: int,
    declared_melds: list,
    bao_tile: Optional[str] = None,
) -> list[str]:
    """
    返回让当前手牌在大连规则下胡牌的所有等待张列表。

    前提：n_declared_melds >= 1（禁止门清），n_declared_melds <= 3。
    手牌张数应为 13 - 3*n_declared_melds（摸牌前的手牌数）。

    如果 bao_tile 已确定，会额外考虑宝牌作为野牌时的等待张。

    Returns:
        去重后的等待张字符串列表，空列表表示未听牌。
    """
    waits: list[str] = []
    for candidate in _ALL_DALIAN_TILES:
        test_hand = list(concealed_tiles) + [candidate]
        if is_winning_hand_dalian(test_hand, n_declared_melds, declared_melds, bao_tile=bao_tile):
            if candidate not in waits:
                waits.append(candidate)
    return waits


def _is_kanchan(winning_tile: str, concealed_without_winning: list[str]) -> bool:
    """
    Detect if the winning tile fills a kanchan (坎张/夹胡) wait.

    A kanchan means the winning tile was the middle tile of a sequential triple
    (e.g. hand has 4,6 and winning tile is 5 — the middle piece of 4-5-6).

    Returns True only if:
    - winning_tile is a suited tile with number 2-8
    - There exists a valid decomposition where winning_tile is the middle of a chow
    - Removing winning_tile from that chow leaves no other valid winning structure
      (i.e. the kanchan is the *only* way to complete the hand)
    """
    suit = get_suit(winning_tile)
    num = get_number(winning_tile)
    if suit is None or num is None or num < 2 or num > 8:
        return False

    lower = f"{suit}_{num - 1}"
    upper = f"{suit}_{num + 1}"

    # Check if winning_tile can be the middle of a kanchan triple (lower, winning, upper)
    tiles_check = list(concealed_without_winning)
    if tiles_check.count(lower) < 1 or tiles_check.count(upper) < 1:
        return False

    # Check two-sided (双面) wait: winning_tile could also be the low or high end of a chow
    # If there's a two-sided alternative, it's not a pure kanchan
    two_sided_possible = False
    # Can winning_tile be the LOW end of a chow? (need winning+1 and winning+2)
    t1 = f"{suit}_{num + 1}"
    t2 = f"{suit}_{num + 2}"
    if num <= 7 and tiles_check.count(t1) >= 1 and tiles_check.count(t2) >= 1:
        two_sided_possible = True
    # Can winning_tile be the HIGH end of a chow? (need winning-2 and winning-1)
    t3 = f"{suit}_{num - 2}"
    t4 = f"{suit}_{num - 1}"
    if num >= 3 and tiles_check.count(t3) >= 1 and tiles_check.count(t4) >= 1:
        two_sided_possible = True

    # Single tile wait (单钓): check if we have tiles that support a tanki wait on winning_tile
    # (i.e. winning_tile is the pair; only valid if it appears ≥2 times in the full hand)
    # In kanchan detection we don't consider tanki.

    return not two_sided_possible


def calculate_han_dalian(
    concealed_tiles: list[str],
    declared_melds: list,
    ron: bool,
    player_seat: int = 0,
    round_wind_idx: int = 0,
    ling_shang: bool = False,
    is_dealer: bool = False,
    winning_tile: 'Optional[str]' = None,
    rob_kong: bool = False,
    bao_tile: Optional[str] = None,
) -> dict:
    """
    Calculate Han (番) for a Dalian Qionghu winning hand.

    番型:
      基础 1番    — always
      自摸 +1    — not ron
      夹胡 +1    — kanchan wait (only when ron=True and winning_tile qualifies)
      庄家 +1    — is_dealer
      杠上开花 +2 — ling_shang and not ron
      抢杠胡 +2  — rob_kong
      冲宝 +2    — ron and winning_tile == bao_tile
      摸宝 +1    — not ron and bao_tile in concealed_tiles (wildcard used)

    Returns: {'breakdown': [...], 'total': int}
    """
    breakdown: list[dict] = []

    def add(name_cn: str, name_en: str, fan: int) -> None:
        breakdown.append({'name_cn': name_cn, 'name_en': name_en, 'fan': fan})

    add('基础', 'Base', 1)

    if not ron:
        add('自摸', 'Tsumo (Self-draw)', 1)

    if is_dealer:
        add('庄家', 'Dealer Bonus', 1)

    # 夹胡 (kanchan) — applies when winning by ron
    if ron and winning_tile is not None:
        hand_without_win = list(concealed_tiles)
        if winning_tile in hand_without_win:
            hand_without_win.remove(winning_tile)
        else:
            # winning tile was not yet added (pre-win state); skip kanchan check
            hand_without_win = list(concealed_tiles)
        if _is_kanchan(winning_tile, hand_without_win):
            add('夹胡', 'Kanchan (Middle Wait)', 1)

    if ling_shang and not ron:
        add('杠上开花', 'Kong Win (Lingshang)', 2)

    if rob_kong:
        add('抢杠胡', 'Rob Kong', 2)

    # ── 宝牌加番 ──────────────────────────────────────────────────────
    if bao_tile is not None:
        if ron and winning_tile == bao_tile:
            # 冲宝：荣和时胡牌张本身就是宝牌
            add('冲宝', 'Chong Bao (Treasure Win)', 2)
        elif not ron and bao_tile in [t for t in concealed_tiles if not is_flower_tile(t)]:
            # 摸宝：自摸时手中有宝牌（作为野牌使用）
            # 宝牌不能同时是 winning_tile（那种情况归于普通自摸，无额外宝牌番）
            if winning_tile != bao_tile:
                add('摸宝', 'Mo Bao (Treasure Draw)', 1)

    total = sum(x['fan'] for x in breakdown)
    return {'breakdown': breakdown, 'total': total}


# ============================================================
# Han (番) Calculation
# ============================================================

_DRAGONS = frozenset({'RED', 'GREEN', 'WHITE'})
_WINDS   = frozenset({'EAST', 'SOUTH', 'WEST', 'NORTH'})
_HONORS  = _DRAGONS | _WINDS

# Seat index → wind tile name
_WIND_TILES = ['EAST', 'SOUTH', 'WEST', 'NORTH']

# Seat index → set of matching flower/season tile names (本命花)
_SEAT_FLOWERS: dict[int, frozenset] = {
    0: frozenset({'FLOWER_1', 'SEASON_1'}),  # East (东)
    1: frozenset({'FLOWER_2', 'SEASON_2'}),  # South (南)
    2: frozenset({'FLOWER_3', 'SEASON_3'}),  # West (西)
    3: frozenset({'FLOWER_4', 'SEASON_4'}),  # North (北)
}


def _h_is_honor(tile: str) -> bool:
    return tile in _HONORS


def _h_is_dragon(tile: str) -> bool:
    return tile in _DRAGONS


def _h_is_wind(tile: str) -> bool:
    return tile in _WINDS


def _h_is_terminal(tile: str) -> bool:
    n = get_number(tile)
    return n is not None and n in (1, 9)


def _h_is_terminal_or_honor(tile: str) -> bool:
    return _h_is_terminal(tile) or _h_is_honor(tile)


def _h_is_simple(tile: str) -> bool:
    """Suited tile with number 2-8 (no terminals, no honors)."""
    n = get_number(tile)
    return n is not None and 2 <= n <= 8


def _extract_groups_rec(tiles: list[str], groups: list) -> bool:
    """Recursively extract melds, appending to groups. Returns True if successful."""
    if not tiles:
        return True
    tile = tiles[0]
    # Try pung
    if tiles.count(tile) >= 3:
        remaining = _remove_tiles(tiles, [tile, tile, tile])
        groups.append({'type': 'pung', 'tiles': [tile, tile, tile]})
        if _extract_groups_rec(remaining, groups):
            return True
        groups.pop()
    # Try chow (tile must be lowest)
    if is_suit_tile(tile):
        suit = get_suit(tile)
        num = get_number(tile)
        n1 = f"{suit}_{num + 1}"
        n2 = f"{suit}_{num + 2}"
        if num <= 7 and n1 in tiles and n2 in tiles:
            remaining = _remove_tiles(tiles, [tile, n1, n2])
            groups.append({'type': 'chow', 'tiles': [tile, n1, n2]})
            if _extract_groups_rec(remaining, groups):
                return True
            groups.pop()
    return False


def decompose_winning_hand(concealed_tiles: list[str]) -> Optional[dict]:
    """
    Find one valid decomposition of the concealed part of a winning hand.

    Args:
        concealed_tiles: Tiles in the player's concealed hand (must exclude bonus tiles).
                         Length = 14 - 3 * n_declared_melds.

    Returns dict with:
        'pair': str              - the pair tile string
        'groups': list of {'type': 'pung'|'chow', 'tiles': [str, str, str]}
        'seven_pairs': bool
        'all_pairs': list[str]   - only present when seven_pairs=True
    Returns None if no valid decomposition exists.
    """
    hand = sorted([t for t in concealed_tiles if not is_flower_tile(t)])

    # Seven pairs (only when 14 concealed tiles)
    if len(hand) == 14 and _is_seven_pairs(hand):
        counts = Counter(hand)
        return {
            'pair': sorted(counts.keys())[0],
            'groups': [],
            'seven_pairs': True,
            'all_pairs': sorted(counts.keys()),
        }

    for pair_tile in find_pairs(hand):
        remaining = _remove_tiles(hand, [pair_tile, pair_tile])
        groups: list = []
        if _extract_groups_rec(remaining, groups):
            return {
                'pair': pair_tile,
                'groups': groups,
                'seven_pairs': False,
            }
    return None


def calculate_han(
    concealed_tiles: list[str],
    declared_melds: list[list[str]],
    flowers: list[str],
    ron: bool,
    player_seat: int = 0,
    round_wind_idx: int = 0,
    ling_shang: bool = False,
) -> dict:
    """
    Calculate Han (番) breakdown for a winning hand.

    Args:
        concealed_tiles: All tiles in the player's concealed hand including the
                         winning tile (no bonus tiles). Length = 14 - 3*len(declared_melds).
        declared_melds:  Declared meld groups (each 3 or 4 tiles).
        flowers:         Bonus tiles already collected.
        ron:             True if won by discard (荣和), False if self-draw (自摸).
        player_seat:     Player's seat index (0=East, 1=South, 2=West, 3=North).
        round_wind_idx:  Current round-wind index (0=East round, 1=South, 2=West, 3=North).
        ling_shang:      True if the winning tile was drawn as a kong replacement (嶺上開花).

    Returns:
        {
            'breakdown': [{'name_cn': str, 'name_en': str, 'fan': int}, ...],
            'total': int,
        }
    """
    breakdown: list[dict] = []

    def add(name_cn: str, name_en: str, fan: int) -> None:
        breakdown.append({'name_cn': name_cn, 'name_en': name_en, 'fan': fan})

    # Decompose the concealed hand
    decomp = decompose_winning_hand(concealed_tiles)
    if decomp is None:
        add('基本分', 'Base', 1)
        return {'breakdown': breakdown, 'total': 1}

    seven_pairs   = decomp['seven_pairs']
    pair_tile     = decomp['pair']
    concl_groups  = decomp['groups']   # list of {'type', 'tiles'}

    # Normalise declared melds to the same format (take first 3 tiles for kongs)
    def _dtype(meld: list[str]) -> str:
        return 'pung' if (len(meld) >= 3 and meld[0] == meld[1]) else 'chow'

    decl_groups = [{'type': _dtype(m), 'tiles': m[:3]} for m in declared_melds]
    all_groups  = concl_groups + decl_groups     # combined meld list (up to 4)

    # All structural tiles (concealed + declared, no bonus tiles)
    all_tiles: list[str] = list(concealed_tiles)
    for m in declared_melds:
        all_tiles.extend(m[:3])
    all_tiles = [t for t in all_tiles if not is_flower_tile(t)]

    # ── Always ──────────────────────────────────────────────
    add('基本分', 'Base', 1)

    if not ron:
        add('自摸', 'Tsumo (Self-draw)', 1)

    if not flowers:
        add('无花', 'No Bonus Tiles', 1)

    if not declared_melds and ron:
        add('门清', 'Concealed Hand', 1)

    # ── Seven Pairs ─────────────────────────────────────────
    if seven_pairs:
        add('七对', 'Seven Pairs', 3)
        # Flush checks still apply
        suits = {get_suit(t) for t in all_tiles if get_suit(t)}
        has_honors = any(_h_is_honor(t) for t in all_tiles)
        if not has_honors:
            if len(suits) == 1:
                add('清一色', 'Full Flush', 7)
        else:
            if not suits:
                add('字一色', 'All Honors', 7)
            elif len(suits) == 1:
                add('混一色', 'Half Flush', 3)
        # 本命花与手牌结构无关，七对子同样计入
        seat_flower_set = _SEAT_FLOWERS.get(player_seat, frozenset())
        seat_flower_count = sum(1 for f in flowers if f in seat_flower_set)
        if seat_flower_count > 0:
            add('本命花', 'Seat Flower', seat_flower_count)
        # 嶺上開花七对子亦适用（暗杠后补牌完成七对，极罕见但合法）
        if ling_shang and not ron:
            add('嶺上開花', 'Kong Win (Lingshang)', 1)
        total = sum(x['fan'] for x in breakdown)
        return {'breakdown': breakdown, 'total': total}

    # ── Structural ──────────────────────────────────────────
    n_groups     = len(all_groups)
    all_pungs    = n_groups == 4 and all(g['type'] == 'pung' for g in all_groups)
    all_chows    = n_groups == 4 and all(g['type'] == 'chow' for g in all_groups)

    if all_pungs:
        add('碰碰胡', 'All Pungs', 3)

    # 平胡: all chows + simple pair + fully concealed + must win by RON (荣和)
    # (港式规则：平胡只能荣和，自摸不计平胡)
    if (all_chows
            and not declared_melds
            and _h_is_simple(pair_tile)
            and ron):
        add('平胡', 'Ping Hu (All Sequences)', 1)

    if all(_h_is_simple(t) for t in all_tiles):
        add('断幺', 'All Simples', 1)

    # 混幺九: EVERY tile in every group AND the pair must be terminal or honor.
    # (港式规则：每张牌均须为幺九牌或风字牌，含中间牌2-8的组合不算)
    # 注：港式日常规则中碰碰胡与混幺九可叠加（分别描述结构与花色特征）。
    if (all_groups
            and all(all(_h_is_terminal_or_honor(t) for t in g['tiles']) for g in all_groups)
            and _h_is_terminal_or_honor(pair_tile)):
        add('混幺九', 'Mixed Terminals & Honors', 3)

    # ── Suit / Color ────────────────────────────────────────
    suits       = {get_suit(t) for t in all_tiles if get_suit(t)}
    has_honors  = any(_h_is_honor(t) for t in all_tiles)

    if not has_honors:
        if len(suits) == 1:
            add('清一色', 'Full Flush', 7)
    else:
        if not suits:
            add('字一色', 'All Honors', 7)
        elif len(suits) == 1:
            add('混一色', 'Half Flush', 3)

    # ── Dragon / Wind Combinations ──────────────────────────
    pung_tiles   = {g['tiles'][0] for g in all_groups if g['type'] == 'pung'}
    dragon_pungs = pung_tiles & _DRAGONS
    wind_pungs   = pung_tiles & _WINDS

    if len(dragon_pungs) == 3:
        add('大三元', 'Big Three Dragons', 8)
    elif len(dragon_pungs) == 2:
        remaining_dragon = _DRAGONS - dragon_pungs
        if pair_tile in remaining_dragon:
            add('小三元', 'Small Three Dragons', 5)

    if len(wind_pungs) == 4:
        add('大四喜', 'Big Four Winds', 13)
    elif len(wind_pungs) == 3:
        remaining_wind = _WINDS - wind_pungs
        if pair_tile in remaining_wind:
            add('小四喜', 'Small Four Winds', 6)

    # ── 嶺上開花 (Ling Shang Kai Hua / Kong Win) ────────────────
    # Winning by self-draw on a kong replacement tile: +1 fan
    if ling_shang and not ron:
        add('嶺上開花', 'Kong Win (Lingshang)', 1)

    # ── 本命花 (Seat Flowers) ──────────────────────────────────
    # Each flower/season tile matching the player's seat: +1 fan each.
    # Merged into one entry to avoid duplicate rows in the breakdown display.
    seat_flower_set = _SEAT_FLOWERS.get(player_seat, frozenset())
    seat_flower_count = sum(1 for f in flowers if f in seat_flower_set)
    if seat_flower_count > 0:
        add('本命花', 'Seat Flower', seat_flower_count)

    # ── 自风 / 圈风 (Seat Wind Pung / Round Wind Pung) ──────────
    # Punging the seat-wind tile or the round-wind tile each give +1 fan.
    # If seat wind == round wind, both bonuses apply (total +2 for that pung).
    seat_wind_tile  = _WIND_TILES[player_seat  % 4]
    round_wind_tile = _WIND_TILES[round_wind_idx % 4]
    if seat_wind_tile in pung_tiles:
        add('自风碰', 'Seat Wind Pung', 1)
    if round_wind_tile in pung_tiles:
        add('圈风碰', 'Round Wind Pung', 1)

    total = sum(x['fan'] for x in breakdown)
    return {'breakdown': breakdown, 'total': total}
