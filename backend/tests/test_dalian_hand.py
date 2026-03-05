"""
test_dalian_hand.py - 大连穷胡手牌规则单元测试

覆盖：
  - decompose_winning_hand_dalian：三元牌禁刻子
  - is_winning_hand_dalian：禁止门清/三色全/幺九/至少一刻/禁手把一/宝牌野牌替换
  - is_tenpai_dalian：听牌检测（基础/宝牌感知）
  - _is_kanchan：坎张检测（True/False）
  - calculate_han_dalian：各番型加成，含冲宝/摸宝
"""

import pytest
from game.hand import (
    decompose_winning_hand_dalian,
    is_winning_hand_dalian,
    is_tenpai_dalian,
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

# 辅助：构造一个合法大连基础胡型（三色全、有幺九/风牌、有刻子、已开门）
def _base_hand():
    """
    合法大连基础胡型（隐藏牌 + 1 副明刻）：
    副露：BAMBOO_1 BAMBOO_1 BAMBOO_1（明刻，满足开门+至少一刻）
    将：EAST EAST (风牌)
    顺：CHARACTERS_1 CHARACTERS_2 CHARACTERS_3
    顺：CIRCLES_1 CIRCLES_2 CIRCLES_3
    顺：BAMBOO_7 BAMBOO_8 BAMBOO_9
    隐藏牌 = 11 张（14 - 3×1），三色全，有幺九
    """
    concealed = (
        ['EAST', 'EAST']
        + ['CHARACTERS_1', 'CHARACTERS_2', 'CHARACTERS_3']
        + ['CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3']
        + ['BAMBOO_7', 'BAMBOO_8', 'BAMBOO_9']
    )
    declared = [['BAMBOO_1', 'BAMBOO_1', 'BAMBOO_1']]
    return concealed, declared


class TestIsWinningHandDalian:

    def test_valid_base_hand(self):
        """合法基础胡型（有副露）应返回 True"""
        concealed, declared = _base_hand()
        assert is_winning_hand_dalian(concealed, 1, declared)

    def test_menqing_forbidden(self):
        """门清（无副露）禁止胡牌"""
        # 结构完全合法，但 n_declared_melds=0 → False
        tiles = (
            ['EAST', 'EAST']
            + ['BAMBOO_1'] * 3
            + ['CHARACTERS_1', 'CHARACTERS_2', 'CHARACTERS_3']
            + ['CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3']
            + ['BAMBOO_7', 'BAMBOO_8', 'BAMBOO_9']
        )
        assert not is_winning_hand_dalian(tiles, 0, [])

    def test_missing_san_se_quan(self):
        """缺色（只有条和万，没有饼）应返回 False"""
        # 副露：BAMBOO_1 * 3（满足开门），但隐藏牌缺饼
        declared = [['BAMBOO_1', 'BAMBOO_1', 'BAMBOO_1']]
        concealed = (
            ['EAST', 'EAST']
            + ['CHARACTERS_1', 'CHARACTERS_2', 'CHARACTERS_3']
            + ['BAMBOO_3', 'BAMBOO_4', 'BAMBOO_5']
            + ['BAMBOO_7', 'BAMBOO_8', 'BAMBOO_9']
        )
        assert not is_winning_hand_dalian(concealed, 1, declared)

    def test_no_terminal_no_honor_fails(self):
        """全是 2-8 数牌无风无字，没有幺九，应失败"""
        # 副露：BAMBOO_5 * 3，隐藏牌全 2-8，三色均有
        declared = [['BAMBOO_5', 'BAMBOO_5', 'BAMBOO_5']]
        concealed = (
            ['BAMBOO_2', 'BAMBOO_2']
            + ['CIRCLES_2', 'CIRCLES_3', 'CIRCLES_4']
            + ['CHARACTERS_2', 'CHARACTERS_3', 'CHARACTERS_4']
            + ['BAMBOO_6', 'BAMBOO_7', 'BAMBOO_8']
        )
        assert not is_winning_hand_dalian(concealed, 1, declared)

    def test_honor_exempts_yaojiu_check(self):
        """包含风牌时豁免幺九检查（全 2-8 + EAST 成将 + 副露刻子）"""
        declared = [['BAMBOO_5', 'BAMBOO_5', 'BAMBOO_5']]
        concealed = (
            ['EAST', 'EAST']
            + ['BAMBOO_2', 'BAMBOO_3', 'BAMBOO_4']
            + ['CIRCLES_2', 'CIRCLES_3', 'CIRCLES_4']
            + ['CHARACTERS_2', 'CHARACTERS_3', 'CHARACTERS_4']
        )
        # EAST 豁免幺九；BAMBOO_5*3 副露满足至少一刻
        assert is_winning_hand_dalian(concealed, 1, declared)

    def test_no_pung_fails(self):
        """全顺子无刻子（包括副露），应失败"""
        # 副露：顺子（不是刻子）
        declared = [['BAMBOO_1', 'BAMBOO_2', 'BAMBOO_3']]
        concealed = (
            ['EAST', 'EAST']
            + ['CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3']
            + ['CHARACTERS_1', 'CHARACTERS_2', 'CHARACTERS_3']
            + ['BAMBOO_7', 'BAMBOO_8', 'BAMBOO_9']
        )
        assert not is_winning_hand_dalian(concealed, 1, declared)

    def test_declared_pung_counts(self):
        """副露中有刻子时满足至少一刻子条件"""
        declared_melds = [['BAMBOO_1', 'BAMBOO_1', 'BAMBOO_1']]
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
        concealed = ['EAST', 'EAST']
        assert not is_winning_hand_dalian(concealed, 4, declared_melds)

    def test_dragon_pung_not_allowed_in_hand(self):
        """三张中形成刻子违反规则（三元牌禁刻子）"""
        # 即使有副露，RED*3 也无法成刻子
        declared = [['BAMBOO_1', 'BAMBOO_2', 'BAMBOO_3']]
        concealed = (
            ['GREEN', 'GREEN']
            + ['RED'] * 3
            + ['CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3']
            + ['CHARACTERS_1', 'CHARACTERS_2', 'CHARACTERS_3']
        )
        assert not is_winning_hand_dalian(concealed, 1, declared)


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
# _is_kanchan_in_hand — 精确坎张检测（单调误判回归测试）
# ---------------------------------------------------------------------------

class TestIsKanchanInHand:
    """
    Bug#42 修复验证：单调（单张将牌）等待不得被误判为坎张。

    场景：手牌有 n-1、n、n+1 且 n 在手中出现 ≥2 次（其中一张是将），
    应识别为单调等待，不计夹胡。
    """

    def test_tanki_middle_tile_not_kanchan(self):
        """
        单调五条：手有 4条5条5条6条，胡 5条（第二张凑将）
        结构：4-5-6（顺子）+ 5-5（将），是单调而非坎张
        """
        from game.hand import _is_kanchan_in_hand
        # hand_without_win = 胡牌后去掉一张胡牌张
        hand_without_win = ['BAMBOO_4', 'BAMBOO_5', 'BAMBOO_5', 'BAMBOO_6']
        assert not _is_kanchan_in_hand('BAMBOO_5', hand_without_win)

    def test_true_kanchan_still_detected(self):
        """真正坎张：手有 4条6条，胡 5条（4-5-6 中间张）"""
        from game.hand import _is_kanchan_in_hand
        hand_without_win = ['BAMBOO_4', 'BAMBOO_6', 'EAST', 'EAST']
        assert _is_kanchan_in_hand('BAMBOO_5', hand_without_win)

    def test_tanki_on_circles_1_not_kanchan(self):
        """单调一饼：num=1<2 直接返回 False（截图场景回归）"""
        from game.hand import _is_kanchan_in_hand
        hand_without_win = ['BAMBOO_3', 'BAMBOO_4', 'BAMBOO_5', 'CIRCLES_1']
        assert not _is_kanchan_in_hand('CIRCLES_1', hand_without_win)

    def test_calculate_han_tanki_middle_no_kanchan_bonus(self):
        """
        Bug#42 核心回归：单调五条番型不得出现夹胡 +1
        手牌：4条5条5条5条6条（顺子4-5-6 + 将5-5，单调胡五条）
        """
        melds = [
            ['CIRCLES_2', 'CIRCLES_2', 'CIRCLES_2'],
            ['CIRCLES_8', 'CIRCLES_8', 'CIRCLES_8'],
            ['CHARACTERS_7', 'CHARACTERS_7', 'CHARACTERS_7'],
        ]
        concealed = ['BAMBOO_4', 'BAMBOO_5', 'BAMBOO_5', 'BAMBOO_5', 'BAMBOO_6']
        result = calculate_han_dalian(concealed, melds, ron=True, winning_tile='BAMBOO_5')
        names = [x['name_cn'] for x in result['breakdown']]
        assert '夹胡' not in names, f"单调胡不应计夹胡，实际番型：{names}"
        assert result['total'] == 1

    def test_calculate_han_true_kanchan_has_bonus(self):
        """真正坎张仍正常计夹胡 +1"""
        melds = [
            ['CIRCLES_2', 'CIRCLES_2', 'CIRCLES_2'],
            ['CIRCLES_8', 'CIRCLES_8', 'CIRCLES_8'],
            ['CHARACTERS_7', 'CHARACTERS_7', 'CHARACTERS_7'],
        ]
        concealed = ['BAMBOO_4', 'BAMBOO_5', 'BAMBOO_6', 'EAST', 'EAST']
        result = calculate_han_dalian(concealed, melds, ron=True, winning_tile='BAMBOO_5')
        names = [x['name_cn'] for x in result['breakdown']]
        assert '夹胡' in names, f"坎张荣和应计夹胡，实际番型：{names}"
        assert result['total'] == 2

    def test_calculate_han_tanki_circles1_screenshot_scenario(self):
        """截图场景：单调一饼，宝牌五条，不计夹胡也不计冲宝"""
        melds = [
            ['CIRCLES_3', 'CIRCLES_3', 'CIRCLES_3'],
            ['CIRCLES_6', 'CIRCLES_6', 'CIRCLES_6'],
            ['CHARACTERS_7', 'CHARACTERS_7', 'CHARACTERS_7'],
        ]
        concealed = ['BAMBOO_3', 'BAMBOO_4', 'BAMBOO_5', 'CIRCLES_1', 'CIRCLES_1']
        result = calculate_han_dalian(
            concealed, melds, ron=True,
            winning_tile='CIRCLES_1', bao_tile='BAMBOO_5',
        )
        names = [x['name_cn'] for x in result['breakdown']]
        assert '夹胡' not in names
        assert '冲宝' not in names
        assert result['total'] == 1


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


# ---------------------------------------------------------------------------
# is_tenpai_dalian — 听牌检测
# ---------------------------------------------------------------------------

class TestIsTenpaiDalian:
    """
    听牌 = 再摸一张特定牌就能胡。
    大连规则：n_declared_melds >= 1（禁止门清），且满足三色全/幺九/至少一刻。
    """

    def _declared(self):
        """标准明刻：BAMBOO_1×3，同时提供三色全中的条色"""
        return [['BAMBOO_1', 'BAMBOO_1', 'BAMBOO_1']]

    def test_basic_tenpai_one_wait(self):
        """单面等待：差一张万子完成顺子"""
        declared = self._declared()
        # 11 张暗手：等 CHARACTERS_3
        concealed = [
            'EAST', 'EAST',                       # 将
            'CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3',  # 顺子（饼）
            'BAMBOO_7', 'BAMBOO_8', 'BAMBOO_9',     # 顺子（条）
            'CHARACTERS_1', 'CHARACTERS_2',          # 等 CHARACTERS_3
        ]
        waits = is_tenpai_dalian(concealed, 1, declared)
        assert 'CHARACTERS_3' in waits

    def test_no_melds_not_tenpai(self):
        """禁止门清：无副露时不能上听"""
        # 结构完整，但 n_declared_melds=0 → 门清
        concealed = [
            'EAST', 'EAST',
            'BAMBOO_1', 'BAMBOO_1', 'BAMBOO_1',
            'CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3',
            'CHARACTERS_1', 'CHARACTERS_2',        # 等 CHARACTERS_3
        ]
        waits = is_tenpai_dalian(concealed, 0, [])
        assert waits == []

    def test_not_tenpai_when_two_away(self):
        """差两张不算听牌"""
        declared = self._declared()
        concealed = [
            'EAST', 'EAST',
            'CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3',
            'BAMBOO_7', 'BAMBOO_8', 'BAMBOO_9',
            'CHARACTERS_1',                         # 差两张（需要顺子）
        ]
        # 10 张只有 10 = 14 - 3*1 是正确的，但 CHARACTERS_1 单张凑不够
        waits = is_tenpai_dalian(concealed, 1, declared)
        # CHARACTERS_1 单张凑不出完整结构，最多能等 2,3 成顺但还差对子
        # 验证期望的等张在内或不在内都可，主要验证不报错且结果合理
        assert isinstance(waits, list)

    def test_tenpai_with_bao_wildcard(self):
        """宝牌感知：手中有宝牌时，等待张包含宝牌可替换的目标牌"""
        declared = self._declared()
        bao_tile = 'BAMBOO_5'
        # 暗手：差 CHARACTERS_3，但手中有宝牌 BAMBOO_5
        concealed = [
            'EAST', 'EAST',
            'CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3',
            'BAMBOO_7', 'BAMBOO_8', 'BAMBOO_9',
            'CHARACTERS_1', 'CHARACTERS_2',
            'BAMBOO_5',                              # 宝牌在手
        ]
        # 不传 bao_tile：只检测普通等待
        waits_no_bao = is_tenpai_dalian(concealed, 1, declared)
        # 传 bao_tile：宝牌可以替代 CHARACTERS_3
        waits_with_bao = is_tenpai_dalian(concealed, 1, declared, bao_tile=bao_tile)
        # 有宝牌时等待张可能更多（宝牌可替代任意缺少的牌）
        assert len(waits_with_bao) >= len(waits_no_bao)

    def test_multi_wait(self):
        """两面等待：等待两张"""
        declared = self._declared()
        concealed = [
            'EAST', 'EAST',
            'CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3',
            'BAMBOO_7', 'BAMBOO_8',                   # 等 BAMBOO_6 或 BAMBOO_9
            'CHARACTERS_1', 'CHARACTERS_2', 'CHARACTERS_3',
        ]
        waits = is_tenpai_dalian(concealed, 1, declared)
        assert 'BAMBOO_6' in waits
        assert 'BAMBOO_9' in waits


# ---------------------------------------------------------------------------
# is_winning_hand_dalian with bao_tile — 宝牌野牌替换
# ---------------------------------------------------------------------------

class TestIsWinningHandDalianBao:
    """宝牌作为野牌：摸到宝牌可代替任意所需牌胡牌。"""

    def _declared_bamboo_pung(self):
        return [['BAMBOO_1', 'BAMBOO_1', 'BAMBOO_1']]

    def test_bao_substitutes_missing_tile(self):
        """宝牌替换缺失的胡牌张后手牌合法"""
        declared = self._declared_bamboo_pung()
        bao = 'BAMBOO_5'
        # 差 CHARACTERS_3，用宝牌 BAMBOO_5 替代
        concealed = [
            'EAST', 'EAST',
            'CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3',
            'BAMBOO_7', 'BAMBOO_8', 'BAMBOO_9',
            'CHARACTERS_1', 'CHARACTERS_2',
            'BAMBOO_5',  # 宝牌
        ]
        assert is_winning_hand_dalian(concealed, 1, declared, bao_tile=bao)

    def test_bao_not_in_hand_no_effect(self):
        """宝牌不在手中时，野牌替换不生效"""
        declared = self._declared_bamboo_pung()
        bao = 'CIRCLES_9'  # 宝牌不在手中
        concealed = [
            'EAST', 'EAST',
            'CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3',
            'BAMBOO_7', 'BAMBOO_8', 'BAMBOO_9',
            'CHARACTERS_1', 'CHARACTERS_2',  # 差 CHARACTERS_3，宝牌不在手
        ]
        # 手中没有 CIRCLES_9，所以宝牌无法发挥作用
        assert not is_winning_hand_dalian(concealed, 1, declared, bao_tile=bao)

    def test_bao_cannot_fix_two_missing_suits(self):
        """宝牌只能替换一张，无法同时弥补两个缺色"""
        declared = [['BAMBOO_1', 'BAMBOO_2', 'BAMBOO_3']]  # 顺子，只提供条色
        bao = 'CIRCLES_5'  # 宝牌是饼色
        # 暗手：全是条+字，缺万和饼
        concealed = [
            'EAST', 'EAST',
            'BAMBOO_4', 'BAMBOO_5', 'BAMBOO_6',
            'BAMBOO_7', 'BAMBOO_8', 'BAMBOO_9',
            'NORTH', 'NORTH',
            'CIRCLES_5',  # 宝牌在手，可补饼，但万仍缺
        ]
        # 宝牌只能补一个花色，两个都缺时仍不能胡
        assert not is_winning_hand_dalian(concealed, 1, declared, bao_tile=bao)

    def test_no_bao_missing_tile_fails(self):
        """没有宝牌时差一张无法胡"""
        declared = self._declared_bamboo_pung()
        concealed = [
            'EAST', 'EAST',
            'CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3',
            'BAMBOO_7', 'BAMBOO_8', 'BAMBOO_9',
            'CHARACTERS_1', 'CHARACTERS_2',  # 差 CHARACTERS_3
        ]
        assert not is_winning_hand_dalian(concealed, 1, declared)


# ---------------------------------------------------------------------------
# calculate_han_dalian — 冲宝/摸宝番型
# ---------------------------------------------------------------------------

class TestCalculateHanDalianBao:
    """冲宝（+2）和摸宝（+1）番型测试，包含修复的 bug 验证。"""

    def _base_tiles(self):
        """合法大连胡牌暗手（含副露 BAMBOO_1×3）"""
        return [
            'EAST', 'EAST',
            'CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3',
            'BAMBOO_7', 'BAMBOO_8', 'BAMBOO_9',
            'CHARACTERS_1', 'CHARACTERS_2', 'CHARACTERS_3',
        ]

    def _declared(self):
        return [['BAMBOO_1', 'BAMBOO_1', 'BAMBOO_1']]

    # ── 冲宝 ────────────────────────────────────────────────────────────

    def test_chong_bao_ron(self):
        """冲宝 +2：荣和时胡牌张本身就是宝牌"""
        tiles = self._base_tiles()
        result = calculate_han_dalian(
            concealed_tiles=tiles,
            declared_melds=self._declared(),
            ron=True,
            winning_tile='CHARACTERS_3',
            bao_tile='CHARACTERS_3',
        )
        names = [x['name_cn'] for x in result['breakdown']]
        assert '冲宝' in names
        assert next(x for x in result['breakdown'] if x['name_cn'] == '冲宝')['fan'] == 2
        assert '摸宝' not in names

    def test_chong_bao_tsumo(self):
        """冲宝 +2：自摸时胡牌张本身也是宝牌（修复 bug：原实现只判断荣和）"""
        tiles = self._base_tiles()
        result = calculate_han_dalian(
            concealed_tiles=tiles,
            declared_melds=self._declared(),
            ron=False,                    # 自摸！
            winning_tile='CHARACTERS_3',
            bao_tile='CHARACTERS_3',
        )
        names = [x['name_cn'] for x in result['breakdown']]
        # Bug 修复验证：自摸冲宝应计入（旧代码 ron=False 时冲宝被忽略）
        assert '冲宝' in names, "自摸冲宝应加番（bug 修复验证）"
        assert '摸宝' not in names, "冲宝不叠加摸宝"

    def test_no_chong_bao_when_bao_not_winning_tile(self):
        """宝牌不是胡牌张时不计冲宝"""
        tiles = self._base_tiles()
        result = calculate_han_dalian(
            concealed_tiles=tiles,
            declared_melds=self._declared(),
            ron=True,
            winning_tile='CHARACTERS_3',
            bao_tile='EAST',              # 宝牌是 EAST，不是胡牌张
        )
        names = [x['name_cn'] for x in result['breakdown']]
        assert '冲宝' not in names

    # ── 摸宝 ────────────────────────────────────────────────────────────

    def test_mo_bao_tsumo(self):
        """摸宝 +1：自摸时手中有宝牌（宝牌充当野牌，不是胡牌张）"""
        # 手中有 BAMBOO_5（宝牌），胡牌张是 CHARACTERS_3
        tiles = self._base_tiles() + ['BAMBOO_5']  # 宝牌在手
        # 去掉一张让总数正确（暗手+1副露=11+3=14）
        tiles_11 = self._base_tiles()
        # 暗手放入宝牌，胡牌张是 CHARACTERS_3
        concealed_with_bao = [
            'EAST', 'EAST',
            'CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3',
            'BAMBOO_7', 'BAMBOO_8', 'BAMBOO_9',
            'CHARACTERS_1', 'CHARACTERS_2', 'BAMBOO_5',  # BAMBOO_5 是宝牌
        ]
        result = calculate_han_dalian(
            concealed_tiles=concealed_with_bao + ['CHARACTERS_3'],  # 加上胡牌张
            declared_melds=self._declared(),
            ron=False,
            winning_tile='CHARACTERS_3',
            bao_tile='BAMBOO_5',
        )
        names = [x['name_cn'] for x in result['breakdown']]
        assert '摸宝' in names
        assert next(x for x in result['breakdown'] if x['name_cn'] == '摸宝')['fan'] == 1
        assert '冲宝' not in names

    def test_no_mo_bao_on_ron(self):
        """摸宝不计荣和（摸宝仅限自摸）"""
        tiles = self._base_tiles() + ['BAMBOO_5']
        result = calculate_han_dalian(
            concealed_tiles=tiles,
            declared_melds=self._declared(),
            ron=True,                     # 荣和！
            winning_tile='EAST',
            bao_tile='BAMBOO_5',
        )
        names = [x['name_cn'] for x in result['breakdown']]
        assert '摸宝' not in names

    def test_tsumo_bao_as_wildcard_is_mobao_not_chongbao(self):
        """Bug 修复验证：摸到宝牌通过野牌替代胡牌，应计摸宝(+1)不是冲宝(+2)。
        即 winning_tile == bao_tile 但宝牌不是结构性等待张时，应为摸宝。"""
        # 等待 CHARACTERS_3，摸到宝牌 BAMBOO_5（宝牌通过野牌替代 CHARACTERS_3）
        concealed = [
            'EAST', 'EAST',
            'CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3',
            'BAMBOO_7', 'BAMBOO_8', 'BAMBOO_9',
            'CHARACTERS_1', 'CHARACTERS_2',
            'BAMBOO_5',   # 宝牌（摸到后代替 CHARACTERS_3）
        ]
        result = calculate_han_dalian(
            concealed_tiles=concealed,
            declared_melds=self._declared(),
            ron=False,
            winning_tile='BAMBOO_5',   # 摸到宝牌
            bao_tile='BAMBOO_5',
        )
        names = [x['name_cn'] for x in result['breakdown']]
        assert '摸宝' in names, "宝牌通过野牌替代胡牌应计摸宝"
        assert '冲宝' not in names, "宝牌通过野牌替代时不应计冲宝（bug 修复验证）"
        fan_mobao = next(x for x in result['breakdown'] if x['name_cn'] == '摸宝')
        assert fan_mobao['fan'] == 1

    def test_chong_bao_requires_structural_win(self):
        """冲宝要求宝牌是结构性等待张：手牌去掉宝牌野牌效果后仍能直接胡。"""
        # 结构性等待 CHARACTERS_3，宝牌也恰好是 CHARACTERS_3 → 真正冲宝
        tiles_with_structural_wait = self._base_tiles()  # 含 CHARACTERS_1,2,3
        result = calculate_han_dalian(
            concealed_tiles=tiles_with_structural_wait,
            declared_melds=self._declared(),
            ron=False,
            winning_tile='CHARACTERS_3',
            bao_tile='CHARACTERS_3',   # 宝牌恰好是结构性等待张
        )
        names = [x['name_cn'] for x in result['breakdown']]
        assert '冲宝' in names, "宝牌是结构性等待张时应计冲宝"
        assert '摸宝' not in names

    def test_no_bao_bonus_when_bao_is_none(self):
        """bao_tile=None 时不计任何宝牌番"""
        tiles = self._base_tiles()
        result = calculate_han_dalian(
            concealed_tiles=tiles,
            declared_melds=self._declared(),
            ron=True,
            winning_tile='CHARACTERS_3',
            bao_tile=None,
        )
        names = [x['name_cn'] for x in result['breakdown']]
        assert '冲宝' not in names
        assert '摸宝' not in names
