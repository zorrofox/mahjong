"""Tests for game/tiles.py — deck building, shuffling, and tile utility functions."""

import pytest
from collections import Counter
from game.tiles import (
    build_deck,
    shuffle_deck,
    is_suit_tile,
    is_honor_tile,
    is_flower_tile,
    get_suit,
    get_number,
    TileType,
    SUITS,
    WIND_TILES,
    DRAGON_TILES,
    HONOR_TILES,
    FLOWER_TILES,
    SEASON_TILES,
    BONUS_TILES,
)


class TestBuildDeck:
    def test_deck_has_144_tiles(self):
        deck = build_deck()
        assert len(deck) == 144

    def test_bamboo_count(self):
        deck = build_deck()
        bamboo = [t for t in deck if t.startswith("BAMBOO_")]
        assert len(bamboo) == 36  # 9 numbers * 4 copies

    def test_circles_count(self):
        deck = build_deck()
        circles = [t for t in deck if t.startswith("CIRCLES_")]
        assert len(circles) == 36

    def test_characters_count(self):
        deck = build_deck()
        chars = [t for t in deck if t.startswith("CHARACTERS_")]
        assert len(chars) == 36

    def test_wind_count(self):
        deck = build_deck()
        winds = [t for t in deck if t in WIND_TILES]
        assert len(winds) == 16  # 4 winds * 4 copies

    def test_dragon_count(self):
        deck = build_deck()
        dragons = [t for t in deck if t in DRAGON_TILES]
        assert len(dragons) == 12  # 3 dragons * 4 copies

    def test_flower_count(self):
        deck = build_deck()
        flowers = [t for t in deck if t in FLOWER_TILES]
        assert len(flowers) == 4  # 4 unique flowers * 1 copy each

    def test_season_count(self):
        deck = build_deck()
        seasons = [t for t in deck if t in SEASON_TILES]
        assert len(seasons) == 4  # 4 unique seasons * 1 copy each

    def test_each_suit_tile_appears_4_times(self):
        deck = build_deck()
        counts = Counter(deck)
        for suit in SUITS:
            for num in range(1, 10):
                tile = f"{suit}_{num}"
                assert counts[tile] == 4, f"{tile} should appear 4 times"

    def test_each_wind_appears_4_times(self):
        deck = build_deck()
        counts = Counter(deck)
        for wind in WIND_TILES:
            assert counts[wind] == 4

    def test_each_dragon_appears_4_times(self):
        deck = build_deck()
        counts = Counter(deck)
        for dragon in DRAGON_TILES:
            assert counts[dragon] == 4

    def test_each_flower_appears_once(self):
        deck = build_deck()
        counts = Counter(deck)
        for flower in FLOWER_TILES:
            assert counts[flower] == 1

    def test_each_season_appears_once(self):
        deck = build_deck()
        counts = Counter(deck)
        for season in SEASON_TILES:
            assert counts[season] == 1

    def test_deck_is_not_shuffled(self):
        """Two consecutive build_deck calls return the same order."""
        assert build_deck() == build_deck()


class TestShuffleDeck:
    def test_shuffle_preserves_tiles(self):
        deck = build_deck()
        shuffled = shuffle_deck(deck)
        assert sorted(shuffled) == sorted(deck)

    def test_shuffle_returns_new_list(self):
        deck = build_deck()
        shuffled = shuffle_deck(deck)
        assert shuffled is not deck

    def test_shuffle_does_not_modify_original(self):
        deck = build_deck()
        original = list(deck)
        shuffle_deck(deck)
        assert deck == original

    def test_shuffle_changes_order(self):
        """At least one of several shuffles should differ from canonical order."""
        deck = build_deck()
        # With 144 tiles, the probability of a shuffle matching canonical order is ~0
        different = any(shuffle_deck(deck) != deck for _ in range(5))
        assert different


class TestIsSuitTile:
    @pytest.mark.parametrize("tile", [
        "BAMBOO_1", "BAMBOO_9", "CIRCLES_5", "CHARACTERS_1",
    ])
    def test_suit_tiles_return_true(self, tile):
        assert is_suit_tile(tile) is True

    @pytest.mark.parametrize("tile", [
        "EAST", "SOUTH", "RED", "GREEN", "WHITE",
        "FLOWER_1", "SEASON_3",
    ])
    def test_non_suit_tiles_return_false(self, tile):
        assert is_suit_tile(tile) is False


class TestIsHonorTile:
    @pytest.mark.parametrize("tile", ["EAST", "SOUTH", "WEST", "NORTH", "RED", "GREEN", "WHITE"])
    def test_honor_tiles_return_true(self, tile):
        assert is_honor_tile(tile) is True

    @pytest.mark.parametrize("tile", ["BAMBOO_1", "CIRCLES_9", "FLOWER_1", "SEASON_4"])
    def test_non_honor_tiles_return_false(self, tile):
        assert is_honor_tile(tile) is False


class TestIsFlowerTile:
    @pytest.mark.parametrize("tile", [
        "FLOWER_1", "FLOWER_2", "FLOWER_3", "FLOWER_4",
        "SEASON_1", "SEASON_2", "SEASON_3", "SEASON_4",
    ])
    def test_bonus_tiles_return_true(self, tile):
        assert is_flower_tile(tile) is True

    @pytest.mark.parametrize("tile", ["BAMBOO_1", "EAST", "RED"])
    def test_non_bonus_tiles_return_false(self, tile):
        assert is_flower_tile(tile) is False


class TestGetSuit:
    @pytest.mark.parametrize("tile,expected", [
        ("BAMBOO_3", "BAMBOO"),
        ("CIRCLES_7", "CIRCLES"),
        ("CHARACTERS_1", "CHARACTERS"),
    ])
    def test_suit_tiles(self, tile, expected):
        assert get_suit(tile) == expected

    @pytest.mark.parametrize("tile", ["EAST", "RED", "FLOWER_1", "SEASON_2"])
    def test_non_suit_tiles_return_none(self, tile):
        assert get_suit(tile) is None


class TestGetNumber:
    @pytest.mark.parametrize("tile,expected", [
        ("BAMBOO_1", 1),
        ("CIRCLES_9", 9),
        ("CHARACTERS_5", 5),
    ])
    def test_suit_tile_numbers(self, tile, expected):
        assert get_number(tile) == expected

    @pytest.mark.parametrize("tile,expected", [
        ("FLOWER_1", 1),
        ("FLOWER_4", 4),
        ("SEASON_2", 2),
    ])
    def test_flower_season_numbers(self, tile, expected):
        assert get_number(tile) == expected

    @pytest.mark.parametrize("tile", ["EAST", "RED", "WHITE"])
    def test_honor_tiles_return_none(self, tile):
        assert get_number(tile) is None


class TestTileType:
    def test_all_suit_values_exist(self):
        for suit in SUITS:
            for num in range(1, 10):
                assert hasattr(TileType, f"{suit}_{num}")

    def test_wind_values_exist(self):
        for wind in ["EAST", "SOUTH", "WEST", "NORTH"]:
            assert hasattr(TileType, wind)

    def test_dragon_values_exist(self):
        for dragon in ["RED", "GREEN", "WHITE"]:
            assert hasattr(TileType, dragon)

    def test_flower_values_exist(self):
        for i in range(1, 5):
            assert hasattr(TileType, f"FLOWER_{i}")

    def test_season_values_exist(self):
        for i in range(1, 5):
            assert hasattr(TileType, f"SEASON_{i}")
