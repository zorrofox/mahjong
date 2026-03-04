"""港式麻将完整游戏流程 E2E 测试。

策略：全 AI 局（run_all_ai_game）+ 重连观察结果
  1. API 创建房间，不加入人类玩家
  2. AI 自动打完（轮询等待 ended）
  3. 以 ai_player_1 身份连接游戏页（触发 is_reconnect=True game_over 事件）
  4. 结算弹窗出现，验证各项指标
"""
import pytest

from helpers import run_all_ai_game, wait_for_game_over, chips_are_zero_sum, api_get
from page_objects import GamePage


async def _run_and_observe_hk(page, base_url, max_wait: float = 90.0) -> tuple:
    """全 AI 港式局完成后，导航到游戏页观察结果，返回 (room_id, result_dict)。"""
    info = await run_all_ai_game(base_url, ruleset="hk", max_wait=max_wait)
    room_id = info["room_id"]
    observer = info["observer_player_id"]

    # 重连游戏页 → 服务端发送 game_over(is_reconnect=True)
    await page.goto(f"{base_url}/game.html?room={room_id}&player={observer}")
    result = await wait_for_game_over(page, timeout=15_000)
    return room_id, result


@pytest.mark.asyncio
class TestHKGameFlow:

    async def test_game_page_loads_with_hk_badge(self, page, base_url):
        """游戏页面（重连已结束的 HK 局）顶栏显示港式规则标签。"""
        info = await run_all_ai_game(base_url, ruleset="hk", max_wait=90.0)
        await page.goto(
            f"{base_url}/game.html?room={info['room_id']}&player={info['observer_player_id']}"
        )
        await page.wait_for_selector("#game-over-modal:not(.hidden)", timeout=15_000)

        gp = GamePage(page)
        badge_text = await gp.ruleset_text()
        assert "港式" in badge_text, f"期望「港式」标签，实际：'{badge_text}'"

    async def test_hk_game_completes(self, page, base_url):
        """全 AI 港式游戏能在 60s 内完成（有赢家或流局）。"""
        _, result = await _run_and_observe_hk(page, base_url)
        assert result["winner"] or result["is_draw"], \
            f"游戏未正常结束: {result}"

    async def test_hk_settlement_zero_sum(self, page, base_url):
        """结算后所有玩家筹码总和 = 4000（4人×1000初始）。"""
        _, result = await _run_and_observe_hk(page, base_url)
        scores = result["scores"]
        assert len(scores) == 4, f"期望4名玩家，得到 {len(scores)}"
        assert chips_are_zero_sum(scores, initial=1000), \
            f"筹码不零和: {[s['chips'] for s in scores]}"

    async def test_hk_win_shows_fan_breakdown(self, page, base_url):
        """有赢家时结算弹窗显示番型明细，且含「基本分」。"""
        _, result = await _run_and_observe_hk(page, base_url)
        if result["is_draw"]:
            pytest.skip("本局流局，无番型明细")
        assert len(result["han_breakdown"]) > 0, "胡牌无番型明细"
        names = [x["name"] for x in result["han_breakdown"]]
        assert any(n.startswith("基本分") for n in names), f"缺少「基本分」: {names}"

    async def test_hk_settlement_modal_shows_winner(self, page, base_url):
        """结算弹窗显示赢家名字或「流局 Draw」。"""
        _, result = await _run_and_observe_hk(page, base_url)
        gp = GamePage(page)
        assert await gp.game_over_modal.is_visible()
        if result["is_draw"]:
            assert "流局" in result["win_type"] or "Draw" in result["win_type"]
        else:
            assert result["winner"] and result["winner"] != "–"

    async def test_hk_play_again_button_visible(self, page, base_url):
        """结算弹窗中「再来一局」按钮可见。"""
        _, result = await _run_and_observe_hk(page, base_url)
        gp = GamePage(page)
        assert await gp.play_again_btn.is_visible()

    async def test_hk_winner_chips_increased(self, page, base_url):
        """有赢家时赢家筹码 > 1000。"""
        _, result = await _run_and_observe_hk(page, base_url)
        if result["is_draw"]:
            pytest.skip("本局流局，跳过赢家验证")
        chips = [s["chips"] for s in result["scores"]]
        assert max(chips) > 1000, "赢家筹码未增加"

    async def test_api_room_status_after_game(self, page, base_url):
        """游戏结束后 API 返回 status=ended。"""
        room_id, _ = await _run_and_observe_hk(page, base_url)
        rooms = await api_get(base_url, "/api/rooms")
        room = next((r for r in rooms if r["id"] == room_id), None)
        assert room is not None
        assert room["status"] in ("ended", "finished")

    async def test_hk_tiles_visible_after_game_ends(self, page, base_url):
        """游戏结束重连后对手手牌翻开（end-game reveal）。"""
        await _run_and_observe_hk(page, base_url)
        tiles_count = await page.locator(".tile-img").count()
        assert tiles_count > 0, "游戏结束后未看到翻开的牌"

    async def test_hk_no_bao_badge_visible(self, page, base_url):
        """港式游戏不显示宝牌 badge（大连专属）。"""
        info = await run_all_ai_game(base_url, ruleset="hk", max_wait=90.0)
        await page.goto(
            f"{base_url}/game.html?room={info['room_id']}&player={info['observer_player_id']}"
        )
        await page.wait_for_selector("#game-over-modal:not(.hidden)", timeout=15_000)
        gp = GamePage(page)
        assert not await gp.bao_badge.is_visible(), "港式游戏不应显示宝牌 badge"
