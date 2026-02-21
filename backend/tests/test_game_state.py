"""Tests for game/game_state.py — GameState and PlayerState classes."""

import pytest
from unittest.mock import patch
from game.game_state import GameState, PlayerState, NUM_PLAYERS
from game.tiles import is_flower_tile, build_deck


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_game(player_ids=None):
    """Create a GameState with default players."""
    if player_ids is None:
        player_ids = ["p0", "p1", "p2", "p3"]
    return GameState(room_id="test-room", player_ids=player_ids)


def make_dealt_game():
    """Create a GameState with tiles already dealt."""
    gs = make_game()
    gs.deal_initial_tiles()
    return gs


# ---------------------------------------------------------------------------
# PlayerState tests
# ---------------------------------------------------------------------------

class TestPlayerState:
    def test_hand_without_bonus(self):
        ps = PlayerState(id="test")
        ps.hand = ["BAMBOO_1", "FLOWER_1", "EAST", "SEASON_2"]
        result = ps.hand_without_bonus()
        assert result == ["BAMBOO_1", "EAST"]

    def test_full_tile_count(self):
        ps = PlayerState(id="test")
        ps.hand = ["BAMBOO_1", "BAMBOO_2", "BAMBOO_3"]
        assert ps.full_tile_count() == 3

    def test_effective_tile_count_excludes_bonus(self):
        ps = PlayerState(id="test")
        ps.hand = ["BAMBOO_1", "FLOWER_1", "EAST"]
        assert ps.effective_tile_count() == 2


# ---------------------------------------------------------------------------
# GameState init tests
# ---------------------------------------------------------------------------

class TestGameStateInit:
    def test_requires_4_players(self):
        with pytest.raises(ValueError, match="exactly 4"):
            GameState(room_id="r", player_ids=["p0", "p1"])

    def test_initial_state(self):
        gs = make_game()
        assert gs.phase == "drawing"
        assert gs.current_turn == 0
        assert gs.winner is None
        assert len(gs.wall) == 144
        assert len(gs.players) == 4

    def test_wall_is_shuffled(self):
        """Wall should not be in canonical build_deck order."""
        gs = make_game()
        canonical = build_deck()
        # Very unlikely to match after shuffle
        assert gs.wall != canonical


# ---------------------------------------------------------------------------
# Dealing tests
# ---------------------------------------------------------------------------

class TestDealInitialTiles:
    def test_dealer_has_14_effective_tiles(self):
        gs = make_dealt_game()
        p0 = gs.players[0]
        # After collecting flowers, effective hand should be ~14 (flowers replaced)
        # Dealer starts with 14 tiles drawn; bonus tiles are replaced
        effective = p0.effective_tile_count()
        assert effective == 14, f"Dealer should have 14 effective tiles, got {effective}"

    def test_non_dealers_have_13_effective_tiles(self):
        gs = make_dealt_game()
        for i in range(1, 4):
            effective = gs.players[i].effective_tile_count()
            assert effective == 13, f"Player {i} should have 13 effective tiles, got {effective}"

    def test_bonus_tiles_collected(self):
        """No player should have bonus tiles in their hand after dealing."""
        gs = make_dealt_game()
        for p in gs.players:
            for tile in p.hand:
                assert not is_flower_tile(tile), f"Bonus tile {tile} still in hand"

    def test_phase_is_discarding_after_deal(self):
        gs = make_dealt_game()
        assert gs.phase == "discarding"

    def test_current_turn_is_dealer(self):
        gs = make_dealt_game()
        assert gs.current_turn == 0

    def test_total_tiles_accounted_for(self):
        """All 144 tiles should be in wall + hands + flowers."""
        gs = make_dealt_game()
        total = len(gs.wall)
        for p in gs.players:
            total += len(p.hand) + len(p.flowers)
        assert total == 144


# ---------------------------------------------------------------------------
# Drawing tests
# ---------------------------------------------------------------------------

class TestDrawTile:
    def test_draw_in_drawing_phase(self):
        gs = make_dealt_game()
        # Dealer discards first to advance
        tile_to_discard = gs.players[0].hand[0]
        gs.discard_tile(0, tile_to_discard)
        # Skip all claims
        for i in range(1, 4):
            gs.skip_claim(i)
        # Now player 1 should be in drawing phase
        assert gs.phase == "drawing"
        assert gs.current_turn == 1
        drawn = gs.draw_tile(1)
        assert drawn is not None
        assert gs.phase == "discarding"

    def test_draw_wrong_phase_raises(self):
        gs = make_dealt_game()
        # Phase is "discarding" after deal
        with pytest.raises(ValueError, match="Cannot draw"):
            gs.draw_tile(0)

    def test_draw_wrong_player_raises(self):
        gs = make_game()
        gs.phase = "drawing"
        gs.current_turn = 0
        with pytest.raises(ValueError, match="not player 1"):
            gs.draw_tile(1)

    def test_draw_from_empty_wall_ends_game(self):
        gs = make_game()
        gs.wall = []  # Empty wall
        gs.phase = "drawing"
        gs.current_turn = 0
        result = gs.draw_tile(0)
        assert result is None
        assert gs.phase == "ended"


# ---------------------------------------------------------------------------
# Discard tests
# ---------------------------------------------------------------------------

class TestDiscardTile:
    def test_discard_valid(self):
        gs = make_dealt_game()
        tile = gs.players[0].hand[0]
        count_before = gs.players[0].hand.count(tile)
        gs.discard_tile(0, tile)
        count_after = gs.players[0].hand.count(tile)
        assert count_after == count_before - 1
        assert tile in gs.discards[0]
        assert gs.phase == "claiming"
        assert gs.last_discard == tile
        assert gs.last_discard_player == 0

    def test_discard_wrong_phase_raises(self):
        gs = make_game()
        gs.phase = "drawing"
        gs.players[0].hand = ["BAMBOO_1"]
        with pytest.raises(ValueError, match="Cannot discard"):
            gs.discard_tile(0, "BAMBOO_1")

    def test_discard_wrong_player_raises(self):
        gs = make_dealt_game()
        with pytest.raises(ValueError, match="not player 1"):
            gs.discard_tile(1, "BAMBOO_1")

    def test_discard_tile_not_in_hand_raises(self):
        gs = make_dealt_game()
        with pytest.raises(ValueError, match="not in player"):
            gs.discard_tile(0, "NONEXISTENT_TILE")

    def test_discard_bonus_tile_raises(self):
        gs = make_dealt_game()
        gs.players[0].hand.append("FLOWER_1")
        with pytest.raises(ValueError, match="bonus tile"):
            gs.discard_tile(0, "FLOWER_1")


# ---------------------------------------------------------------------------
# Claim tests
# ---------------------------------------------------------------------------

class TestClaimPung:
    def _setup_claim_scenario(self):
        """Set up a scenario where player 0 discards and player 1 can pung."""
        gs = make_dealt_game()
        tile = gs.players[0].hand[0]
        # Give player 1 two copies of that tile
        gs.players[1].hand.extend([tile, tile])
        gs.discard_tile(0, tile)
        return gs, tile

    def test_claim_pung_valid(self):
        gs, tile = self._setup_claim_scenario()
        result = gs.claim_pung(1)
        assert result is True

    def test_claim_pung_wrong_phase_raises(self):
        gs = make_dealt_game()
        with pytest.raises(ValueError, match="Not in claiming"):
            gs.claim_pung(1)

    def test_discarder_cannot_claim_raises(self):
        gs, tile = self._setup_claim_scenario()
        with pytest.raises(ValueError, match="discarder cannot claim"):
            gs.claim_pung(0)

    def test_claim_pung_insufficient_tiles(self):
        gs, tile = self._setup_claim_scenario()
        # Player 2 doesn't have the tiles
        result = gs.claim_pung(2)
        assert result is False


class TestSkipClaim:
    def test_skip_all_advances_turn(self):
        gs = make_dealt_game()
        tile = gs.players[0].hand[0]
        gs.discard_tile(0, tile)
        # All other players skip
        for i in range(1, 4):
            gs.skip_claim(i)
        assert gs.phase == "drawing"
        assert gs.current_turn == 1

    def test_skip_wrong_phase_raises(self):
        gs = make_dealt_game()
        with pytest.raises(ValueError, match="Not in claiming"):
            gs.skip_claim(1)


class TestClaimChow:
    def _setup_chow_scenario(self):
        """Player 0 discards BAMBOO_5; player 1 (left of p0) has BAMBOO_4, BAMBOO_6."""
        gs = make_dealt_game()
        # Ensure player 0 has BAMBOO_5
        if "BAMBOO_5" not in gs.players[0].hand:
            gs.players[0].hand.append("BAMBOO_5")
        # Ensure player 1 has the adjacent tiles
        gs.players[1].hand.extend(["BAMBOO_4", "BAMBOO_6"])
        gs.discard_tile(0, "BAMBOO_5")
        return gs

    def test_claim_chow_valid(self):
        gs = self._setup_chow_scenario()
        result = gs.claim_chow(1, ["BAMBOO_4", "BAMBOO_6"])
        assert result is True

    def test_chow_wrong_player_raises(self):
        """Only the player to the right of the discarder can chow."""
        gs = self._setup_chow_scenario()
        gs.players[2].hand.extend(["BAMBOO_4", "BAMBOO_6"])
        with pytest.raises(ValueError, match="left"):
            gs.claim_chow(2, ["BAMBOO_4", "BAMBOO_6"])


# ---------------------------------------------------------------------------
# Declare win tests
# ---------------------------------------------------------------------------

class TestDeclareWin:
    def test_self_draw_win(self):
        gs = make_dealt_game()
        # Set up a winning hand for player 0
        gs.players[0].hand = (
            ["BAMBOO_1"] * 3
            + ["BAMBOO_2"] * 3
            + ["CIRCLES_5"] * 3
            + ["EAST"] * 3
            + ["RED"] * 2
        )
        gs.phase = "discarding"
        gs.current_turn = 0
        result = gs.declare_win(0)
        assert result["winner"] == "p0"
        assert result["ron"] is False
        assert result["score"] > 0
        assert gs.phase == "ended"

    def test_declare_win_not_winning_hand_raises(self):
        gs = make_dealt_game()
        gs.phase = "discarding"
        gs.current_turn = 0
        # Hand is random, very unlikely winning
        gs.players[0].hand = [
            "BAMBOO_1", "BAMBOO_3", "BAMBOO_5", "BAMBOO_7", "BAMBOO_9",
            "CIRCLES_2", "CIRCLES_4", "CIRCLES_6", "CIRCLES_8",
            "CHARACTERS_1", "CHARACTERS_3", "CHARACTERS_5",
            "EAST", "SOUTH",
        ]
        with pytest.raises(ValueError, match="not a winning hand"):
            gs.declare_win(0)

    def test_ron_win(self):
        """Win by claiming another player's discard."""
        gs = make_dealt_game()
        # Give player 1 a hand that needs just one more tile to win
        gs.players[1].hand = (
            ["BAMBOO_1"] * 3
            + ["BAMBOO_2"] * 3
            + ["CIRCLES_5"] * 3
            + ["EAST"] * 3
            + ["RED"]
        )
        # Player 0 discards RED
        if "RED" not in gs.players[0].hand:
            gs.players[0].hand.append("RED")
        gs.discard_tile(0, "RED")
        result = gs.declare_win(1)
        assert result["winner"] == "p1"
        assert result["ron"] is True

    def test_declare_win_wrong_phase_raises(self):
        gs = make_dealt_game()
        gs.phase = "drawing"
        with pytest.raises(ValueError, match="Cannot declare win"):
            gs.declare_win(0)

    def test_self_draw_win_with_pung_meld(self):
        """Player can declare self-draw win when they have claimed melds."""
        gs = make_dealt_game()
        # Player 0 has already claimed one pung meld; hand has only 11 tiles
        gs.players[0].melds = [["EAST", "EAST", "EAST"]]
        gs.players[0].hand = (
            ["BAMBOO_1"] * 3
            + ["BAMBOO_2"] * 3
            + ["CIRCLES_5"] * 3
            + ["RED"] * 2
        )  # 11 tiles + 1 pung meld = winning
        gs.phase = "discarding"
        gs.current_turn = 0
        result = gs.declare_win(0)
        assert result["winner"] == "p0"
        assert result["ron"] is False
        assert gs.phase == "ended"

    def test_self_draw_win_action_offered_with_melds(self):
        """'win' appears in available actions when player has melds and a winning hand."""
        gs = make_dealt_game()
        # One pung meld already claimed; remaining hand wins
        gs.players[0].melds = [["CIRCLES_9", "CIRCLES_9", "CIRCLES_9"]]
        gs.players[0].hand = (
            ["BAMBOO_1"] * 3
            + ["BAMBOO_2"] * 3
            + ["CHARACTERS_7"] * 3
            + ["SOUTH"] * 2
        )  # 11 tiles + meld → 14 effective
        gs.phase = "discarding"
        gs.current_turn = 0
        actions = gs.get_available_actions(0)
        assert "win" in actions, f"Expected 'win' in actions, got: {actions}"

    def test_ron_win_with_pung_meld(self):
        """Player can win by claiming a discard when they already have a meld."""
        gs = make_dealt_game()
        # Player 1 has one pung meld; needs one more tile for a complete hand.
        # Hand has RED (single); discard is RED → pair becomes RED+RED.
        gs.players[1].melds = [["WEST", "WEST", "WEST"]]
        gs.players[1].hand = (
            ["BAMBOO_3"] * 3
            + ["CIRCLES_1"] * 3
            + ["CHARACTERS_5"] * 3
            + ["RED"]  # 10 tiles; discard RED completes RED+RED pair
        )
        # Player 0 discards RED so player 1 can ron
        gs.players[0].hand.append("RED")
        gs.discard_tile(0, "RED")
        result = gs.declare_win(1)
        assert result["winner"] == "p1"
        assert result["ron"] is True

    def test_ron_win_action_offered_with_melds(self):
        """'win' appears in claiming-phase actions when player has melds."""
        gs = make_dealt_game()
        gs.players[1].melds = [["NORTH", "NORTH", "NORTH"]]
        # Hand has GREEN (single); discard GREEN completes GREEN+GREEN pair.
        gs.players[1].hand = (
            ["BAMBOO_5"] * 3
            + ["CIRCLES_2"] * 3
            + ["CHARACTERS_8"] * 3
            + ["GREEN"]
        )
        gs.players[0].hand.append("GREEN")
        gs.discard_tile(0, "GREEN")
        actions = gs.get_available_actions(1)
        assert "win" in actions, f"Expected 'win' in actions, got: {actions}"


# ---------------------------------------------------------------------------
# Kong tests
# ---------------------------------------------------------------------------

class TestClaimKong:
    def test_self_drawn_kong(self):
        gs = make_dealt_game()
        # Give player 0 four copies of a tile
        gs.players[0].hand = ["BAMBOO_1"] * 4 + ["CIRCLES_1", "CIRCLES_2"]
        gs.phase = "discarding"
        gs.current_turn = 0
        result = gs.claim_kong(0, "BAMBOO_1")
        assert result is True
        assert ["BAMBOO_1"] * 4 in gs.players[0].melds

    def test_self_kong_insufficient_tiles_raises(self):
        gs = make_dealt_game()
        gs.players[0].hand = ["BAMBOO_1"] * 2 + ["CIRCLES_1"]
        gs.phase = "discarding"
        gs.current_turn = 0
        with pytest.raises(ValueError, match="does not have 4x"):
            gs.claim_kong(0, "BAMBOO_1")


# ---------------------------------------------------------------------------
# Available actions tests
# ---------------------------------------------------------------------------

class TestGetAvailableActions:
    def test_drawing_phase(self):
        gs = make_game()
        gs.phase = "drawing"
        gs.current_turn = 0
        actions = gs.get_available_actions(0)
        assert "draw" in actions

    def test_discarding_phase(self):
        gs = make_dealt_game()
        actions = gs.get_available_actions(0)
        assert "discard" in actions

    def test_ended_phase(self):
        gs = make_game()
        gs.phase = "ended"
        actions = gs.get_available_actions(0)
        assert actions == []

    def test_claiming_phase_with_skip(self):
        gs = make_dealt_game()
        tile = gs.players[0].hand[0]
        gs.discard_tile(0, tile)
        # Player 1 should have at least "skip"
        actions = gs.get_available_actions(1)
        assert "skip" in actions


# ---------------------------------------------------------------------------
# to_dict tests
# ---------------------------------------------------------------------------

class TestToDict:
    def test_to_dict_hides_other_hands(self):
        gs = make_dealt_game()
        state = gs.to_dict(viewing_player_idx=0)
        # Player 0's hand is visible
        assert state["players"][0]["hand"]["hidden"] is False
        assert "tiles" in state["players"][0]["hand"]
        # Other players' hands are hidden
        for i in range(1, 4):
            assert state["players"][i]["hand"]["hidden"] is True
            assert "count" in state["players"][i]["hand"]

    def test_to_dict_no_viewing_player(self):
        gs = make_dealt_game()
        state = gs.to_dict(viewing_player_idx=None)
        # All hands should be visible
        for i in range(4):
            assert state["players"][i]["hand"]["hidden"] is False

    def test_to_dict_contains_required_fields(self):
        gs = make_dealt_game()
        state = gs.to_dict(viewing_player_idx=0)
        assert "room_id" in state
        assert "phase" in state
        assert "current_turn" in state
        assert "wall_remaining" in state
        assert "discards" in state
        assert "players" in state
        assert "winner" in state
        assert "available_actions" in state


# ---------------------------------------------------------------------------
# Flower collection tests
# ---------------------------------------------------------------------------

class TestFlowerCollection:
    def test_flowers_moved_to_flowers_list(self):
        gs = make_dealt_game()
        for p in gs.players:
            # All bonus tiles should be in flowers, not hand
            for tile in p.hand:
                assert not is_flower_tile(tile)

    def test_flower_replaced_from_wall(self):
        """When a flower is collected, a replacement is drawn from the back."""
        gs = make_game()
        gs.players[0].hand = ["FLOWER_1", "BAMBOO_1"]
        wall_size_before = len(gs.wall)
        gs._collect_bonus_tiles(0)
        assert "FLOWER_1" not in gs.players[0].hand
        assert "FLOWER_1" in gs.players[0].flowers
        # One tile drawn from wall as replacement
        assert len(gs.wall) == wall_size_before - 1


# ---------------------------------------------------------------------------
# Score calculation tests
# ---------------------------------------------------------------------------

class TestHanBasedScore:
    """Scoring is now han-based. player.score == han_total after a win."""

    def test_player_score_equals_han_total_after_win(self):
        """After declare_win, player.score reflects the han count."""
        gs = make_dealt_game()
        # Build a minimal winning hand (平胡 all chows, concealed, no flowers)
        gs.players[0].hand = [
            "BAMBOO_1", "BAMBOO_2", "BAMBOO_3",
            "CIRCLES_4", "CIRCLES_5", "CIRCLES_6",
            "CHARACTERS_7", "CHARACTERS_8", "CHARACTERS_9",
            "BAMBOO_4", "BAMBOO_5", "BAMBOO_6",
            "EAST", "EAST",
        ]
        gs.players[0].melds = []
        gs.players[0].flowers = []
        gs.phase = "discarding"
        gs.current_turn = 0
        gs.declare_win(0)
        assert gs.players[0].score == gs.han_total
        assert gs.han_total >= 1  # at least base 1 fan

    def test_kong_chip_transfers_accumulate(self):
        """record_kong_payment credits konger +3 and debits each other -1."""
        gs = make_dealt_game()
        assert gs.kong_chip_transfers == {}
        gs.record_kong_payment(0)
        assert gs.kong_chip_transfers[gs.players[0].id] == 3
        for i in range(1, 4):
            assert gs.kong_chip_transfers[gs.players[i].id] == -1

    def test_dealer_idx_default(self):
        gs = make_dealt_game()
        assert gs.dealer_idx == 0
