"""Tests for game/hand.py — winning hand detection and meld/claim checks."""

import pytest
from game.hand import (
    is_winning_hand,
    is_winning_hand_given_melds,
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

    def test_chow_kanchan_exact(self):
        """坎张: only 4-5-6 possible when hand contains just 4 and 6."""
        result = can_chow(["BAMBOO_4", "BAMBOO_6"], "BAMBOO_5")
        assert len(result) == 1
        assert sorted(result[0]) == ["BAMBOO_4", "BAMBOO_5", "BAMBOO_6"]

    def test_chow_tile_2_yields_two_options(self):
        """Tile 2 at most 2 combos: 1-2-3 and 2-3-4 (offset-2 combo out of range)."""
        result = can_chow(["BAMBOO_1", "BAMBOO_3", "BAMBOO_3", "BAMBOO_4"], "BAMBOO_2")
        assert len(result) == 2
        combos = [sorted(c) for c in result]
        assert ["BAMBOO_1", "BAMBOO_2", "BAMBOO_3"] in combos
        assert ["BAMBOO_2", "BAMBOO_3", "BAMBOO_4"] in combos

    def test_chow_tile_8_yields_two_options(self):
        """Tile 8 at most 2 combos: 6-7-8 and 7-8-9 (offset-0 combo out of range)."""
        result = can_chow(["BAMBOO_6", "BAMBOO_7", "BAMBOO_7", "BAMBOO_9"], "BAMBOO_8")
        assert len(result) == 2
        combos = [sorted(c) for c in result]
        assert ["BAMBOO_6", "BAMBOO_7", "BAMBOO_8"] in combos
        assert ["BAMBOO_7", "BAMBOO_8", "BAMBOO_9"] in combos

    def test_chow_1_correct_sequence(self):
        """Edge low: BAMBOO_1-2-3 is the only valid sequence, not 0-1-2."""
        result = can_chow(["BAMBOO_2", "BAMBOO_3"], "BAMBOO_1")
        assert len(result) == 1
        assert sorted(result[0]) == ["BAMBOO_1", "BAMBOO_2", "BAMBOO_3"]

    def test_chow_9_correct_sequence(self):
        """Edge high: BAMBOO_7-8-9 is the only valid sequence, not 8-9-10."""
        result = can_chow(["BAMBOO_7", "BAMBOO_8"], "BAMBOO_9")
        assert len(result) == 1
        assert sorted(result[0]) == ["BAMBOO_7", "BAMBOO_8", "BAMBOO_9"]


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


# ============================================================
# Tests for #1 fix: Seven Pairs now legal in is_winning_hand
# ============================================================

class TestSevenPairsWinningHand:
    """Verify seven pairs (七對) is now accepted by is_winning_hand."""

    def test_seven_pairs_is_winning_hand(self):
        """A hand of 7 distinct pairs must be a valid winning hand."""
        tiles = (
            ["BAMBOO_1"] * 2
            + ["BAMBOO_3"] * 2
            + ["CIRCLES_5"] * 2
            + ["CHARACTERS_7"] * 2
            + ["EAST"] * 2
            + ["RED"] * 2
            + ["BAMBOO_9"] * 2
        )
        assert is_winning_hand(tiles) is True

    def test_all_honour_seven_pairs(self):
        """Seven pairs from honour tiles only is also a valid winning hand."""
        tiles = (
            ["EAST"] * 2 + ["SOUTH"] * 2 + ["WEST"] * 2 + ["NORTH"] * 2
            + ["RED"] * 2 + ["GREEN"] * 2 + ["WHITE"] * 2
        )
        assert is_winning_hand(tiles) is True

    def test_duplicate_pair_is_not_seven_pairs(self):
        """Four copies of one tile does NOT form seven pairs (only 6 distinct types)."""
        tiles = (
            ["BAMBOO_1"] * 4        # 4-of-a-kind, not two separate pairs
            + ["BAMBOO_3"] * 2
            + ["CIRCLES_5"] * 2
            + ["CHARACTERS_7"] * 2
            + ["EAST"] * 2
            + ["RED"] * 2
        )
        # 14 tiles but only 6 distinct types → not seven pairs, and not 4+1 either
        assert is_winning_hand(tiles) is False

    def test_seven_pairs_calculate_han_gives_3(self):
        """Seven pairs hand must receive the 七對 +3 fan bonus."""
        from game.hand import calculate_han
        tiles = (
            ["BAMBOO_1"] * 2 + ["BAMBOO_3"] * 2 + ["CIRCLES_5"] * 2
            + ["CHARACTERS_7"] * 2 + ["EAST"] * 2 + ["RED"] * 2
            + ["BAMBOO_9"] * 2
        )
        result = calculate_han(tiles, [], [], ron=False)
        names = [item['name_cn'] for item in result['breakdown']]
        assert '七对' in names
        fan = next(item['fan'] for item in result['breakdown'] if item['name_cn'] == '七对')
        assert fan == 3


# ============================================================
# Tests for rule fixes #4, #5, #8, #9, #12
# ============================================================

class TestHunYaoJiuFanValue:
    """#4: 混幺九 must be worth +3 fan, not +2."""

    def test_hun_yao_jiu_is_3_fan(self):
        from game.hand import calculate_han
        # All-pung hand of terminals and honours
        tiles = (
            ["BAMBOO_1"] * 3 + ["CIRCLES_9"] * 3 + ["EAST"] * 3
            + ["NORTH", "NORTH"]
        )
        melds = [["CHARACTERS_9", "CHARACTERS_9", "CHARACTERS_9"]]
        result = calculate_han(tiles, melds, [], ron=True)
        item = next((x for x in result['breakdown'] if x['name_cn'] == '混幺九'), None)
        assert item is not None, "混幺九 not found in breakdown"
        assert item['fan'] == 3


class TestMenQingRonOnly:
    """#5: 门清 bonus applies only to ron wins, not tsumo."""

    _CONCEALED_HAND = [
        "BAMBOO_2", "BAMBOO_3", "BAMBOO_4",
        "CIRCLES_5", "CIRCLES_6", "CIRCLES_7",
        "CHARACTERS_2", "CHARACTERS_3", "CHARACTERS_4",
        "BAMBOO_6", "BAMBOO_7", "BAMBOO_8",
        "EAST", "EAST",
    ]

    def test_men_qing_awarded_on_ron(self):
        from game.hand import calculate_han
        result = calculate_han(self._CONCEALED_HAND, [], [], ron=True)
        names = [x['name_cn'] for x in result['breakdown']]
        assert '门清' in names

    def test_men_qing_not_awarded_on_tsumo(self):
        from game.hand import calculate_han
        result = calculate_han(self._CONCEALED_HAND, [], [], ron=False)
        names = [x['name_cn'] for x in result['breakdown']]
        assert '门清' not in names
        assert '自摸' in names


class TestLingShang:
    """#8: 嶺上開花 — winning on a kong replacement tile gives +1 fan."""

    _WINNING_HAND = [
        "BAMBOO_1", "BAMBOO_2", "BAMBOO_3",
        "CIRCLES_4", "CIRCLES_5", "CIRCLES_6",
        "CHARACTERS_7", "CHARACTERS_8", "CHARACTERS_9",
        "BAMBOO_4", "BAMBOO_5", "BAMBOO_6",
        "EAST", "EAST",
    ]

    def test_ling_shang_adds_1_fan(self):
        from game.hand import calculate_han
        result = calculate_han(self._WINNING_HAND, [], [], ron=False, ling_shang=True)
        names = [x['name_cn'] for x in result['breakdown']]
        assert '嶺上開花' in names
        fan = next(x['fan'] for x in result['breakdown'] if x['name_cn'] == '嶺上開花')
        assert fan == 1

    def test_ling_shang_not_awarded_on_ron(self):
        from game.hand import calculate_han
        # ling_shang=True but ron=True → should NOT give the bonus
        result = calculate_han(self._WINNING_HAND, [], [], ron=True, ling_shang=True)
        names = [x['name_cn'] for x in result['breakdown']]
        assert '嶺上開花' not in names


class TestSeatFlower:
    """#9: 本命花 — collecting a matching seat flower gives +1 fan each."""

    _BASE_HAND = [
        "BAMBOO_2", "BAMBOO_3", "BAMBOO_4",
        "CIRCLES_5", "CIRCLES_6", "CIRCLES_7",
        "CHARACTERS_2", "CHARACTERS_3", "CHARACTERS_4",
        "BAMBOO_5", "BAMBOO_6", "BAMBOO_7",
        "EAST", "EAST",
    ]

    def test_seat_flower_awards_1_fan(self):
        from game.hand import calculate_han
        # Seat 0 (East); FLOWER_1 is East's seat flower
        result = calculate_han(self._BASE_HAND, [], ["FLOWER_1"], ron=True, player_seat=0)
        names = [x['name_cn'] for x in result['breakdown']]
        assert '本命花' in names

    def test_two_seat_flowers_award_2_fan_total(self):
        from game.hand import calculate_han
        result = calculate_han(
            self._BASE_HAND, [], ["FLOWER_1", "SEASON_1"],
            ron=True, player_seat=0,
        )
        seat_fan = sum(x['fan'] for x in result['breakdown'] if x['name_cn'] == '本命花')
        assert seat_fan == 2

    def test_non_seat_flower_not_awarded(self):
        from game.hand import calculate_han
        # Seat 0 (East); FLOWER_2 belongs to South (seat 1) → no 本命花
        result = calculate_han(self._BASE_HAND, [], ["FLOWER_2"], ron=True, player_seat=0)
        names = [x['name_cn'] for x in result['breakdown']]
        assert '本命花' not in names


class TestWindPungs:
    """#12: 自风碰 and 圈风碰 each give +1 fan."""

    def _make_east_pung_hand(self):
        """Concealed hand: 3 chows + pung of EAST + pair."""
        return (
            ["BAMBOO_2", "BAMBOO_3", "BAMBOO_4"]
            + ["CIRCLES_5", "CIRCLES_6", "CIRCLES_7"]
            + ["CHARACTERS_2", "CHARACTERS_3", "CHARACTERS_4"]
            + ["EAST", "EAST", "EAST"]
            + ["BAMBOO_5", "BAMBOO_5"]
        )

    def test_seat_wind_pung_gives_1_fan(self):
        from game.hand import calculate_han
        # Seat 0 = East; pung of EAST = seat wind pung
        result = calculate_han(self._make_east_pung_hand(), [], [], ron=True, player_seat=0)
        names = [x['name_cn'] for x in result['breakdown']]
        assert '自风碰' in names

    def test_round_wind_pung_gives_1_fan(self):
        from game.hand import calculate_han
        # Round wind = East (idx 0); pung of EAST = round wind pung for any player
        result = calculate_han(
            self._make_east_pung_hand(), [], [],
            ron=True, player_seat=1, round_wind_idx=0,
        )
        names = [x['name_cn'] for x in result['breakdown']]
        assert '圈风碰' in names

    def test_east_player_east_round_gets_double_bonus(self):
        from game.hand import calculate_han
        # Seat 0 = East, Round = East → both 自风碰 and 圈风碰
        result = calculate_han(
            self._make_east_pung_hand(), [], [],
            ron=True, player_seat=0, round_wind_idx=0,
        )
        names = [x['name_cn'] for x in result['breakdown']]
        assert '自风碰' in names
        assert '圈风碰' in names

    def test_non_wind_player_no_seat_bonus(self):
        from game.hand import calculate_han
        # Seat 1 = South; pung of EAST ≠ seat wind → no 自风碰
        result = calculate_han(
            self._make_east_pung_hand(), [], [],
            ron=True, player_seat=1, round_wind_idx=1,
        )
        names = [x['name_cn'] for x in result['breakdown']]
        assert '自风碰' not in names
        assert '圈风碰' not in names


# ---------------------------------------------------------------------------
# Edge case: 七对 combined with flush fans
# ---------------------------------------------------------------------------


class TestSevenPairsFlushCombinations:
    """七对 can combine with 清一色 / 混一色 / 字一色 for extra fan."""

    from game.hand import calculate_han  # noqa: F401 (used in methods)

    # 7 distinct pairs all in bamboo suit (清一色 qualifies)
    _BAMBOO_7PAIRS = (
        ["BAMBOO_1"] * 2 + ["BAMBOO_2"] * 2 + ["BAMBOO_3"] * 2 +
        ["BAMBOO_4"] * 2 + ["BAMBOO_5"] * 2 + ["BAMBOO_6"] * 2 +
        ["BAMBOO_7"] * 2
    )
    # 7 pairs: mixed bamboo + honor tiles (混一色 qualifies)
    _MIXED_7PAIRS = (
        ["BAMBOO_1"] * 2 + ["BAMBOO_3"] * 2 + ["BAMBOO_5"] * 2 +
        ["EAST"] * 2 + ["SOUTH"] * 2 + ["WEST"] * 2 + ["NORTH"] * 2
    )
    # 7 pairs: all wind/dragon tiles (字一色 qualifies)
    _HONORS_7PAIRS = (
        ["EAST"] * 2 + ["SOUTH"] * 2 + ["WEST"] * 2 + ["NORTH"] * 2 +
        ["RED"] * 2 + ["GREEN"] * 2 + ["WHITE"] * 2
    )

    def test_seven_pairs_plus_full_flush(self):
        """七对 + 清一色 both awarded (+3 and +7)."""
        from game.hand import calculate_han
        result = calculate_han(self._BAMBOO_7PAIRS, [], [], ron=True)
        fan_map = {x['name_cn']: x['fan'] for x in result['breakdown']}
        assert '七对' in fan_map and fan_map['七对'] == 3
        assert '清一色' in fan_map and fan_map['清一色'] == 7

    def test_seven_pairs_plus_half_flush(self):
        """七对 + 混一色 both awarded (+3 and +3)."""
        from game.hand import calculate_han
        result = calculate_han(self._MIXED_7PAIRS, [], [], ron=True)
        fan_map = {x['name_cn']: x['fan'] for x in result['breakdown']}
        assert '七对' in fan_map
        assert '混一色' in fan_map and fan_map['混一色'] == 3

    def test_seven_pairs_plus_all_honors(self):
        """七对 + 字一色 both awarded (+3 and +7)."""
        from game.hand import calculate_han
        result = calculate_han(self._HONORS_7PAIRS, [], [], ron=True)
        fan_map = {x['name_cn']: x['fan'] for x in result['breakdown']}
        assert '七对' in fan_map
        assert '字一色' in fan_map and fan_map['字一色'] == 7

    def test_seven_pairs_does_not_trigger_all_pungs(self):
        """七对 hand must NOT also be awarded 碰碰胡 (they are mutually exclusive)."""
        from game.hand import calculate_han
        result = calculate_han(self._BAMBOO_7PAIRS, [], [], ron=True)
        names = [x['name_cn'] for x in result['breakdown']]
        assert '碰碰胡' not in names

    def test_seven_pairs_total_fan_full_flush(self):
        """Total for 七对+清一色 ron (no flowers): 基本分1+无花1+门清1+七对3+清一色7 = 13."""
        from game.hand import calculate_han
        result = calculate_han(self._BAMBOO_7PAIRS, [], [], ron=True)
        assert result['total'] == 13  # 基本分+无花+门清+七对+清一色

    def test_seven_pairs_with_seat_flower(self):
        """七对子 + 本命花：本命花应计入（与手牌结构无关）。
        基本分1+无花0+门清1+七对3+本命花1 = 6
        （有花牌则无花不计；荣和且无副露才计门清）
        """
        from game.hand import calculate_han
        # seat 0 (East); FLOWER_1 is East's seat flower
        result = calculate_han(
            self._BAMBOO_7PAIRS, [], ["FLOWER_1"], ron=True, player_seat=0
        )
        names = [x['name_cn'] for x in result['breakdown']]
        assert '七对' in names
        assert '本命花' in names
        seat_fan = next(x['fan'] for x in result['breakdown'] if x['name_cn'] == '本命花')
        assert seat_fan == 1

    def test_seven_pairs_with_two_seat_flowers(self):
        """七对子 + 本命花 2 张：本命花合计 +2 番。"""
        from game.hand import calculate_han
        # seat 0: FLOWER_1 + SEASON_1 → 2 seat flowers
        result = calculate_han(
            self._BAMBOO_7PAIRS, [], ["FLOWER_1", "SEASON_1"], ron=True, player_seat=0
        )
        names = [x['name_cn'] for x in result['breakdown']]
        assert '七对' in names
        assert '本命花' in names
        seat_fan = next(x['fan'] for x in result['breakdown'] if x['name_cn'] == '本命花')
        assert seat_fan == 2

    def test_seven_pairs_non_seat_flower_not_counted(self):
        """七对子持有非本座花牌时，不计本命花。"""
        from game.hand import calculate_han
        # seat 0 (East); FLOWER_2 belongs to South (seat 1)
        result = calculate_han(
            self._BAMBOO_7PAIRS, [], ["FLOWER_2"], ron=True, player_seat=0
        )
        names = [x['name_cn'] for x in result['breakdown']]
        assert '本命花' not in names


# ---------------------------------------------------------------------------
# Edge case: lingshang_pending flag lifecycle
# ---------------------------------------------------------------------------


class TestLingShangPendingInGameState:
    """Test that lingshang_pending is set and cleared at the right moments."""

    def _state_with_kong(self):
        """Return a GameState where player 0 can perform a concealed kong."""
        from game.game_state import GameState
        gs = GameState(room_id="ls-test", player_ids=["p0", "p1", "p2", "p3"])
        gs.players[0].hand = (
            ["BAMBOO_1"] * 4          # will kong
            + ["BAMBOO_2", "BAMBOO_3", "BAMBOO_4",
               "CIRCLES_5", "CIRCLES_6", "CIRCLES_7",
               "EAST", "EAST", "SOUTH"]   # 9 more tiles
        )
        for i in range(1, 4):
            gs.players[i].hand = ["CHARACTERS_1"] * 13
        gs.phase = "discarding"
        gs.current_turn = 0
        gs.last_drawn_tile = "BAMBOO_1"
        # Put tiles in wall so kong replacement works
        gs.wall = ["CHARACTERS_2"] * 10
        return gs

    def test_lingshang_pending_set_after_concealed_kong(self):
        """After player declares a concealed kong, lingshang_pending becomes True."""
        gs = self._state_with_kong()
        assert gs.lingshang_pending is False
        gs.claim_kong(0, "BAMBOO_1")
        assert gs.lingshang_pending is True

    def test_lingshang_pending_cleared_after_discard(self):
        """lingshang_pending resets to False when the player discards."""
        gs = self._state_with_kong()
        gs.claim_kong(0, "BAMBOO_1")
        assert gs.lingshang_pending is True
        # Player discards any tile from hand (not a kong'd tile)
        gs.discard_tile(0, "EAST")
        assert gs.lingshang_pending is False


# ---------------------------------------------------------------------------
# Edge case: bonus tile chain (花牌连续)
# ---------------------------------------------------------------------------


class TestBonusTileChain:
    """_collect_bonus_tiles should handle consecutive bonus tiles correctly."""

    def _make_gs(self, wall=None):
        from game.game_state import GameState
        gs = GameState(room_id="btc-test", player_ids=["p0", "p1", "p2", "p3"])
        # Use a controlled wall of plain tiles so replacements are predictable.
        gs.wall = wall if wall is not None else ["BAMBOO_5"] * 20
        return gs

    def test_single_bonus_tile_collected(self):
        """A single flower in hand is moved to flowers and replaced by 1 wall tile."""
        gs = self._make_gs(wall=["CIRCLES_9", "BAMBOO_5"])
        gs.players[0].hand = ["FLOWER_1", "BAMBOO_1", "BAMBOO_2"]
        gs._collect_bonus_tiles(0)
        assert "FLOWER_1" not in gs.players[0].hand
        assert "FLOWER_1" in gs.players[0].flowers
        # 1 replacement drawn → hand stays at 3 non-bonus tiles
        from game.tiles import is_flower_tile
        normal = [t for t in gs.players[0].hand if not is_flower_tile(t)]
        assert len(normal) == 3

    def test_two_bonus_tiles_both_collected(self):
        """Two flowers in hand: both move to flowers, exactly 2 replacements drawn."""
        # Wall is purely plain tiles so no further chaining occurs.
        gs = self._make_gs(wall=["CIRCLES_1", "CIRCLES_2", "CIRCLES_3"])
        gs.players[0].hand = ["FLOWER_1", "FLOWER_2", "BAMBOO_1"]
        wall_before = len(gs.wall)
        gs._collect_bonus_tiles(0)
        assert "FLOWER_1" in gs.players[0].flowers
        assert "FLOWER_2" in gs.players[0].flowers
        assert "FLOWER_1" not in gs.players[0].hand
        assert "FLOWER_2" not in gs.players[0].hand
        assert len(gs.wall) == wall_before - 2

    def test_bonus_chain_replacement_also_bonus(self):
        """If replacement tile is also a flower, that flower is also collected."""
        # wall[-1] is drawn first: FLOWER_3 → then BAMBOO_5
        gs = self._make_gs(wall=["BAMBOO_5", "FLOWER_3"])
        gs.players[0].hand = ["FLOWER_1", "BAMBOO_1"]
        gs._collect_bonus_tiles(0)
        # FLOWER_1 collected → FLOWER_3 drawn → FLOWER_3 collected → BAMBOO_5 drawn
        assert "FLOWER_1" in gs.players[0].flowers
        assert "FLOWER_3" in gs.players[0].flowers
        from game.tiles import is_flower_tile
        normal = [t for t in gs.players[0].hand if not is_flower_tile(t)]
        assert sorted(normal) == ["BAMBOO_1", "BAMBOO_5"]
        assert len(gs.wall) == 0


class TestIsWinningHandGivenMelds:
    """回归测试：副露锁定后不得将副露牌重新混入手牌进行胡牌判断。

    Bug 场景：is_winning_hand(effective_hand + meld_tiles) 把副露牌当自由牌，
    导致以下情况误判为胡牌：
        已声索吃牌 [B1, B2, B3]，手牌 [B2, B3, B4, B5, B6, B7, B8, B9x4]
    自由组合会借用吃牌里的 B2 配对，实为不合法胡牌。
    """

    def test_false_positive_with_pung_meld_regression(self):
        """主回归用例：副露碰牌 [B3,B3,B3]，手牌含 1 张 B3。

        旧方法把副露的两张 B3 借用到手牌做顺子，使总牌池凑成胡牌型（假阳性）：
          pair B3(1手+1副露) + 顺B1-B2-B3(2手+1副露) + 顺B3-B4-B5? ← 不对
          实际上：pair B3 + 顺B1-B2-B3 + 顺B3-B4-B5 + 顺B6-B7-B8 + 刻B8
          这借用了副露里的 B3，属非法分解。

        正确判断：碰牌 [B3,B3,B3] 锁定后，手牌 [B1..B8, B8x4] 中
        只有 B8 可对，剩余 9 张无法凑成 3 副顺/刻。
        """
        hand = [
            "BAMBOO_1", "BAMBOO_2", "BAMBOO_3", "BAMBOO_4", "BAMBOO_5",
            "BAMBOO_6", "BAMBOO_7", "BAMBOO_8", "BAMBOO_8", "BAMBOO_8", "BAMBOO_8",
        ]
        declared_pung = ["BAMBOO_3", "BAMBOO_3", "BAMBOO_3"]

        # 旧方法（副露自由混入）产生假阳性
        old_check = is_winning_hand(hand + declared_pung)
        assert old_check is True, "证明旧方法确实产生假阳性"

        # 正确判断（副露锁定）：不能胡
        assert is_winning_hand_given_melds(hand, n_declared_melds=1) is False

    def test_no_melds_equivalent_to_is_winning_hand(self):
        """无副露时，两个函数结果应完全一致。"""
        winning = (
            ["BAMBOO_1"] * 2
            + ["BAMBOO_2", "BAMBOO_3", "BAMBOO_4"]
            + ["BAMBOO_5", "BAMBOO_6", "BAMBOO_7"]
            + ["BAMBOO_8", "BAMBOO_9", "BAMBOO_9", "BAMBOO_9"]
            + ["CIRCLES_1"]
        )
        # 14 张合法手牌
        assert is_winning_hand(winning) == is_winning_hand_given_melds(winning, 0)

    def test_valid_win_with_pung_meld_accepted(self):
        """有碰牌副露时，合法胡型应被接受。"""
        # 副露：碰 BAMBOO_9（3 张）
        # 手牌 11 张 = 对 + 3 副顺子
        hand = [
            "BAMBOO_1", "BAMBOO_2", "BAMBOO_3",
            "BAMBOO_4", "BAMBOO_5", "BAMBOO_6",
            "BAMBOO_7", "BAMBOO_8", "BAMBOO_8",
            "BAMBOO_8", "BAMBOO_8",
        ]
        # 对 B8 + 顺 1-2-3 + 顺 4-5-6 + 顺 7-8-8 — 不合法
        # 重新构造合法手牌：对 B1 + 顺 2-3-4 + 顺 5-6-7 + 顺 ... 需要12张，不对
        # 用正规 11 张：对 + 3 副刻/顺
        hand2 = (
            ["BAMBOO_1", "BAMBOO_1"]       # 对
            + ["BAMBOO_2", "BAMBOO_3", "BAMBOO_4"]  # 顺
            + ["BAMBOO_5", "BAMBOO_6", "BAMBOO_7"]  # 顺
            + ["BAMBOO_7", "BAMBOO_8", "BAMBOO_9"]  # 顺
        )
        assert is_winning_hand_given_melds(hand2, n_declared_melds=1) is True

    def test_two_melds_win(self):
        """2 副副露时，手牌 8 张 = 对 + 2 副顺子，应判胡。"""
        hand = (
            ["CIRCLES_1", "CIRCLES_1"]           # 对
            + ["CIRCLES_2", "CIRCLES_3", "CIRCLES_4"]  # 顺
            + ["CIRCLES_5", "CIRCLES_6", "CIRCLES_7"]  # 顺
        )
        assert is_winning_hand_given_melds(hand, n_declared_melds=2) is True

    def test_seven_pairs_no_melds(self):
        """七对（无副露）应被接受。"""
        hand = [
            "BAMBOO_1", "BAMBOO_1",
            "BAMBOO_3", "BAMBOO_3",
            "BAMBOO_5", "BAMBOO_5",
            "BAMBOO_7", "BAMBOO_7",
            "CIRCLES_2", "CIRCLES_2",
            "CHARACTERS_4", "CHARACTERS_4",
            "EAST", "EAST",
        ]
        assert is_winning_hand_given_melds(hand, n_declared_melds=0) is True

    def test_seven_pairs_rejected_with_melds(self):
        """有副露时七对不合法（手牌不足 14 张）。"""
        hand = [
            "BAMBOO_1", "BAMBOO_1",
            "BAMBOO_3", "BAMBOO_3",
            "BAMBOO_5", "BAMBOO_5",
            "BAMBOO_7", "BAMBOO_7",
            "CIRCLES_2", "CIRCLES_2",
            "CHARACTERS_4",
        ]  # 11 张，非七对
        assert is_winning_hand_given_melds(hand, n_declared_melds=1) is False

    def test_wrong_tile_count_rejected(self):
        """瓦数不符（副露数 × 3 + 手牌 ≠ 14）应直接返回 False。"""
        hand = ["BAMBOO_1"] * 12  # 应为 11 张（1 副副露）
        assert is_winning_hand_given_melds(hand, n_declared_melds=1) is False
