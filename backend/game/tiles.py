"""
tiles.py - Mahjong tile definitions, deck builder, and tile utility functions.

Tile string format:
  Suit tiles:   "BAMBOO_1" .. "BAMBOO_9"
                "CIRCLES_1" .. "CIRCLES_9"
                "CHARACTERS_1" .. "CHARACTERS_9"
  Wind tiles:   "EAST", "SOUTH", "WEST", "NORTH"
  Dragon tiles: "RED", "GREEN", "WHITE"
  Flowers:      "FLOWER_1" .. "FLOWER_4"
  Seasons:      "SEASON_1" .. "SEASON_4"

Standard 144-tile deck:
  36 bamboo + 36 circles + 36 characters (each number 1-9 x4)
  16 winds (each x4)
  12 dragons (each x4)
  8 flowers/seasons (each x1)
"""

import random
from enum import Enum
from typing import Optional


class TileType(Enum):
    # Bamboo suit (1-9)
    BAMBOO_1 = "BAMBOO_1"
    BAMBOO_2 = "BAMBOO_2"
    BAMBOO_3 = "BAMBOO_3"
    BAMBOO_4 = "BAMBOO_4"
    BAMBOO_5 = "BAMBOO_5"
    BAMBOO_6 = "BAMBOO_6"
    BAMBOO_7 = "BAMBOO_7"
    BAMBOO_8 = "BAMBOO_8"
    BAMBOO_9 = "BAMBOO_9"

    # Circles suit (1-9)
    CIRCLES_1 = "CIRCLES_1"
    CIRCLES_2 = "CIRCLES_2"
    CIRCLES_3 = "CIRCLES_3"
    CIRCLES_4 = "CIRCLES_4"
    CIRCLES_5 = "CIRCLES_5"
    CIRCLES_6 = "CIRCLES_6"
    CIRCLES_7 = "CIRCLES_7"
    CIRCLES_8 = "CIRCLES_8"
    CIRCLES_9 = "CIRCLES_9"

    # Characters suit (1-9)
    CHARACTERS_1 = "CHARACTERS_1"
    CHARACTERS_2 = "CHARACTERS_2"
    CHARACTERS_3 = "CHARACTERS_3"
    CHARACTERS_4 = "CHARACTERS_4"
    CHARACTERS_5 = "CHARACTERS_5"
    CHARACTERS_6 = "CHARACTERS_6"
    CHARACTERS_7 = "CHARACTERS_7"
    CHARACTERS_8 = "CHARACTERS_8"
    CHARACTERS_9 = "CHARACTERS_9"

    # Wind tiles
    EAST = "EAST"
    SOUTH = "SOUTH"
    WEST = "WEST"
    NORTH = "NORTH"

    # Dragon tiles
    RED = "RED"
    GREEN = "GREEN"
    WHITE = "WHITE"

    # Flower tiles (each appears once)
    FLOWER_1 = "FLOWER_1"
    FLOWER_2 = "FLOWER_2"
    FLOWER_3 = "FLOWER_3"
    FLOWER_4 = "FLOWER_4"

    # Season tiles (each appears once)
    SEASON_1 = "SEASON_1"
    SEASON_2 = "SEASON_2"
    SEASON_3 = "SEASON_3"
    SEASON_4 = "SEASON_4"


# Ordered suit names for sequence detection
SUITS = ("BAMBOO", "CIRCLES", "CHARACTERS")

# Wind and dragon tiles considered "honor" tiles
WIND_TILES = frozenset({"EAST", "SOUTH", "WEST", "NORTH"})
DRAGON_TILES = frozenset({"RED", "GREEN", "WHITE"})
HONOR_TILES = WIND_TILES | DRAGON_TILES

# Flower and season tiles
FLOWER_TILES = frozenset({"FLOWER_1", "FLOWER_2", "FLOWER_3", "FLOWER_4"})
SEASON_TILES = frozenset({"SEASON_1", "SEASON_2", "SEASON_3", "SEASON_4"})
BONUS_TILES = FLOWER_TILES | SEASON_TILES


def build_deck(ruleset: str = "hk") -> list[str]:
    """
    Build a standard Mahjong deck.

    Args:
        ruleset: "hk" for Hong Kong rules (144 tiles, includes flowers/seasons),
                 "dalian" for Dalian Qionghu rules (136 tiles, no flowers/seasons).

    Returns:
        A list of tile strings in canonical order (not shuffled).
    """
    deck: list[str] = []

    # Suit tiles: 4 copies each of 1-9 for each suit = 108 tiles
    for suit in SUITS:
        for number in range(1, 10):
            tile = f"{suit}_{number}"
            deck.extend([tile] * 4)

    # Wind tiles: 4 copies each = 16 tiles
    for wind in ("EAST", "SOUTH", "WEST", "NORTH"):
        deck.extend([wind] * 4)

    # Dragon tiles: 4 copies each = 12 tiles
    for dragon in ("RED", "GREEN", "WHITE"):
        deck.extend([dragon] * 4)

    if ruleset == "hk":
        # Flower tiles: 1 copy each = 4 tiles
        for i in range(1, 5):
            deck.append(f"FLOWER_{i}")

        # Season tiles: 1 copy each = 4 tiles
        for i in range(1, 5):
            deck.append(f"SEASON_{i}")

        assert len(deck) == 144, f"HK deck should have 144 tiles, got {len(deck)}"
    else:
        # "dalian": no flower/season tiles
        assert len(deck) == 136, f"Dalian deck should have 136 tiles, got {len(deck)}"

    return deck


def shuffle_deck(deck: list[str]) -> list[str]:
    """
    Return a shuffled copy of the given deck.

    Args:
        deck: The original deck list.

    Returns:
        A new list with the same tiles in a randomized order.
    """
    shuffled = list(deck)
    random.shuffle(shuffled)
    return shuffled


def is_suit_tile(tile: str) -> bool:
    """Return True if the tile belongs to bamboo, circles, or characters suit."""
    return any(tile.startswith(suit + "_") for suit in SUITS)


def is_honor_tile(tile: str) -> bool:
    """Return True if the tile is a wind or dragon tile."""
    return tile in HONOR_TILES


def is_flower_tile(tile: str) -> bool:
    """Return True if the tile is a flower or season tile (bonus tile)."""
    return tile in BONUS_TILES


def get_suit(tile: str) -> Optional[str]:
    """
    Return the suit of a suit tile, or None for non-suit tiles.

    Args:
        tile: A tile string.

    Returns:
        One of "BAMBOO", "CIRCLES", "CHARACTERS", or None.
    """
    for suit in SUITS:
        if tile.startswith(suit + "_"):
            return suit
    return None


def get_number(tile: str) -> Optional[int]:
    """
    Return the number of a suit tile, or None for non-suit tiles.

    Args:
        tile: A tile string.

    Returns:
        An integer 1-9, or None if the tile has no number.
    """
    for suit in SUITS:
        if tile.startswith(suit + "_"):
            try:
                return int(tile[len(suit) + 1:])
            except ValueError:
                return None
    # Check flower/season tiles for their number
    for prefix in ("FLOWER_", "SEASON_"):
        if tile.startswith(prefix):
            try:
                return int(tile[len(prefix):])
            except ValueError:
                return None
    return None
