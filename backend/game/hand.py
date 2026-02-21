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

    # Special case: seven pairs (not standard but common variant)
    # Uncomment to enable:
    # if _is_seven_pairs(sorted_tiles):
    #     return True

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
