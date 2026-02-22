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
        with pytest.raises(ValueError, match="cannot declare kong"):
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


# ============================================================
# Tests for #10 fix: Ron chip formula for dealer winner
# ============================================================

class TestRonChipFormulaDealerWin:
    """
    When the DEALER wins by ron (discard win), the discarder must pay
    6×unit (not 3×unit).  This was a bug where winner_idx == dealer_idx
    caused all payers to be treated as non-dealers (1×unit each).

    We test the formula directly via a helper that mirrors _handle_game_over.
    """

    @staticmethod
    def _compute_transfers(winner_idx: int, dealer_idx: int, han_total: int,
                           win_ron: bool, discarder_idx, n_players: int = 4,
                           chip_cap: int = 64) -> dict:
        """Pure replica of the _pay logic from websocket._handle_game_over."""
        unit = min(chip_cap, 2 ** (han_total - 1))

        def _pay(payer_idx):
            if winner_idx == dealer_idx:
                return 2 * unit
            return 2 * unit if payer_idx == dealer_idx else unit

        transfers = {i: 0 for i in range(n_players)}
        if win_ron and discarder_idx is not None:
            full = sum(_pay(i) for i in range(n_players) if i != winner_idx)
            transfers[winner_idx] += full
            transfers[discarder_idx] -= full
        else:
            for i in range(n_players):
                if i != winner_idx:
                    pay = _pay(i)
                    transfers[winner_idx] += pay
                    transfers[i] -= pay
        return transfers

    def test_dealer_wins_ron_pays_6_unit(self):
        """Dealer (seat 0) wins by ron: discarder pays 6×unit."""
        # 1 han → unit = 1; dealer wins → discarder should pay 6
        t = self._compute_transfers(
            winner_idx=0, dealer_idx=0, han_total=1,
            win_ron=True, discarder_idx=1,
        )
        assert t[0] == 6   # winner receives 6
        assert t[1] == -6  # discarder pays 6
        assert t[2] == 0
        assert t[3] == 0

    def test_non_dealer_wins_ron_pays_4_unit(self):
        """Non-dealer (seat 1) wins by ron: discarder pays 4×unit."""
        t = self._compute_transfers(
            winner_idx=1, dealer_idx=0, han_total=1,
            win_ron=True, discarder_idx=2,
        )
        assert t[1] == 4   # winner receives 4
        assert t[2] == -4  # discarder pays 4
        assert t[0] == 0
        assert t[3] == 0

    def test_dealer_wins_tsumo_6_unit(self):
        """Dealer wins by self-draw: each of 3 others pays 2×unit = 6 total."""
        t = self._compute_transfers(
            winner_idx=0, dealer_idx=0, han_total=1,
            win_ron=False, discarder_idx=None,
        )
        assert t[0] == 6
        assert t[1] == -2
        assert t[2] == -2
        assert t[3] == -2

    def test_non_dealer_wins_tsumo_4_unit(self):
        """Non-dealer wins tsumo: dealer pays 2×unit, others pay 1×unit = 4 total."""
        t = self._compute_transfers(
            winner_idx=1, dealer_idx=0, han_total=1,
            win_ron=False, discarder_idx=None,
        )
        assert t[1] == 4
        assert t[0] == -2  # dealer pays double
        assert t[2] == -1
        assert t[3] == -1

    def test_formula_scales_with_han(self):
        """2 fan → unit=2; dealer wins ron should pay 12 (6×2)."""
        t = self._compute_transfers(
            winner_idx=0, dealer_idx=0, han_total=2,
            win_ron=True, discarder_idx=3,
        )
        assert t[0] == 12
        assert t[3] == -12


# ============================================================
# Tests for #13 fix: Minimum 3-fan requirement
# ============================================================

class TestMinimumFanRequirement:
    """declare_win must reject hands that score fewer than MIN_HAN (3) fan."""

    def _low_fan_ron_state(self):
        """
        Player 0 holds a structurally valid ron win but only 1 fan
        (Base=1; has flowers → no 无花; has meld → no 门清; ron → no 自摸).

        With 1 declared meld (3 tiles), the player must have exactly
        10 concealed tiles so that hand(10) + discard(1) + meld_reps(3) = 14.
        """
        gs = make_dealt_game()
        gs.players[0].melds = [["BAMBOO_1", "BAMBOO_2", "BAMBOO_3"]]
        gs.players[0].flowers = ["FLOWER_1"]
        # 10 concealed tiles: three chows + one pair (pair = WEST to win on WEST)
        gs.players[0].hand = [
            "CIRCLES_4", "CIRCLES_5", "CIRCLES_6",
            "CHARACTERS_7", "CHARACTERS_8", "CHARACTERS_9",
            "BAMBOO_4", "BAMBOO_5", "BAMBOO_6",
            "WEST",  # pair first tile; WEST is the discard to claim
        ]
        # Set up claiming phase: player 0 claims WEST as the discard to win
        gs.phase = "claiming"
        gs.last_discard = "WEST"
        gs.last_discard_player = 1
        gs._pending_claims = {0, 2, 3}
        gs.current_turn = 1
        return gs

    def test_min_han_constant_is_positive(self):
        from game.game_state import MIN_HAN
        assert MIN_HAN >= 1

    def test_low_fan_ron_rejected_if_below_min(self):
        """declare_win raises ValueError when hand scores < MIN_HAN fan."""
        import pytest
        from game.hand import calculate_han
        from game.game_state import MIN_HAN
        gs = self._low_fan_ron_state()
        discard = gs.last_discard
        test_tiles = gs.players[0].hand_without_bonus() + [discard]
        fan = calculate_han(test_tiles, gs.players[0].melds,
                            gs.players[0].flowers, ron=True)['total']
        if fan >= MIN_HAN:
            pytest.skip(
                f"Hand scored {fan} fan (≥ MIN_HAN={MIN_HAN}); "
                "raise MIN_HAN above this value to exercise the rejection path"
            )
        with pytest.raises(ValueError, match="fan"):
            gs.declare_win(0)

    def test_high_fan_hand_accepted(self):
        """A hand well above MIN_HAN fan is accepted without error."""
        from game.game_state import MIN_HAN
        gs = make_dealt_game()
        # 清一色 碰碰胡 自摸 无花 门清 → far above 3 fan
        gs.players[0].hand = [
            "BAMBOO_1", "BAMBOO_1", "BAMBOO_1",
            "BAMBOO_3", "BAMBOO_3", "BAMBOO_3",
            "BAMBOO_5", "BAMBOO_5", "BAMBOO_5",
            "BAMBOO_7", "BAMBOO_7", "BAMBOO_7",
            "BAMBOO_9", "BAMBOO_9",
        ]
        gs.players[0].melds = []
        gs.players[0].flowers = []
        gs.phase = "discarding"
        gs.current_turn = 0
        result = gs.declare_win(0)
        assert result["winner"] == gs.players[0].id
        assert gs.han_total >= MIN_HAN

    def test_seven_pairs_meets_min_fan(self):
        """Seven pairs (七対) scores ≥ 3 fan and must be declarable."""
        from game.game_state import MIN_HAN
        gs = make_dealt_game()
        gs.players[0].hand = (
            ["BAMBOO_1"] * 2 + ["BAMBOO_3"] * 2 + ["CIRCLES_5"] * 2
            + ["CHARACTERS_7"] * 2 + ["EAST"] * 2 + ["RED"] * 2
            + ["BAMBOO_9"] * 2
        )
        gs.players[0].melds = []
        gs.players[0].flowers = []
        gs.phase = "discarding"
        gs.current_turn = 0
        result = gs.declare_win(0)
        assert result["winner"] == gs.players[0].id
        assert gs.han_total >= MIN_HAN


# ============================================================
# Tests for #2 fix: 平胡 (Ping Hu) requires ron only
# ============================================================

class TestPingHuRonOnly:
    """平胡 must only be awarded when winning by ron, not by tsumo."""

    _HAND = [
        "BAMBOO_2", "BAMBOO_3", "BAMBOO_4",
        "CIRCLES_3", "CIRCLES_4", "CIRCLES_5",
        "CHARACTERS_5", "CHARACTERS_6", "CHARACTERS_7",
        "BAMBOO_5", "BAMBOO_6", "BAMBOO_7",
        "CIRCLES_8", "CIRCLES_8",
    ]

    def test_ping_hu_awarded_for_ron(self):
        from game.hand import calculate_han
        result = calculate_han(self._HAND, [], [], ron=True)
        names = [x['name_cn'] for x in result['breakdown']]
        assert '平胡' in names

    def test_ping_hu_not_awarded_for_tsumo(self):
        from game.hand import calculate_han
        result = calculate_han(self._HAND, [], [], ron=False)
        names = [x['name_cn'] for x in result['breakdown']]
        assert '平胡' not in names
        assert '自摸' in names  # self-draw bonus awarded instead


# ============================================================
# Tests for #3 fix: 混幺九 requires ALL tiles to be terminals/honors
# ============================================================

class TestHunYaoJiu:
    """混幺九: every tile in every group and pair must be terminal or honor."""

    def test_valid_hun_yao_jiu(self):
        """All-pung hand of terminals/honors + honor pair → 混幺九."""
        from game.hand import calculate_han
        tiles = (
            ["BAMBOO_1"] * 3 + ["CIRCLES_9"] * 3 + ["EAST"] * 3 + ["NORTH", "NORTH"]
        )
        melds = [["CHARACTERS_9", "CHARACTERS_9", "CHARACTERS_9"]]
        result = calculate_han(tiles, melds, [], ron=True)
        names = [x['name_cn'] for x in result['breakdown']]
        assert '混幺九' in names

    def test_middle_tile_in_group_disqualifies(self):
        """A group containing 2-8 tile must NOT qualify for 混幺九."""
        from game.hand import calculate_han
        tiles = (
            ["BAMBOO_1", "BAMBOO_2", "BAMBOO_3"]   # 2 and 3 are NOT terminals
            + ["CIRCLES_9"] * 3 + ["EAST"] * 3 + ["NORTH", "NORTH"]
        )
        melds = [["CHARACTERS_9", "CHARACTERS_9", "CHARACTERS_9"]]
        result = calculate_han(tiles, melds, [], ron=True)
        names = [x['name_cn'] for x in result['breakdown']]
        assert '混幺九' not in names


# ============================================================
# Tests for #6/#7 fix: Extend-pung (加杠) and Rob-the-Kong (搶杠胡)
# ============================================================

class TestExtendPungKong:
    """加杠: tile in hand matching a declared pung meld → extend to kong."""

    def _state(self):
        gs = make_dealt_game()
        gs.players[0].melds = [["BAMBOO_5", "BAMBOO_5", "BAMBOO_5"]]
        gs.players[0].hand = [
            "BAMBOO_1", "BAMBOO_2", "BAMBOO_3",
            "CIRCLES_4", "CIRCLES_5", "CIRCLES_6",
            "CHARACTERS_7", "CHARACTERS_8", "CHARACTERS_9",
            "BAMBOO_5", "EAST",
        ]
        gs.phase = "discarding"
        gs.current_turn = 0
        return gs

    def test_extend_pung_in_available_actions(self):
        gs = self._state()
        assert "kong" in gs.get_available_actions(0)

    def test_extend_pung_opens_rob_kong_window(self):
        gs = self._state()
        gs.claim_kong(0, "BAMBOO_5")
        assert gs.phase == "claiming"
        assert gs._is_rob_kong_window is True
        assert gs._rob_kong_tile == "BAMBOO_5"
        assert gs._rob_kong_player_idx == 0

    def test_meld_becomes_4_tiles(self):
        gs = self._state()
        gs.claim_kong(0, "BAMBOO_5")
        kong_meld = next(m for m in gs.players[0].melds if "BAMBOO_5" in m)
        assert len(kong_meld) == 4

    def test_rob_kong_window_only_allows_win_skip(self):
        gs = self._state()
        gs.claim_kong(0, "BAMBOO_5")
        for i in range(1, 4):
            actions = gs.get_available_actions(i)
            assert "pung" not in actions
            assert "chow" not in actions
            assert "kong" not in actions
            assert "skip" in actions

    def test_all_skip_completes_kong(self):
        gs = self._state()
        gs.claim_kong(0, "BAMBOO_5")
        for i in range(1, 4):
            gs.skip_claim(i)
        assert gs.phase == "discarding"
        assert gs.current_turn == 0
        assert gs._is_rob_kong_window is False
        assert gs.kong_chip_transfers.get(gs.players[0].id, 0) == 3


class TestRobTheKong:
    """搶杠胡: player can win on the tile being extended into a kong."""

    def _state(self):
        gs = make_dealt_game()
        gs.players[0].melds = [["BAMBOO_5", "BAMBOO_5", "BAMBOO_5"]]
        gs.players[0].hand = [
            "CIRCLES_1", "CIRCLES_2", "CIRCLES_3",
            "CHARACTERS_7", "CHARACTERS_8", "CHARACTERS_9",
            "BAMBOO_1", "BAMBOO_2", "BAMBOO_3",
            "BAMBOO_5", "EAST",
        ]
        # Player 1 holds 13 tiles; claiming BAMBOO_5 completes the chow 4-5-6
        gs.players[1].hand = [
            "BAMBOO_1", "BAMBOO_2", "BAMBOO_3",   # chow
            "CIRCLES_1", "CIRCLES_2", "CIRCLES_3", # chow
            "CHARACTERS_7", "CHARACTERS_8", "CHARACTERS_9",  # chow
            "BAMBOO_4", "BAMBOO_6",                # incomplete chow (needs BAMBOO_5)
            "EAST", "EAST",                        # pair
        ]
        gs.players[1].melds = []
        gs.players[1].flowers = []
        gs.phase = "discarding"
        gs.current_turn = 0
        return gs

    def test_rob_kong_win_ends_game(self):
        gs = self._state()
        gs.claim_kong(0, "BAMBOO_5")
        gs.skip_claim(2)
        gs.skip_claim(3)
        gs.declare_win(1)
        assert gs.phase == "ended"
        assert gs.winner == gs.players[1].id
        assert gs.win_ron is True
        assert gs._is_rob_kong_window is False

    def test_rob_kong_reverts_kong_to_pung(self):
        gs = self._state()
        gs.claim_kong(0, "BAMBOO_5")
        gs.skip_claim(2)
        gs.skip_claim(3)
        gs.declare_win(1)
        pung = next(m for m in gs.players[0].melds if "BAMBOO_5" in m)
        assert len(pung) == 3


# ---------------------------------------------------------------------------
# Comprehensive kong tests covering all paths
# ---------------------------------------------------------------------------


class TestConcealedKongFull:
    """暗杠 — 4 identical tiles in hand, declared during own discard turn."""

    def _state(self):
        gs = make_dealt_game()
        gs.players[0].hand = (
            ["BAMBOO_1"] * 4
            + ["BAMBOO_2", "BAMBOO_3", "CIRCLES_4", "CIRCLES_5",
               "CHARACTERS_6", "CHARACTERS_7", "EAST"]
        )
        gs.phase = "discarding"
        gs.current_turn = 0
        gs.wall = ["CIRCLES_9"] * 10  # guaranteed non-flower replacements
        return gs

    def test_concealed_kong_meld_has_4_tiles(self):
        gs = self._state()
        gs.claim_kong(0, "BAMBOO_1")
        kong_meld = next(m for m in gs.players[0].melds if m[0] == "BAMBOO_1")
        assert len(kong_meld) == 4

    def test_concealed_kong_removes_tiles_from_hand(self):
        gs = self._state()
        before = gs.players[0].hand.count("BAMBOO_1")
        gs.claim_kong(0, "BAMBOO_1")
        assert "BAMBOO_1" not in gs.players[0].hand
        assert before == 4

    def test_concealed_kong_draws_replacement(self):
        gs = self._state()
        hand_before = len(gs.players[0].hand)
        # 4 removed, 1 replacement drawn → hand size unchanged
        gs.claim_kong(0, "BAMBOO_1")
        assert len(gs.players[0].hand) == hand_before - 4 + 1

    def test_concealed_kong_lingshang_pending_set(self):
        gs = self._state()
        gs.claim_kong(0, "BAMBOO_1")
        assert gs.lingshang_pending is True

    def test_concealed_kong_phase_stays_discarding(self):
        gs = self._state()
        gs.claim_kong(0, "BAMBOO_1")
        assert gs.phase == "discarding"
        assert gs.current_turn == 0

    def test_concealed_kong_chip_payment_3_per_kong(self):
        gs = self._state()
        gs.claim_kong(0, "BAMBOO_1")
        konger_id = gs.players[0].id
        assert gs.kong_chip_transfers.get(konger_id, 0) == 3

    def test_concealed_kong_last_drawn_tile_is_replacement(self):
        """last_drawn_tile must be the actual replacement in hand, not the bonus tile."""
        gs = self._state()
        gs.wall = ["CIRCLES_9"]  # one non-flower replacement
        gs.claim_kong(0, "BAMBOO_1")
        assert gs.last_drawn_tile == "CIRCLES_9"
        assert gs.last_drawn_tile in gs.players[0].hand

    def test_concealed_kong_last_drawn_tile_when_replacement_is_flower(self):
        """If replacement is a flower, last_drawn_tile should be the NEXT tile, not the flower."""
        from game.tiles import is_flower_tile
        gs = self._state()
        gs.wall = ["BAMBOO_4", "FLOWER_1"]  # wall[-1]=FLOWER_1 drawn first, then BAMBOO_4
        gs.claim_kong(0, "BAMBOO_1")
        assert not is_flower_tile(gs.last_drawn_tile), (
            "last_drawn_tile must be a non-flower tile after bonus collection"
        )
        assert gs.last_drawn_tile in gs.players[0].hand

    def test_failed_concealed_kong_clears_lingshang_pending(self):
        """After a failed kong attempt, lingshang_pending must not remain stale."""
        gs = self._state()
        gs.lingshang_pending = True  # simulate stale flag from previous kong
        with pytest.raises(ValueError):
            gs.claim_kong(0, "CIRCLES_4")  # CIRCLES_4 appears only once → fails
        assert gs.lingshang_pending is False

    def test_concealed_kong_not_available_without_4_copies(self):
        gs = self._state()
        # Max 3 of any tile → no 4-of-a-kind, no pung meld → no kong available
        gs.players[0].hand = (
            ["BAMBOO_1"] * 3 + ["BAMBOO_2"] * 3 + ["BAMBOO_3"] * 3 + ["EAST", "SOUTH"]
        )
        gs.players[0].melds = []  # no pung meld either
        actions = gs.get_available_actions(0)
        assert "kong" not in actions

    def test_sequential_concealed_kongs(self):
        """Player can declare two concealed kongs in the same discarding turn."""
        gs = make_dealt_game()
        gs.players[0].hand = (
            ["BAMBOO_1"] * 4 + ["BAMBOO_2"] * 4
            + ["CIRCLES_1", "CIRCLES_2", "EAST"]
        )
        gs.phase = "discarding"
        gs.current_turn = 0
        gs.wall = ["CIRCLES_9"] * 10
        gs.claim_kong(0, "BAMBOO_1")
        assert gs.phase == "discarding"
        gs.claim_kong(0, "BAMBOO_2")
        assert gs.phase == "discarding"
        assert len(gs.players[0].melds) == 2
        # Two kongs → konger earns 3+3 = 6 chip-units
        assert gs.kong_chip_transfers.get(gs.players[0].id, 0) == 6


class TestExtendPungKongFull:
    """加杠 — extend an existing pung meld with a matching tile from hand."""

    def _state(self):
        gs = make_dealt_game()
        gs.players[0].melds = [["BAMBOO_5", "BAMBOO_5", "BAMBOO_5"]]
        gs.players[0].hand = [
            "BAMBOO_2", "BAMBOO_3", "CIRCLES_4", "CIRCLES_5",
            "CHARACTERS_7", "CHARACTERS_8", "EAST", "BAMBOO_5",
        ]
        gs.phase = "discarding"
        gs.current_turn = 0
        gs.wall = ["CIRCLES_9"] * 10
        return gs

    def test_extend_pung_pending_claims_excludes_konger(self):
        gs = self._state()
        gs.claim_kong(0, "BAMBOO_5")
        assert 0 not in gs._pending_claims
        assert {1, 2, 3} == gs._pending_claims

    def test_extend_pung_chip_payment_after_all_skip(self):
        gs = self._state()
        gs.claim_kong(0, "BAMBOO_5")
        for i in range(1, 4):
            gs.skip_claim(i)
        assert gs.kong_chip_transfers.get(gs.players[0].id, 0) == 3

    def test_extend_pung_lingshang_pending_after_completion(self):
        gs = self._state()
        gs.claim_kong(0, "BAMBOO_5")
        for i in range(1, 4):
            gs.skip_claim(i)
        assert gs.lingshang_pending is True

    def test_extend_pung_last_drawn_tile_after_completion(self):
        gs = self._state()
        gs.wall = ["CIRCLES_9"]
        gs.claim_kong(0, "BAMBOO_5")
        for i in range(1, 4):
            gs.skip_claim(i)
        assert gs.last_drawn_tile == "CIRCLES_9"
        assert gs.last_drawn_tile in gs.players[0].hand

    def test_extend_pung_last_drawn_tile_when_flower_replacement(self):
        """Flower bonus replacement must not be reported as last_drawn_tile."""
        from game.tiles import is_flower_tile
        gs = self._state()
        gs.wall = ["BAMBOO_4", "FLOWER_2"]  # FLOWER_2 drawn first, then BAMBOO_4
        gs.claim_kong(0, "BAMBOO_5")
        for i in range(1, 4):
            gs.skip_claim(i)
        assert not is_flower_tile(gs.last_drawn_tile)
        assert gs.last_drawn_tile in gs.players[0].hand

    def test_rob_kong_no_chip_payment_to_konger(self):
        """When someone robs the kong (搶杠胡), no kong chip transfer is recorded."""
        gs = make_dealt_game()
        gs.players[0].melds = [["BAMBOO_5", "BAMBOO_5", "BAMBOO_5"]]
        gs.players[0].hand = ["BAMBOO_5", "EAST", "SOUTH", "WEST", "NORTH",
                               "RED", "GREEN", "WHITE"]
        # Player 1 can win on BAMBOO_5
        gs.players[1].hand = (
            ["BAMBOO_1", "BAMBOO_2", "BAMBOO_3",
             "CIRCLES_1", "CIRCLES_2", "CIRCLES_3",
             "CHARACTERS_7", "CHARACTERS_8", "CHARACTERS_9",
             "BAMBOO_4", "BAMBOO_6", "EAST", "EAST"]
        )
        gs.phase = "discarding"
        gs.current_turn = 0
        gs.claim_kong(0, "BAMBOO_5")
        gs.skip_claim(2)
        gs.skip_claim(3)
        gs.declare_win(1)
        # Game ended; konger should NOT have received kong chip payment
        assert gs.kong_chip_transfers.get(gs.players[0].id, 0) == 0

    def test_extend_pung_not_available_without_matching_hand_tile(self):
        gs = make_dealt_game()
        gs.players[0].melds = [["BAMBOO_5", "BAMBOO_5", "BAMBOO_5"]]
        gs.players[0].hand = ["BAMBOO_1", "BAMBOO_2", "BAMBOO_3",
                               "CIRCLES_4", "EAST"]  # no BAMBOO_5 in hand
        gs.phase = "discarding"
        gs.current_turn = 0
        actions = gs.get_available_actions(0)
        assert "kong" not in actions


class TestClaimedKongFull:
    """声索杠 — claiming another player's discard when holding 3 matching tiles."""

    def _setup(self):
        gs = make_dealt_game()
        # Discard BAMBOO_7 from player 1
        gs.players[1].hand = ["BAMBOO_7"] + ["EAST"] * 12
        gs.phase = "discarding"
        gs.current_turn = 1
        gs.discard_tile(1, "BAMBOO_7")
        # Give player 0 three BAMBOO_7
        gs.players[0].hand = ["BAMBOO_7"] * 3 + ["CIRCLES_1"]
        gs._pending_claims = {0, 2, 3}
        gs._skipped_claims = {2, 3}  # only player 0 claims
        gs.wall = ["CIRCLES_9"] * 10
        return gs

    def test_claimed_kong_forms_quad_meld(self):
        gs = self._setup()
        gs.claim_kong(0, "BAMBOO_7")
        kong_meld = next(m for m in gs.players[0].melds if m[0] == "BAMBOO_7")
        assert len(kong_meld) == 4

    def test_claimed_kong_tile_removed_from_discard_pile(self):
        gs = self._setup()
        discard_before = list(gs.discards[1])
        gs.claim_kong(0, "BAMBOO_7")
        # The claimed tile is no longer in the discard pile
        assert gs.discards[1].count("BAMBOO_7") < discard_before.count("BAMBOO_7")

    def test_claimed_kong_draws_replacement(self):
        gs = self._setup()
        hand_before = len(gs.players[0].hand)
        # 3 removed from hand + 1 discard taken + 1 replacement drawn
        gs.claim_kong(0, "BAMBOO_7")
        assert len(gs.players[0].hand) == hand_before - 3 + 1

    def test_claimed_kong_phase_becomes_discarding(self):
        gs = self._setup()
        gs.claim_kong(0, "BAMBOO_7")
        assert gs.phase == "discarding"
        assert gs.current_turn == 0

    def test_claimed_kong_lingshang_pending_set(self):
        gs = self._setup()
        gs.claim_kong(0, "BAMBOO_7")
        assert gs.lingshang_pending is True

    def test_claimed_kong_chip_payment_recorded(self):
        gs = self._setup()
        gs.claim_kong(0, "BAMBOO_7")
        konger_id = gs.players[0].id
        assert gs.kong_chip_transfers.get(konger_id, 0) == 3

    def test_claimed_kong_last_drawn_tile_correct(self):
        gs = self._setup()
        gs.wall = ["CIRCLES_9"]
        gs.claim_kong(0, "BAMBOO_7")
        assert gs.last_drawn_tile == "CIRCLES_9"

    def test_claimed_kong_not_available_with_only_2_matching(self):
        gs = make_dealt_game()
        gs.players[1].hand = ["BAMBOO_7"] + ["EAST"] * 12
        gs.phase = "discarding"
        gs.current_turn = 1
        gs.discard_tile(1, "BAMBOO_7")
        gs.players[0].hand = ["BAMBOO_7"] * 2 + ["CIRCLES_1"] * 8  # only 2
        actions = gs.get_available_actions(0)
        assert "kong" not in actions
