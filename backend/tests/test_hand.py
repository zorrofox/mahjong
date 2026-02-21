"""Tests for game/hand.py — winning hand detection and meld/claim checks."""

import pytest
from game.hand import (
    is_winning_hand,
    can_pung,
    can_kong,
    can_chow,
    find_pairs,
    find_melds,
    _is_seven_pairs,
    _is_pung,
    _is_chow,
    _try_extract_melds,
)


class TestIsWinningHand:
    def test_four_pungs_plus_pair(self):
        """4 pungs + 1 pair = valid winning hand."""
        hand = (
            ["BAMBOO_1"] * 3
            + ["BAMBOO_2"] * 3
            + ["CIRCLES_5"] * 3
            + ["EAST"] * 3
            + ["RED"] * 2
        )
        assert is_winning_hand(hand) is True

    def test_four_chows_plus_pair(self):
        """4 chows + 1 pair = valid winning hand."""
        hand = (
            ["BAMBOO_1", "BAMBOO_2", "BAMBOO_3"]
            + ["BAMBOO_4", "BAMBOO_5", "BAMBOO_6"]
            + ["CIRCLES_1", "CIRCLES_2", "CIRCLES_3"]
            + ["CIRCLES_7", "CIRCLES_8", "CIRCLES_9"]
            + ["EAST", "EAST"]
        )
        assert is_winning_hand(hand) is True

    def test_mixed_pungs_and_chows(self):
        """2 pungs + 2 chows + 1 pair."""
        hand = (
            ["BAMBOO_1"] * 3
            + ["RED"] * 3
            + ["CIRCLES_1", "CIRCLES_2", "CIRCLES_3"]
            + ["CHARACTERS_7", "CHARACTERS_8", "CHARACTERS_9"]
            + ["WEST", "WEST"]
        )
        assert is_winning_hand(hand) is True

    def test_wrong_tile_count(self):
        """13 tiles should not be a winning hand."""
        hand = ["BAMBOO_1"] * 3 + ["BAMBOO_2"] * 3 + ["CIRCLES_5"] * 3 + ["EAST"] * 3 + ["RED"]
        assert is_winning_hand(hand) is False

    def test_15_tiles_not_winning(self):
        hand = ["BAMBOO_1"] * 3 + ["BAMBOO_2"] * 3 + ["CIRCLES_5"] * 3 + ["EAST"] * 3 + ["RED"] * 3
        assert is_winning_hand(hand) is False

    def test_isolated_tiles_not_winning(self):
        """14 totally unrelated tiles."""
        hand = [
            "BAMBOO_1", "BAMBOO_3", "BAMBOO_5", "BAMBOO_7", "BAMBOO_9",
            "CIRCLES_2", "CIRCLES_4", "CIRCLES_6", "CIRCLES_8",
            "CHARACTERS_1", "CHARACTERS_3", "CHARACTERS_5",
            "EAST", "SOUTH",
        ]
        assert is_winning_hand(hand) is False

    def test_bonus_tiles_filtered(self):
        """Bonus tiles in the hand are filtered, leaving fewer than 14 playable tiles."""
        hand = (
            ["BAMBOO_1"] * 3
            + ["BAMBOO_2"] * 3
            + ["CIRCLES_5"] * 3
            + ["EAST"] * 3
            + ["RED", "RED"]
        )
        # Replace one tile with a flower — now only 13 playable tiles
        hand_with_flower = hand[:13] + ["FLOWER_1"]
        assert is_winning_hand(hand_with_flower) is False

    def test_all_same_suit_winning(self):
        """All bamboo winning hand."""
        hand = (
            ["BAMBOO_1", "BAMBOO_2", "BAMBOO_3"]
            + ["BAMBOO_4", "BAMBOO_5", "BAMBOO_6"]
            + ["BAMBOO_7", "BAMBOO_8", "BAMBOO_9"]
            + ["BAMBOO_1"] * 3
            + ["BAMBOO_5", "BAMBOO_5"]
        )
        assert is_winning_hand(hand) is True


class TestSevenPairs:
    """Test the _is_seven_pairs helper (not used in is_winning_hand by default)."""

    def test_valid_seven_pairs(self):
        hand = (
            ["BAMBOO_1"] * 2
            + ["BAMBOO_3"] * 2
            + ["CIRCLES_5"] * 2
            + ["EAST"] * 2
            + ["RED"] * 2
            + ["WEST"] * 2
            + ["CHARACTERS_9"] * 2
        )
        assert _is_seven_pairs(hand) is True

    def test_seven_pairs_wrong_count(self):
        hand = ["BAMBOO_1"] * 2 + ["BAMBOO_3"] * 2 + ["CIRCLES_5"] * 2
        assert _is_seven_pairs(hand) is False

    def test_four_of_a_kind_not_seven_pairs(self):
        """4 copies of one tile means only 6 distinct pair types, not 7."""
        hand = (
            ["BAMBOO_1"] * 4
            + ["BAMBOO_3"] * 2
            + ["CIRCLES_5"] * 2
            + ["EAST"] * 2
            + ["RED"] * 2
            + ["WEST"] * 2
        )
        assert _is_seven_pairs(hand) is False


class TestFindPairs:
    def test_no_pairs(self):
        hand = ["BAMBOO_1", "BAMBOO_2", "BAMBOO_3"]
        assert find_pairs(hand) == []

    def test_one_pair(self):
        hand = ["BAMBOO_1", "BAMBOO_1", "BAMBOO_3"]
        assert find_pairs(hand) == ["BAMBOO_1"]

    def test_multiple_pairs(self):
        hand = ["BAMBOO_1", "BAMBOO_1", "EAST", "EAST"]
        result = find_pairs(hand)
        assert "BAMBOO_1" in result
        assert "EAST" in result

    def test_triplet_counts_as_pair_candidate(self):
        hand = ["BAMBOO_5"] * 3
        assert "BAMBOO_5" in find_pairs(hand)


class TestIsPung:
    def test_valid_pung(self):
        assert _is_pung(["BAMBOO_1", "BAMBOO_1", "BAMBOO_1"]) is True

    def test_invalid_pung_different_tiles(self):
        assert _is_pung(["BAMBOO_1", "BAMBOO_1", "BAMBOO_2"]) is False

    def test_invalid_pung_wrong_count(self):
        assert _is_pung(["BAMBOO_1", "BAMBOO_1"]) is False


class TestIsChow:
    def test_valid_chow(self):
        assert _is_chow(["BAMBOO_1", "BAMBOO_2", "BAMBOO_3"]) is True

    def test_valid_chow_unsorted(self):
        assert _is_chow(["BAMBOO_3", "BAMBOO_1", "BAMBOO_2"]) is True

    def test_invalid_chow_different_suits(self):
        assert _is_chow(["BAMBOO_1", "CIRCLES_2", "BAMBOO_3"]) is False

    def test_invalid_chow_non_consecutive(self):
        assert _is_chow(["BAMBOO_1", "BAMBOO_3", "BAMBOO_5"]) is False

    def test_invalid_chow_honor_tiles(self):
        assert _is_chow(["EAST", "SOUTH", "WEST"]) is False

    def test_invalid_chow_wrong_count(self):
        assert _is_chow(["BAMBOO_1", "BAMBOO_2"]) is False


class TestTryExtractMelds:
    def test_empty_tiles(self):
        assert _try_extract_melds([]) is True

    def test_one_pung(self):
        assert _try_extract_melds(sorted(["BAMBOO_1"] * 3)) is True

    def test_one_chow(self):
        assert _try_extract_melds(sorted(["BAMBOO_1", "BAMBOO_2", "BAMBOO_3"])) is True

    def test_two_melds(self):
        tiles = sorted(["BAMBOO_1"] * 3 + ["CIRCLES_1", "CIRCLES_2", "CIRCLES_3"])
        assert _try_extract_melds(tiles) is True

    def test_cannot_form_melds(self):
        assert _try_extract_melds(sorted(["BAMBOO_1", "BAMBOO_3", "BAMBOO_5"])) is False


class TestCanPung:
    def test_can_pung_with_two_in_hand(self):
        hand = ["BAMBOO_5", "BAMBOO_5", "CIRCLES_1"]
        assert can_pung(hand, "BAMBOO_5") is True

    def test_cannot_pung_with_one_in_hand(self):
        hand = ["BAMBOO_5", "CIRCLES_1", "CIRCLES_2"]
        assert can_pung(hand, "BAMBOO_5") is False

    def test_cannot_pung_with_zero_in_hand(self):
        hand = ["CIRCLES_1", "CIRCLES_2", "CIRCLES_3"]
        assert can_pung(hand, "BAMBOO_5") is False

    def test_can_pung_honor_tile(self):
        hand = ["EAST", "EAST", "BAMBOO_1"]
        assert can_pung(hand, "EAST") is True


class TestCanKong:
    def test_can_kong_with_three_in_hand(self):
        hand = ["BAMBOO_5", "BAMBOO_5", "BAMBOO_5", "CIRCLES_1"]
        assert can_kong(hand, "BAMBOO_5") is True

    def test_cannot_kong_with_two_in_hand(self):
        hand = ["BAMBOO_5", "BAMBOO_5", "CIRCLES_1"]
        assert can_kong(hand, "BAMBOO_5") is False

    def test_can_kong_honor_tile(self):
        hand = ["RED", "RED", "RED"]
        assert can_kong(hand, "RED") is True


class TestCanChow:
    def test_chow_middle(self):
        """Tile completes middle of sequence."""
        hand = ["BAMBOO_1", "BAMBOO_3", "CIRCLES_1"]
        result = can_chow(hand, "BAMBOO_2")
        assert len(result) >= 1
        assert sorted(result[0]) == ["BAMBOO_1", "BAMBOO_2", "BAMBOO_3"]

    def test_chow_low_end(self):
        """Tile is the lowest in the sequence."""
        hand = ["BAMBOO_2", "BAMBOO_3", "CIRCLES_1"]
        result = can_chow(hand, "BAMBOO_1")
        assert any(sorted(c) == ["BAMBOO_1", "BAMBOO_2", "BAMBOO_3"] for c in result)

    def test_chow_high_end(self):
        """Tile is the highest in the sequence."""
        hand = ["BAMBOO_7", "BAMBOO_8", "CIRCLES_1"]
        result = can_chow(hand, "BAMBOO_9")
        assert any(sorted(c) == ["BAMBOO_7", "BAMBOO_8", "BAMBOO_9"] for c in result)

    def test_no_chow_for_honor_tiles(self):
        hand = ["EAST", "SOUTH", "WEST"]
        assert can_chow(hand, "NORTH") == []

    def test_no_chow_when_tiles_missing(self):
        hand = ["BAMBOO_1", "BAMBOO_5", "CIRCLES_1"]
        assert can_chow(hand, "BAMBOO_3") == []

    def test_multiple_chow_options(self):
        """Tile 5 can form [3,4,5], [4,5,6], or [5,6,7]."""
        hand = ["BAMBOO_3", "BAMBOO_4", "BAMBOO_6", "BAMBOO_7"]
        result = can_chow(hand, "BAMBOO_5")
        assert len(result) >= 2

    def test_chow_boundary_tile_1(self):
        """Tile 1 can only be the low end."""
        hand = ["BAMBOO_2", "BAMBOO_3"]
        result = can_chow(hand, "BAMBOO_1")
        assert len(result) == 1

    def test_chow_boundary_tile_9(self):
        """Tile 9 can only be the high end."""
        hand = ["BAMBOO_7", "BAMBOO_8"]
        result = can_chow(hand, "BAMBOO_9")
        assert len(result) == 1


class TestFindMelds:
    def test_find_single_pung(self):
        tiles = ["BAMBOO_1"] * 3
        melds = find_melds(tiles)
        assert len(melds) >= 1

    def test_find_single_chow(self):
        tiles = ["CIRCLES_1", "CIRCLES_2", "CIRCLES_3"]
        melds = find_melds(tiles)
        assert len(melds) >= 1

    def test_empty_hand(self):
        assert find_melds([]) == []
