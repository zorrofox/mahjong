"""
test_dalian_hand.py - 大连穷胡手牌规则单元测试

覆盖：
  - decompose_winning_hand_dalian：三元牌禁刻子
  - is_winning_hand_dalian：三色全/幺九/至少一刻/禁手把一
  - _is_kanchan：坎张检测（True/False）
  - calculate_han_dalian：各番型加成
"""

import pytest
from game.hand import (
    decompose_winning_hand_dalian,
    is_winning_hand_dalian,
    _is_kanchan,
    calculate_han_dalian,
)


# ---------------------------------------------------------------------------
# decompose_winning_hand_dalian — 三元牌禁刻子
# ---------------------------------------------------------------------------

class TestDecomposeWinningHandDalian:

    def test_dragon_pair_only_valid(self):
        """三元牌（中）作将，剩余可分解为4组刻/顺"""
        # 手: 中中 + 1万1万1万2万3万4万1条1条1条1筒2筒3筒 (14张)
        tiles = (
            ['RED', 'RED']
            + ['CHARACTERS_1'] * 3
            + ['CHARACTERS_2', 'CHARACTERS_3', 'CHARACTERS_4']
            + ['BAMBOO_1'] * 3
            + ['CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3']
        )
        result = decompose_winning_hand_dalian(tiles)
        assert result is not None
        assert result['pair'] == 'RED'

    def test_dragon_cannot_form_pung(self):
        """三张中无法被拆成刻子（中只能做将）"""
        # 手: 中中中 + 1万1万2万3万4万 + 1条2条3条 + 1筒2筒3筒  (14张)
        tiles = (
            ['RED'] * 3
            + ['CHARACTERS_1'] * 2
            + ['CHARACTERS_2', 'CHARACTERS_3', 'CHARACTERS_4']
            + ['BAMBOO_1', 'BAMBOO_2', 'BAMBOO_3']
            + ['CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3']
        )
        # 三张 RED，但 RED 不能做刻子——所以 RED 的对子成将，剩余11张
        # 11-9=2 无法整除3 => None
        result = decompose_winning_hand_dalian(tiles)
        # 有一张 RED 多余无法归组
        assert result is None

    def test_wind_can_form_pung(self):
        """风牌（EAST）可以组成刻子"""
        tiles = (
            ['RED', 'RED']
            + ['EAST'] * 3
            + ['CHARACTERS_1', 'CHARACTERS_2', 'CHARACTERS_3']
            + ['BAMBOO_1', 'BAMBOO_2', 'BAMBOO_3']
            + ['CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3']
        )
        result = decompose_winning_hand_dalian(tiles)
        assert result is not None
        pung_types = [g['tiles'][0] for g in result['groups'] if g['type'] == 'pung']
        assert 'EAST' in pung_types

    def test_no_seven_pairs(self):
        """大连穷胡不支持七对子"""
        # 7 个不同对子 (14张)
        tiles = [
            'BAMBOO_1', 'BAMBOO_1',
            'BAMBOO_3', 'BAMBOO_3',
            'BAMBOO_5', 'BAMBOO_5',
            'CIRCLES_2', 'CIRCLES_2',
            'CIRCLES_4', 'CIRCLES_4',
            'CHARACTERS_1', 'CHARACTERS_1',
            'EAST', 'EAST',
        ]
        result = decompose_winning_hand_dalian(tiles)
        # 七对子不在大连规则中，所以这里要看能否分解为1将+4组
        # 以上14张无法分解为标准 1+4 结构，应返回 None
        assert result is None


# ---------------------------------------------------------------------------
# is_winning_hand_dalian
# ---------------------------------------------------------------------------

# 辅助：构造一个合法大连基础胡型（三色全、有幺九/风牌、有刻子）
def _base_hand():
    """
    合法大连基础胡型：
    将：EAST EAST (风牌)
    刻：BAMBOO_1 BAMBOO_1 BAMBOO_1
    顺：CHARACTERS_1 CHARACTERS_2 CHARACTERS_3
    顺：CIRCLES_1 CIRCLES_2 CIRCLES_3
    顺：BAMBOO_7 BAMBOO_8 BAMBOO_9
    = 14 张，三色全，有幺九，有刻子
    """
    return (
        ['EAST', 'EAST']
        + ['BAMBOO_1'] * 3
        + ['CHARACTERS_1', 'CHARACTERS_2', 'CHARACTERS_3']
        + ['CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3']
        + ['BAMBOO_7', 'BAMBOO_8', 'BAMBOO_9']
    )


class TestIsWinningHandDalian:

    def test_valid_base_hand(self):
        """合法基础胡型应返回 True"""
        assert is_winning_hand_dalian(_base_hand(), 0, [])

    def test_missing_san_se_quan(self):
        """缺色（只有条和万，没有饼）应返回 False"""
        tiles = (
            ['EAST', 'EAST']
            + ['BAMBOO_1'] * 3
            + ['CHARACTERS_1', 'CHARACTERS_2', 'CHARACTERS_3']
            + ['BAMBOO_3', 'BAMBOO_4', 'BAMBOO_5']
            + ['BAMBOO_7', 'BAMBOO_8', 'BAMBOO_9']
        )
        assert not is_winning_hand_dalian(tiles, 0, [])

    def test_no_terminal_no_honor_fails(self):
        """全是 2-8 数牌无风无字，没有幺九，应失败"""
        # 凑 14 张，三色均有，但全是 2-8
        tiles = (
            ['BAMBOO_2', 'BAMBOO_2']
            + ['BAMBOO_2', 'BAMBOO_3', 'BAMBOO_4']
            + ['CIRCLES_2', 'CIRCLES_3', 'CIRCLES_4']
            + ['CHARACTERS_2', 'CHARACTERS_3', 'CHARACTERS_4']
            + ['BAMBOO_5', 'BAMBOO_6', 'BAMBOO_7']
        )
        assert not is_winning_hand_dalian(tiles, 0, [])

    def test_honor_exempts_yaojiu_check(self):
        """包含风牌/字牌时豁免幺九检查（全 2-8 + EAST 成将）"""
        tiles = (
            ['EAST', 'EAST']
            + ['BAMBOO_2', 'BAMBOO_3', 'BAMBOO_4']
            + ['CIRCLES_2', 'CIRCLES_3', 'CIRCLES_4']
            + ['CHARACTERS_2', 'CHARACTERS_3', 'CHARACTERS_4']
            + ['BAMBOO_5', 'BAMBOO_5', 'BAMBOO_5']
        )
        # 有 EAST 所以豁免幺九；但需要至少一刻子 (BAMBOO_5 * 3)
        assert is_winning_hand_dalian(tiles, 0, [])

    def test_no_pung_fails(self):
        """全顺子无刻子，应失败"""
        # 将 EAST EAST，四组顺子
        tiles = (
            ['EAST', 'EAST']
            + ['BAMBOO_1', 'BAMBOO_2', 'BAMBOO_3']
            + ['CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3']
            + ['CHARACTERS_1', 'CHARACTERS_2', 'CHARACTERS_3']
            + ['BAMBOO_7', 'BAMBOO_8', 'BAMBOO_9']
        )
        assert not is_winning_hand_dalian(tiles, 0, [])

    def test_declared_pung_counts(self):
        """副露中有刻子时满足至少一刻子条件"""
        # 副露刻子（BAMBOO_1 * 3）
        declared_melds = [['BAMBOO_1', 'BAMBOO_1', 'BAMBOO_1']]
        # 隐藏牌 14-3=11 张
        concealed = (
            ['EAST', 'EAST']
            + ['CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3']
            + ['CHARACTERS_1', 'CHARACTERS_2', 'CHARACTERS_3']
            + ['BAMBOO_7', 'BAMBOO_8', 'BAMBOO_9']
        )
        assert is_winning_hand_dalian(concealed, 1, declared_melds)

    def test_four_declared_melds_forbidden(self):
        """四副全副露（手把一）禁止胡牌"""
        declared_melds = [
            ['BAMBOO_1', 'BAMBOO_1', 'BAMBOO_1'],
            ['CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3'],
            ['CHARACTERS_1', 'CHARACTERS_2', 'CHARACTERS_3'],
            ['BAMBOO_7', 'BAMBOO_8', 'BAMBOO_9'],
        ]
        # 隐藏牌 14-12=2 张（就是将）
        concealed = ['EAST', 'EAST']
        assert not is_winning_hand_dalian(concealed, 4, declared_melds)

    def test_dragon_pung_not_allowed_in_hand(self):
        """三张中形成刻子违反规则（三元牌禁刻子）"""
        tiles = (
            ['GREEN', 'GREEN']
            + ['RED'] * 3
            + ['BAMBOO_1', 'BAMBOO_2', 'BAMBOO_3']
            + ['CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3']
            + ['CHARACTERS_1', 'CHARACTERS_2', 'CHARACTERS_3']
        )
        # RED*3 无法成刻子 → decompose 返回 None → False
        assert not is_winning_hand_dalian(tiles, 0, [])


# ---------------------------------------------------------------------------
# _is_kanchan — 坎张/夹胡检测
# ---------------------------------------------------------------------------

class TestIsKanchan:

    def test_kanchan_true_simple(self):
        """简单坎张：手有 4和6，胡 5"""
        concealed_without_win = [
            'BAMBOO_4', 'BAMBOO_6',
            # 其余牌（用来凑合法手型，本函数只检测坎张位）
        ]
        assert _is_kanchan('BAMBOO_5', concealed_without_win)

    def test_two_sided_not_kanchan(self):
        """双面等待不是坎张：手有 4,5，胡 6（可以是 4-5-6 的高端）"""
        concealed_without_win = ['BAMBOO_4', 'BAMBOO_5', 'BAMBOO_7', 'BAMBOO_8']
        # 可能是双面（胡 3 或 6），所以不算坎张
        assert not _is_kanchan('BAMBOO_6', concealed_without_win)

    def test_two_sided_high_end_not_kanchan(self):
        """双面：手有 6,7，胡 5（可能是 5-6-7 低端）"""
        concealed_without_win = ['BAMBOO_6', 'BAMBOO_7']
        assert not _is_kanchan('BAMBOO_5', concealed_without_win)

    def test_honor_tile_not_kanchan(self):
        """风牌/字牌无法坎张"""
        assert not _is_kanchan('EAST', [])
        assert not _is_kanchan('RED', [])

    def test_terminal_1_not_kanchan(self):
        """1 不在 2-8 范围内，不是坎张"""
        assert not _is_kanchan('BAMBOO_1', ['BAMBOO_2', 'BAMBOO_3'])

    def test_terminal_9_not_kanchan(self):
        """9 不在 2-8 范围内，不是坎张"""
        assert not _is_kanchan('BAMBOO_9', ['BAMBOO_7', 'BAMBOO_8'])

    def test_kanchan_with_low_number(self):
        """坎张最小情形：胡 2，手有 1 和 3"""
        concealed_without_win = ['CIRCLES_1', 'CIRCLES_3']
        assert _is_kanchan('CIRCLES_2', concealed_without_win)

    def test_kanchan_with_high_number(self):
        """坎张最大情形：胡 8，手有 7 和 9"""
        concealed_without_win = ['CIRCLES_7', 'CIRCLES_9']
        assert _is_kanchan('CIRCLES_8', concealed_without_win)

    def test_no_matching_tiles_not_kanchan(self):
        """坎张所需的上下牌不存在"""
        concealed_without_win = ['BAMBOO_1', 'BAMBOO_2']
        assert not _is_kanchan('BAMBOO_5', concealed_without_win)


# ---------------------------------------------------------------------------
# calculate_han_dalian — 番型计算
# ---------------------------------------------------------------------------

class TestCalculateHanDalian:

    def _base_call(self, **kwargs):
        defaults = dict(
            concealed_tiles=['EAST', 'EAST',
                             'BAMBOO_1', 'BAMBOO_1', 'BAMBOO_1',
                             'CHARACTERS_1', 'CHARACTERS_2', 'CHARACTERS_3',
                             'CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3',
                             'BAMBOO_7', 'BAMBOO_8', 'BAMBOO_9'],
            declared_melds=[],
            ron=False,
            player_seat=0,
            round_wind_idx=0,
            ling_shang=False,
            is_dealer=False,
            winning_tile='BAMBOO_9',
            rob_kong=False,
        )
        defaults.update(kwargs)
        return calculate_han_dalian(**defaults)

    def test_base_1_fan(self):
        """基础始终 +1"""
        result = self._base_call()
        names = [x['name_cn'] for x in result['breakdown']]
        assert '基础' in names
        assert result['total'] >= 1

    def test_tsumo_adds_1(self):
        """自摸 +1"""
        result = self._base_call(ron=False)
        names = [x['name_cn'] for x in result['breakdown']]
        assert '自摸' in names

    def test_ron_no_tsumo(self):
        """荣和不计自摸"""
        result = self._base_call(ron=True)
        names = [x['name_cn'] for x in result['breakdown']]
        assert '自摸' not in names

    def test_dealer_adds_1(self):
        """庄家 +1"""
        result = self._base_call(is_dealer=True)
        names = [x['name_cn'] for x in result['breakdown']]
        assert '庄家' in names
        total_nodeal = self._base_call(is_dealer=False)['total']
        assert result['total'] == total_nodeal + 1

    def test_ling_shang_adds_2(self):
        """杠上开花 +2（自摸）"""
        result = self._base_call(ling_shang=True, ron=False)
        names = [x['name_cn'] for x in result['breakdown']]
        assert '杠上开花' in names
        entry = next(x for x in result['breakdown'] if x['name_cn'] == '杠上开花')
        assert entry['fan'] == 2

    def test_ling_shang_not_applied_to_ron(self):
        """杠上开花不计荣和"""
        result = self._base_call(ling_shang=True, ron=True)
        names = [x['name_cn'] for x in result['breakdown']]
        assert '杠上开花' not in names

    def test_rob_kong_adds_2(self):
        """抢杠胡 +2"""
        result = self._base_call(rob_kong=True, ron=True)
        names = [x['name_cn'] for x in result['breakdown']]
        assert '抢杠胡' in names
        entry = next(x for x in result['breakdown'] if x['name_cn'] == '抢杠胡')
        assert entry['fan'] == 2

    def test_kanchan_adds_1_on_ron(self):
        """夹胡 +1（荣和时坎张）"""
        # 手有 CIRCLES_4 CIRCLES_6（去掉将后），胡 CIRCLES_5 (坎张)
        tiles = (
            ['EAST', 'EAST']
            + ['BAMBOO_1'] * 3
            + ['CHARACTERS_1', 'CHARACTERS_2', 'CHARACTERS_3']
            + ['BAMBOO_7', 'BAMBOO_8', 'BAMBOO_9']
            + ['CIRCLES_4', 'CIRCLES_5', 'CIRCLES_6']
        )
        # winning_tile = CIRCLES_5，将其从手牌中移除模拟 ron 前状态
        hand_before_win = list(tiles)
        hand_before_win.remove('CIRCLES_5')
        result = calculate_han_dalian(
            concealed_tiles=tiles,  # 已加入赢牌
            declared_melds=[],
            ron=True,
            winning_tile='CIRCLES_5',
        )
        names = [x['name_cn'] for x in result['breakdown']]
        assert '夹胡' in names

    def test_kanchan_not_on_tsumo(self):
        """夹胡只在荣和时计入，自摸不计"""
        tiles = (
            ['EAST', 'EAST']
            + ['BAMBOO_1'] * 3
            + ['CHARACTERS_1', 'CHARACTERS_2', 'CHARACTERS_3']
            + ['BAMBOO_7', 'BAMBOO_8', 'BAMBOO_9']
            + ['CIRCLES_4', 'CIRCLES_5', 'CIRCLES_6']
        )
        result = calculate_han_dalian(
            concealed_tiles=tiles,
            declared_melds=[],
            ron=False,
            winning_tile='CIRCLES_5',
        )
        names = [x['name_cn'] for x in result['breakdown']]
        assert '夹胡' not in names
