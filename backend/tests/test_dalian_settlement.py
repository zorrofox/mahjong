"""
test_dalian_settlement.py - 大连穷胡筹码结算单元测试

覆盖：
  - 自摸时三家各按自己番数付钱
  - 荣和时只有放炮者付钱，其余不动
  - 未开门（loser 无副露）+1 番加成
  - 三家门清（三位 loser 均无副露）+1 番加成
  - 庄家胡 han_total 包含庄家番
"""

import pytest
from game.hand import calculate_han_dalian


CHIP_CAP = 64
INITIAL_CHIPS = 1000


def _unit(han: int) -> int:
    return min(CHIP_CAP, 2 ** (han - 1))


# ---------------------------------------------------------------------------
# calculate_han_dalian 返回值验证
# ---------------------------------------------------------------------------

class TestDalianHanCalculation:

    def _call(self, **kw):
        defaults = dict(
            concealed_tiles=[],
            declared_melds=[],
            ron=False,
            player_seat=0,
            round_wind_idx=0,
            ling_shang=False,
            is_dealer=False,
            winning_tile=None,
            rob_kong=False,
        )
        defaults.update(kw)
        return calculate_han_dalian(**defaults)

    def test_base_total_non_dealer_ron(self):
        """非庄家、荣和：基础 1 番"""
        result = self._call(ron=True)
        assert result['total'] == 1

    def test_base_total_non_dealer_tsumo(self):
        """非庄家、自摸：基础 1 + 自摸 1 = 2 番"""
        result = self._call(ron=False)
        assert result['total'] == 2

    def test_dealer_ron(self):
        """庄家、荣和：基础 1 + 庄家 1 = 2 番"""
        result = self._call(ron=True, is_dealer=True)
        assert result['total'] == 2

    def test_dealer_tsumo(self):
        """庄家、自摸：基础 1 + 自摸 1 + 庄家 1 = 3 番"""
        result = self._call(ron=False, is_dealer=True)
        assert result['total'] == 3

    def test_ling_shang_tsumo(self):
        """杠上开花自摸：基础 1 + 自摸 1 + 杠上开花 2 = 4 番"""
        result = self._call(ron=False, ling_shang=True)
        assert result['total'] == 4

    def test_rob_kong_ron(self):
        """抢杠胡荣和：基础 1 + 抢杠胡 2 = 3 番"""
        result = self._call(ron=True, rob_kong=True)
        assert result['total'] == 3


# ---------------------------------------------------------------------------
# 筹码结算逻辑（模拟 websocket 结算代码）
# ---------------------------------------------------------------------------

def _simulate_dalian_settlement(
    han: int,
    win_ron: bool,
    winner_idx: int,
    discarder_idx,          # None if tsumo
    losers_melds: list,     # list of 3 bools: does each loser have melds?
    initial=INITIAL_CHIPS,
):
    """
    模拟大连穷胡结算，返回 {player_idx: chip_delta} 的 4 人字典。
    winner_idx 的 chip_delta > 0；losers 的 chip_delta < 0 或 0.
    """
    n = 4
    scores = {i: initial for i in range(n)}

    others_clean = all(not has_meld for has_meld in losers_melds)
    three_clean_bonus = 1 if others_clean else 0

    def loser_unit(loser_idx: int, is_discarder: bool = False) -> int:
        # loser_idx is index into the 3-element losers list (not player idx)
        extra = (1 if not losers_melds[loser_idx] else 0)
        extra += three_clean_bonus
        if is_discarder:
            extra += 1
        return min(CHIP_CAP, 2 ** (han + extra - 1))

    # Map loser indices: players other than winner_idx in order
    loser_player_idxs = [i for i in range(n) if i != winner_idx]

    if win_ron and discarder_idx is not None:
        discarder_local = loser_player_idxs.index(discarder_idx)
        pay = loser_unit(discarder_local, is_discarder=True)
        scores[winner_idx] += pay
        scores[discarder_idx] -= pay
    else:
        for local_i, player_i in enumerate(loser_player_idxs):
            pay = loser_unit(local_i)
            scores[winner_idx] += pay
            scores[player_i] -= pay

    return {i: scores[i] - initial for i in range(n)}


class TestDalianSettlement:

    def test_tsumo_3_fan_all_melds(self):
        """自摸 3 番（假设 han=3），三家均有副露 → 各付 unit(3)=4"""
        # 3 番 unit = 2^(3-1) = 4
        deltas = _simulate_dalian_settlement(
            han=3, win_ron=False, winner_idx=0, discarder_idx=None,
            losers_melds=[True, True, True],  # 三家均有副露
        )
        assert deltas[0] == 3 * 4   # 赢家收 12
        assert deltas[1] == -4
        assert deltas[2] == -4
        assert deltas[3] == -4

    def test_ron_2_fan_discarder_pays_han_plus1(self):
        """荣和 2 番：放炮者按 han+1=3 番付（有副露时无未开门加成）"""
        # 三家均有副露，放炮为 player 2
        # 荣和只有放炮者付：extra=0（有副露）+ 1（放炮）= 1 → han+1=3 → unit=4
        deltas = _simulate_dalian_settlement(
            han=2, win_ron=True, winner_idx=0, discarder_idx=2,
            losers_melds=[True, True, True],
        )
        assert deltas[2] == -4   # 放炮者付 4
        assert deltas[0] == 4   # 赢家收 4
        assert deltas[1] == 0
        assert deltas[3] == 0

    def test_loser_no_meld_extra_1(self):
        """未开门（loser 无副露）额外 +1 番"""
        # han=2, 自摸, player 1 无副露, player 2 和 3 有副露
        # loser0 (player1) extra=1（无副露）+0（三家非全清）= 1 → han+1=3 → unit=4
        # loser1 (player2) extra=0 → han=2 → unit=2
        # loser2 (player3) extra=0 → han=2 → unit=2
        deltas = _simulate_dalian_settlement(
            han=2, win_ron=False, winner_idx=0, discarder_idx=None,
            losers_melds=[False, True, True],
        )
        assert deltas[1] == -4
        assert deltas[2] == -2
        assert deltas[3] == -2
        assert deltas[0] == 4 + 2 + 2

    def test_three_clean_bonus(self):
        """三家门清额外 +1（所有 loser 无副露时叠加）"""
        # han=2, 自摸, 三家均无副露
        # 每位 loser: extra=1（无副露）+1（三家门清）= 2 → han+2=4 → unit=8
        deltas = _simulate_dalian_settlement(
            han=2, win_ron=False, winner_idx=0, discarder_idx=None,
            losers_melds=[False, False, False],
        )
        assert deltas[1] == -8
        assert deltas[2] == -8
        assert deltas[3] == -8
        assert deltas[0] == 24

    def test_three_clean_bonus_with_ron(self):
        """三家门清 + 放炮：放炮者 extra=2+1=3 → han+3=5 → unit=16"""
        # han=2, 荣和, 三家均无副露, 放炮 player2
        # extra for discarder: 1（无副露）+1（三家门清）+1（放炮）=3 → han+3=5 → unit=16
        deltas = _simulate_dalian_settlement(
            han=2, win_ron=True, winner_idx=0, discarder_idx=2,
            losers_melds=[False, False, False],
        )
        assert deltas[2] == -16
        assert deltas[0] == 16
        assert deltas[1] == 0
        assert deltas[3] == 0

    def test_dealer_han_includes_dealer_bonus(self):
        """庄家胡 han_total 包含庄家番"""
        result = calculate_han_dalian(
            concealed_tiles=[], declared_melds=[], ron=True,
            is_dealer=True, winning_tile=None,
        )
        # 基础 1 + 庄家 1 = 2
        assert result['total'] == 2
        dealer_names = [x['name_cn'] for x in result['breakdown']]
        assert '庄家' in dealer_names

    def test_chip_cap_applied(self):
        """7+ 番封顶 CHIP_CAP=64"""
        pay = _unit(8)
        assert pay == CHIP_CAP

    def test_ron_only_discarder_pays(self):
        """荣和时除放炮者外其余 loser 不付钱"""
        deltas = _simulate_dalian_settlement(
            han=3, win_ron=True, winner_idx=0, discarder_idx=1,
            losers_melds=[True, True, True],
        )
        assert deltas[2] == 0  # 非放炮者不付
        assert deltas[3] == 0

    def test_tsumo_all_losers_pay(self):
        """自摸时三位 loser 全部付钱"""
        deltas = _simulate_dalian_settlement(
            han=2, win_ron=False, winner_idx=0, discarder_idx=None,
            losers_melds=[True, True, True],
        )
        for i in [1, 2, 3]:
            assert deltas[i] < 0

    def test_zero_sum(self):
        """结算后总筹码不变（零和博弈）"""
        deltas = _simulate_dalian_settlement(
            han=3, win_ron=False, winner_idx=2, discarder_idx=None,
            losers_melds=[False, True, False],
        )
        assert sum(deltas.values()) == 0
