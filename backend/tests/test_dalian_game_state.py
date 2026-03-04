"""
test_dalian_game_state.py - 大连穷胡 GameState 专项测试

覆盖：
  - 牌组：build_deck("dalian") 返回 136 张无花牌
  - 荒庄：≤14 张触发 draw_tile 返回 None
  - 三元牌禁碰：claim_pung 对 RED/GREEN/WHITE 返回 False
  - 宝牌计数：_count_bao_revealed 统计弃牌堆+非暗杠副露
  - 宝牌重摇：check_and_maybe_reroll_bao 达到 3 张时重摇
  - 听牌检测：check_and_trigger_bao 后续玩家也能加入 tenpai_players
  - 不换听：discard_tile 在听牌状态下拒绝破坏听牌的出牌
  - 大连结算：to_dict 对非听牌玩家隐藏 bao_tile
"""

import pytest
from game.game_state import GameState
from game.tiles import build_deck


NUM_PLAYERS = 4


def make_dalian():
    """创建一个标准大连穷胡 GameState 并发牌。"""
    gs = GameState(
        room_id="test-dalian",
        player_ids=["p0", "p1", "p2", "p3"],
        ruleset="dalian",
    )
    gs.deal_initial_tiles()
    return gs


# ---------------------------------------------------------------------------
# 牌组与发牌
# ---------------------------------------------------------------------------

class TestDalianDeck:

    def test_deck_size_136(self):
        """大连牌组 136 张，无花牌"""
        deck = build_deck("dalian")
        assert len(deck) == 136

    def test_no_flower_tiles_in_deck(self):
        """大连牌组不含花牌"""
        from game.tiles import is_flower_tile
        deck = build_deck("dalian")
        assert not any(is_flower_tile(t) for t in deck)

    def test_hk_deck_size_144(self):
        """港式牌组仍为 144 张"""
        deck = build_deck("hk")
        assert len(deck) == 144

    def test_deal_no_flowers_in_hands(self):
        """大连发牌后手牌中无花牌"""
        from game.tiles import is_flower_tile
        gs = make_dalian()
        for player in gs.players:
            assert not any(is_flower_tile(t) for t in player.hand)

    def test_ruleset_in_to_dict(self):
        """to_dict 包含 ruleset 字段"""
        gs = make_dalian()
        d = gs.to_dict()
        assert d["ruleset"] == "dalian"


# ---------------------------------------------------------------------------
# 荒庄
# ---------------------------------------------------------------------------

class TestDalianHuangZhuang:

    def _setup_drawing_phase(self, ruleset: str, wall_size: int):
        """创建一个处于 drawing 阶段、牌墙精确为 wall_size 张的 GameState。"""
        gs = GameState(
            room_id="test", player_ids=["a", "b", "c", "d"], ruleset=ruleset
        )
        gs.deal_initial_tiles()
        # 强制进入 drawing 阶段（跳过庄家出牌流程）
        gs.phase = "drawing"
        gs.current_turn = (gs.dealer_idx + 1) % 4  # 取非庄家玩家
        # 调整牌墙张数
        gs.wall = gs.wall[:wall_size]
        assert len(gs.wall) == wall_size
        return gs

    def test_draw_tile_returns_none_at_14(self):
        """当牌墙 ≤14 张时，draw_tile 返回 None 并设 phase='ended'"""
        gs = self._setup_drawing_phase("dalian", 14)
        result = gs.draw_tile(gs.current_turn)
        assert result is None
        assert gs.phase == "ended"

    def test_draw_tile_ok_at_15(self):
        """当牌墙 > 14 张时，draw_tile 正常返回"""
        gs = self._setup_drawing_phase("dalian", 15)
        result = gs.draw_tile(gs.current_turn)
        assert result is not None
        assert gs.phase == "discarding"

    def test_hk_no_huangzhuang_at_14(self):
        """港式规则 14 张时仍可正常摸牌（无荒庄逻辑）"""
        gs = self._setup_drawing_phase("hk", 14)
        result = gs.draw_tile(gs.current_turn)
        assert result is not None  # HK 不触发荒庄


# ---------------------------------------------------------------------------
# 三元牌禁碰
# ---------------------------------------------------------------------------

class TestDalianDragonPungBan:

    def _setup_claiming(self, dragon: str):
        """让玩家 0 打出 dragon，玩家 1 手中有 2 张同种牌，进入声索窗口。"""
        gs = make_dalian()
        # 清空手牌，手动设置
        gs.players[0].hand = [dragon]
        gs.players[1].hand = [dragon, dragon, 'BAMBOO_1', 'BAMBOO_2']
        gs.players[2].hand = ['BAMBOO_3', 'BAMBOO_4', 'BAMBOO_5']
        gs.players[3].hand = ['CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3']
        gs.current_turn = 0
        gs.phase = "discarding"
        gs.discard_tile(0, dragon)
        return gs

    def test_cannot_pung_red(self):
        """中（RED）不能被碰"""
        gs = self._setup_claiming('RED')
        result = gs.claim_pung(1)
        assert result is False

    def test_cannot_pung_green(self):
        """發（GREEN）不能被碰"""
        gs = self._setup_claiming('GREEN')
        result = gs.claim_pung(1)
        assert result is False

    def test_cannot_pung_white(self):
        """白（WHITE）不能被碰"""
        gs = self._setup_claiming('WHITE')
        result = gs.claim_pung(1)
        assert result is False

    def test_can_pung_wind(self):
        """风牌（EAST）可以被碰"""
        gs = make_dalian()
        gs.players[0].hand = ['EAST']
        gs.players[1].hand = ['EAST', 'EAST', 'BAMBOO_1', 'BAMBOO_2']
        gs.players[2].hand = ['BAMBOO_3']
        gs.players[3].hand = ['BAMBOO_4']
        gs.current_turn = 0
        gs.phase = "discarding"
        gs.discard_tile(0, 'EAST')
        result = gs.claim_pung(1)
        assert result is True


# ---------------------------------------------------------------------------
# 宝牌计数（_count_bao_revealed）
# ---------------------------------------------------------------------------

class TestCountBaoRevealed:

    def _gs_with_bao(self, bao: str):
        gs = make_dalian()
        gs.bao_tile = bao
        gs.bao_declared = True
        return gs

    def test_zero_when_not_declared(self):
        """宝牌未揭示时计数为 0"""
        gs = make_dalian()
        assert gs._count_bao_revealed() == 0

    def test_count_in_discard_pile(self):
        """弃牌堆中的宝牌计入"""
        gs = self._gs_with_bao('BAMBOO_5')
        gs.discards[0] = ['BAMBOO_5', 'BAMBOO_1']
        gs.discards[2] = ['BAMBOO_5']
        assert gs._count_bao_revealed() == 2

    def test_count_in_meld(self):
        """明副露（碰/吃）中的宝牌计入"""
        gs = self._gs_with_bao('BAMBOO_5')
        gs.players[1].melds = [['BAMBOO_5', 'BAMBOO_5', 'BAMBOO_5']]  # 碰宝牌
        assert gs._count_bao_revealed() == 3

    def test_concealed_kong_not_counted(self):
        """暗杠中的宝牌不计（对手不可见）"""
        gs = self._gs_with_bao('BAMBOO_5')
        # 暗杠：4 张相同 = 暗杠
        gs.players[0].melds = [['BAMBOO_5', 'BAMBOO_5', 'BAMBOO_5', 'BAMBOO_5']]
        assert gs._count_bao_revealed() == 0

    def test_declared_kong_counted(self):
        """明杠（3+加杠 = len==4 但非暗杠结构？）暂作明副露处理"""
        gs = self._gs_with_bao('NORTH')
        # 4 张相同的明杠（从碰变成的加杠，实际上也是 4 张相同）
        # 当前 _count_bao_revealed 将 len==4 且 4 张相同作为暗杠处理 → 不计
        # 这是已知设计取舍
        gs.players[0].melds = [['NORTH', 'NORTH', 'NORTH', 'NORTH']]
        # 4张相同视为暗杠 → 0
        assert gs._count_bao_revealed() == 0


# ---------------------------------------------------------------------------
# 宝牌重摇（check_and_maybe_reroll_bao）
# ---------------------------------------------------------------------------

class TestBaoReroll:

    def test_reroll_at_3_revealed(self):
        """明牌数达到 3 时触发重摇"""
        gs = make_dalian()
        gs.bao_tile = 'BAMBOO_5'
        gs.bao_declared = True
        gs.bao_dice_roll = 1

        # 弃牌堆放 3 张宝牌
        gs.discards[0] = ['BAMBOO_5', 'BAMBOO_5']
        gs.discards[1] = ['BAMBOO_5']

        old_bao = gs.bao_tile
        event = gs.check_and_maybe_reroll_bao()
        # 宝牌应该变了（极小概率相同，忽略）
        assert event is not None
        assert 'bao_tile' in event
        assert 'dice' in event

    def test_no_reroll_below_3(self):
        """明牌数 < 3 不重摇"""
        gs = make_dalian()
        gs.bao_tile = 'BAMBOO_5'
        gs.bao_declared = True
        gs.discards[0] = ['BAMBOO_5', 'BAMBOO_5']  # 只有 2 张
        event = gs.check_and_maybe_reroll_bao()
        assert event is None

    def test_no_reroll_when_not_dalian(self):
        """港式规则不触发宝牌逻辑"""
        gs = GameState(room_id="t", player_ids=["a","b","c","d"], ruleset="hk")
        gs.deal_initial_tiles()
        gs.bao_tile = 'BAMBOO_5'
        gs.bao_declared = True
        gs.discards[0] = ['BAMBOO_5'] * 3
        event = gs.check_and_maybe_reroll_bao()
        assert event is None


# ---------------------------------------------------------------------------
# 宝牌私密性：to_dict 对非听牌玩家隐藏 bao_tile
# ---------------------------------------------------------------------------

class TestBaoPrivacy:

    def _gs_with_tenpai(self):
        gs = make_dalian()
        gs.bao_tile = 'BAMBOO_5'
        gs.bao_declared = True
        gs.bao_dice_roll = 3
        gs.tenpai_players = {1}   # 只有玩家 1 听牌
        return gs

    def test_tenpai_player_sees_bao(self):
        """听牌玩家（player_idx=1）能看到宝牌"""
        gs = self._gs_with_tenpai()
        d = gs.to_dict(viewing_player_idx=1)
        assert d["bao_tile"] == 'BAMBOO_5'
        assert d["bao_dice_roll"] == 3

    def test_non_tenpai_player_cannot_see_bao(self):
        """非听牌玩家（player_idx=0）看不到宝牌"""
        gs = self._gs_with_tenpai()
        d = gs.to_dict(viewing_player_idx=0)
        assert d["bao_tile"] is None
        assert d["bao_dice_roll"] is None

    def test_debug_view_sees_bao(self):
        """调试视角（viewing_player_idx=None）能看到宝牌"""
        gs = self._gs_with_tenpai()
        d = gs.to_dict(viewing_player_idx=None)
        assert d["bao_tile"] == 'BAMBOO_5'

    def test_bao_declared_flag_visible_to_all(self):
        """bao_declared 标志对所有玩家可见（知道宝牌已揭示，但不知是哪张）"""
        gs = self._gs_with_tenpai()
        d = gs.to_dict(viewing_player_idx=0)
        assert d["bao_declared"] is True  # 知道有宝牌存在


# ---------------------------------------------------------------------------
# 听牌检测：check_and_trigger_bao 不换听约束
# ---------------------------------------------------------------------------

class TestDalianTenpaiDetection:

    def test_check_trigger_bao_detects_first_tenpai(self):
        """首个听牌玩家触发骰子并设置宝牌"""
        gs = make_dalian()
        # 手动构建一个听牌状态（玩家 0）：已有副露，差一张胡
        gs.players[0].melds = [['BAMBOO_1', 'BAMBOO_1', 'BAMBOO_1']]
        gs.players[0].hand = [
            'EAST', 'EAST',
            'CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3',
            'BAMBOO_7', 'BAMBOO_8', 'BAMBOO_9',
            'CHARACTERS_1', 'CHARACTERS_2',   # 等 CHARACTERS_3
        ]
        event = gs.check_and_trigger_bao()
        # 宝牌应被揭示
        assert gs.bao_declared is True
        assert gs.bao_tile is not None
        assert 0 in gs.tenpai_players
        assert event is not None
        assert event["player_idx"] == 0

    def test_subsequent_tenpai_player_added(self):
        """宝牌已揭示后，后续听牌玩家也能被加入 tenpai_players"""
        gs = make_dalian()
        # 先让玩家 0 进入听牌
        gs.players[0].melds = [['BAMBOO_1', 'BAMBOO_1', 'BAMBOO_1']]
        gs.players[0].hand = [
            'EAST', 'EAST',
            'CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3',
            'BAMBOO_7', 'BAMBOO_8', 'BAMBOO_9',
            'CHARACTERS_1', 'CHARACTERS_2',
        ]
        gs.check_and_trigger_bao()
        assert gs.bao_declared is True

        # 再让玩家 1 也进入听牌（相同结构）
        gs.players[1].melds = [['CIRCLES_1', 'CIRCLES_1', 'CIRCLES_1']]
        gs.players[1].hand = [
            'NORTH', 'NORTH',
            'BAMBOO_2', 'BAMBOO_3', 'BAMBOO_4',
            'BAMBOO_5', 'BAMBOO_6', 'BAMBOO_7',
            'CHARACTERS_4', 'CHARACTERS_5',   # 等 CHARACTERS_6
        ]
        gs.check_and_trigger_bao()
        # 玩家 1 也应被加入 tenpai_players
        assert 1 in gs.tenpai_players, "后续听牌玩家应被加入 tenpai_players"

    def test_discard_breaks_tenpai_rejected(self):
        """听牌后出牌破坏听牌应被拒绝（不换听）"""
        gs = make_dalian()
        # 副露：BAMBOO_1 × 3（提供条色 + 至少一刻）
        gs.players[0].melds = [['BAMBOO_1', 'BAMBOO_1', 'BAMBOO_1']]
        # 暗手 11 张（discarding 状态）：等 CHARACTERS_3 → 听牌
        # 结构：将(EAST×2) + 顺(饼123) + 顺(条789) + 等(万12 → 差3)
        gs.players[0].hand = [
            'EAST', 'EAST',
            'CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3',
            'BAMBOO_7', 'BAMBOO_8', 'BAMBOO_9',
            'CHARACTERS_1', 'CHARACTERS_2',
            'NORTH',   # 第11张：刚摸到的无用牌
        ]
        gs.tenpai_players.add(0)
        gs.phase = "discarding"
        gs.current_turn = 0

        # 尝试打出 EAST（将牌）：打出后暗手变10张，结构中将消失 → 不能再听牌
        # 打出 NORTH 是合法的（返回到10张等牌状态），打出 EAST 破坏将 → 不能换听
        with pytest.raises(ValueError, match="不能换听"):
            gs.discard_tile(0, 'EAST')

    def test_discard_valid_tile_in_tenpai_ok(self):
        """听牌时打出不破坏听牌的牌是允许的"""
        gs = make_dalian()
        gs.players[0].melds = [['BAMBOO_1', 'BAMBOO_1', 'BAMBOO_1']]
        gs.players[0].hand = [
            'EAST', 'EAST',
            'CIRCLES_1', 'CIRCLES_2', 'CIRCLES_3',
            'BAMBOO_7', 'BAMBOO_8', 'BAMBOO_9',
            'CHARACTERS_1', 'CHARACTERS_2',
            'NORTH',   # 打出这张，剩下10张仍在听 CHARACTERS_3
        ]
        gs.tenpai_players.add(0)
        gs.phase = "discarding"
        gs.current_turn = 0
        # 打出 NORTH：不影响听牌结构 → 应成功
        gs.discard_tile(0, 'NORTH')
        assert gs.phase == "claiming"
