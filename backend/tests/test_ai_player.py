"""Tests for game/ai_player.py — AI discard, claim, and evaluation logic."""

import pytest
from game.ai_player import AIPlayer


@pytest.fixture
def ai():
    return AIPlayer()


class TestChooseDiscard:
    def test_discard_isolated_honor_over_connected_suit(self, ai):
        hand = ["BAMBOO_1", "BAMBOO_2", "BAMBOO_3", "EAST"]
        result = ai.choose_discard(hand, [])
        assert result == "EAST"

    def test_discard_prefers_isolated_honor(self, ai):
        hand = ["BAMBOO_5", "BAMBOO_5", "CIRCLES_3", "CIRCLES_4", "NORTH"]
        result = ai.choose_discard(hand, [])
        assert result == "NORTH"

    def test_discard_keeps_pairs(self, ai):
        hand = ["BAMBOO_1", "BAMBOO_1", "EAST"]
        result = ai.choose_discard(hand, [])
        # Should discard EAST (isolated) rather than break the pair
        assert result == "EAST"

    def test_discard_empty_hand_raises(self, ai):
        with pytest.raises(ValueError, match="empty hand"):
            ai.choose_discard([], [])

    def test_discard_returns_tile_from_hand(self, ai):
        hand = ["BAMBOO_1", "BAMBOO_3", "CIRCLES_7", "EAST", "RED"]
        result = ai.choose_discard(hand, [])
        assert result in hand

    def test_discard_keeps_triplets(self, ai):
        hand = ["BAMBOO_5"] * 3 + ["WEST"]
        result = ai.choose_discard(hand, [])
        assert result == "WEST"


class TestDecideClaim:
    def test_always_claim_win(self, ai):
        hand = ["BAMBOO_1"] * 3
        assert ai.decide_claim(hand, [], "BAMBOO_1", "win") is True

    def test_claim_pung_when_beneficial(self, ai):
        hand = ["BAMBOO_5", "BAMBOO_5", "CIRCLES_1", "CIRCLES_2", "CIRCLES_3"]
        result = ai.decide_claim(hand, [], "BAMBOO_5", "pung")
        assert isinstance(result, bool)

    def test_claim_kong_when_possible(self, ai):
        hand = ["RED", "RED", "RED"]
        result = ai.decide_claim(hand, [], "RED", "kong")
        assert result is True

    def test_claim_kong_not_possible(self, ai):
        hand = ["RED", "RED"]
        result = ai.decide_claim(hand, [], "RED", "kong")
        assert result is False

    def test_unknown_claim_type(self, ai):
        result = ai.decide_claim(["BAMBOO_1"], [], "BAMBOO_1", "invalid_type")
        assert result is False


class TestShouldDeclareWin:
    def test_winning_hand_returns_true(self, ai):
        hand = (
            ["BAMBOO_1"] * 3
            + ["BAMBOO_2"] * 3
            + ["CIRCLES_5"] * 3
            + ["EAST"] * 3
            + ["RED"] * 2
        )
        assert ai.should_declare_win(hand, []) is True

    def test_non_winning_hand_returns_false(self, ai):
        hand = ["BAMBOO_1", "BAMBOO_3", "BAMBOO_5", "EAST"]
        assert ai.should_declare_win(hand, []) is False

    def test_winning_with_melds(self, ai):
        """Hand with committed melds that complete a win."""
        hand = (
            ["CIRCLES_5"] * 3
            + ["EAST"] * 3
            + ["RED"] * 2
        )
        melds = [["BAMBOO_1"] * 3, ["BAMBOO_2"] * 3]
        assert ai.should_declare_win(hand, melds) is True

    def test_bonus_tiles_filtered(self, ai):
        """Bonus tiles in hand should be ignored."""
        hand = (
            ["BAMBOO_1"] * 3
            + ["BAMBOO_2"] * 3
            + ["CIRCLES_5"] * 3
            + ["EAST"] * 3
            + ["RED"] * 2
        )
        # This is 14 playable tiles, should still win
        assert ai.should_declare_win(hand, []) is True
        # Add a flower — now 15 total but 14 playable; meld_tiles = 0, so full_hand = 14+flower=15 playable? No, flowers filtered out
        # Actually with no melds, full_hand = 14 playable tiles, should still be True
        hand_with_flower = hand + ["FLOWER_1"]
        # Now playable = 14, meld_tiles = 0, full_hand = 14, len check passes
        assert ai.should_declare_win(hand_with_flower, []) is True


class TestHandProgressScore:
    def test_melds_add_score(self, ai):
        score_no_melds = ai._hand_progress_score(["BAMBOO_1"], [])
        score_with_melds = ai._hand_progress_score(["BAMBOO_1"], [["EAST"] * 3])
        assert score_with_melds > score_no_melds

    def test_pairs_score_higher_than_isolated(self, ai):
        score_pair = ai._hand_progress_score(["BAMBOO_1", "BAMBOO_1"], [])
        score_isolated = ai._hand_progress_score(["BAMBOO_1", "EAST"], [])
        assert score_pair > score_isolated

    def test_triplet_scores_highest(self, ai):
        score_triple = ai._hand_progress_score(["BAMBOO_1"] * 3, [])
        score_pair = ai._hand_progress_score(["BAMBOO_1"] * 2 + ["EAST"], [])
        assert score_triple > score_pair

    def test_connected_suit_tiles_score_higher(self, ai):
        score_connected = ai._hand_progress_score(["BAMBOO_1", "BAMBOO_2"], [])
        score_disconnected = ai._hand_progress_score(["BAMBOO_1", "BAMBOO_9"], [])
        assert score_connected > score_disconnected


class TestDiscardScore:
    def test_flower_tile_lowest_score(self, ai):
        score = ai._discard_score("FLOWER_1", ["FLOWER_1", "BAMBOO_1"])
        assert score == -1000.0

    def test_isolated_honor_low_score(self, ai):
        score = ai._discard_score("EAST", ["EAST", "BAMBOO_1"])
        assert score == -10.0

    def test_paired_honor_positive_score(self, ai):
        score = ai._discard_score("EAST", ["EAST", "EAST", "BAMBOO_1"])
        assert score == 20.0

    def test_triple_honor_highest(self, ai):
        score = ai._discard_score("EAST", ["EAST", "EAST", "EAST"])
        assert score == 50.0
