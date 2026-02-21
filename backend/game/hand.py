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
# Han (番) Calculation
# ============================================================

_DRAGONS = frozenset({'RED', 'GREEN', 'WHITE'})
_WINDS   = frozenset({'EAST', 'SOUTH', 'WEST', 'NORTH'})
_HONORS  = _DRAGONS | _WINDS


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
) -> dict:
    """
    Calculate Han (番) breakdown for a winning hand.

    Args:
        concealed_tiles: All tiles in the player's concealed hand including the
                         winning tile (no bonus tiles). Length = 14 - 3*len(declared_melds).
        declared_melds:  Declared meld groups (each 3 or 4 tiles).
        flowers:         Bonus tiles already collected.
        ron:             True if won by discard (荣和), False if self-draw (自摸).

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

    if not declared_melds:
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
    if (all_groups
            and all(all(_h_is_terminal_or_honor(t) for t in g['tiles']) for g in all_groups)
            and _h_is_terminal_or_honor(pair_tile)):
        add('混幺九', 'Mixed Terminals & Honors', 2)

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

    total = sum(x['fan'] for x in breakdown)
    return {'breakdown': breakdown, 'total': total}
