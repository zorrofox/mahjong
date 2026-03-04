"""港式麻将完整游戏流程 E2E 测试。"""
import pytest
import httpx

from helpers import (
    wait_for_game_over,
    chips_are_zero_sum,
    api_get,
    discard_first_tile,
    wait_for_my_turn_or_game_over,
)
from page_objects import GamePage


async def _create_and_start_hk_game(page, base_url) -> tuple:
    """
    辅助：通过 API 创建港式房间，加入一名人类玩家，开始游戏（AI 填满剩余座位），
    导航到游戏页面，返回 (room_id, player_id)。
    """
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{base_url}/api/rooms",
            json={"name": "E2E-HK", "ruleset": "hk"},
        )
        assert r.status_code == 201, f"创建房间失败: {r.text}"
        room = r.json()
        room_id = room["id"]

        # 加入房间（人类玩家）
        player_id = "e2e_player_hk"
        jr = await client.post(
            f"{base_url}/api/rooms/{room_id}/join",
            json={"player_id": player_id},
        )
        assert jr.status_code == 200, f"加入房间失败: {jr.text}"

        # 开始游戏（AI 填满剩余座位）
        sr = await client.post(f"{base_url}/api/rooms/{room_id}/start")
        assert sr.status_code == 200, f"开始游戏失败: {sr.text}"

    # 导航到游戏页面（作为该玩家观察/操作）
    await page.goto(f"{base_url}/game.html?room={room_id}&player={player_id}")
    await page.wait_for_selector(".tile[data-tile]", timeout=15_000)

    return room_id, player_id


@pytest.mark.asyncio
class TestHKGameFlow:

    async def test_game_page_loads_with_hk_badge(self, page, base_url):
        """游戏页面加载后顶栏显示港式规则标签。"""
        await _create_and_start_hk_game(page, base_url)
        gp = GamePage(page)

        badge_text = await gp.ruleset_text()
        assert "港式" in badge_text, \
            f"期望顶栏显示「港式」，实际内容: '{badge_text}'"

    async def test_hk_game_completes(self, page, base_url):
        """港式游戏能自动完成（AI 自动出牌，有赢家或流局）。"""
        await _create_and_start_hk_game(page, base_url)

        result = await wait_for_game_over(page, timeout=120_000)

        assert result["winner"] or result["is_draw"], \
            f"游戏未正常结束: {result}"

    async def test_hk_settlement_zero_sum(self, page, base_url):
        """结算后所有玩家筹码总和等于 4000（4 人 × 1000 初始筹码）。"""
        await _create_and_start_hk_game(page, base_url)
        result = await wait_for_game_over(page, timeout=120_000)

        scores = result["scores"]
        assert len(scores) == 4, f"期望 4 名玩家，得到 {len(scores)}"
        assert chips_are_zero_sum(scores, initial=1000), \
            f"筹码不零和: {[s['chips'] for s in scores]}"

    async def test_hk_win_shows_fan_breakdown(self, page, base_url):
        """有赢家时结算弹窗显示番型明细，且至少包含「基本分」。"""
        await _create_and_start_hk_game(page, base_url)
        result = await wait_for_game_over(page, timeout=120_000)

        if not result["is_draw"]:
            assert len(result["han_breakdown"]) > 0, \
                "有赢家但番型明细列表为空"
            names = [x["name"] for x in result["han_breakdown"]]
            assert "基本分" in names, \
                f"番型明细缺少「基本分」，实际: {names}"

    async def test_hk_settlement_modal_shows_winner(self, page, base_url):
        """结算弹窗显示赢家名字或流局文字，弹窗本身可见。"""
        await _create_and_start_hk_game(page, base_url)
        result = await wait_for_game_over(page, timeout=120_000)

        gp = GamePage(page)
        assert await gp.game_over_modal.is_visible(), \
            "结算弹窗未显示"

        if result["is_draw"]:
            win_type = result["win_type"]
            assert "流局" in win_type or "Draw" in win_type, \
                f"流局时 win_type 文字不符: '{win_type}'"
        else:
            assert result["winner"] and result["winner"] != "–", \
                f"有赢家但 winner 字段为空或占位符: '{result['winner']}'"

    async def test_hk_play_again_button_visible(self, page, base_url):
        """结算弹窗中「再来一局」按钮可见。"""
        await _create_and_start_hk_game(page, base_url)
        await wait_for_game_over(page, timeout=120_000)

        gp = GamePage(page)
        assert await gp.play_again_btn.is_visible(), \
            "结算弹窗中未找到「再来一局」按钮"

    async def test_hk_winner_chips_increased(self, page, base_url):
        """有赢家时赢家筹码 > 1000，且至少有人筹码减少。"""
        await _create_and_start_hk_game(page, base_url)
        result = await wait_for_game_over(page, timeout=120_000)

        if result["is_draw"]:
            pytest.skip("本局流局，跳过赢家筹码验证")

        chips = [s["chips"] for s in result["scores"]]
        assert max(chips) > 1000, \
            f"赢家筹码未增加，所有筹码: {chips}"
        assert min(chips) < 1000, \
            f"无人筹码减少，所有筹码: {chips}"

    async def test_api_room_status_after_game(self, page, base_url):
        """游戏结束后通过 API 查询房间状态为 ended 或 finished。"""
        room_id, _ = await _create_and_start_hk_game(page, base_url)
        await wait_for_game_over(page, timeout=120_000)

        rooms = await api_get(base_url, "/api/rooms")
        room = next((r for r in rooms if r["id"] == room_id), None)
        assert room is not None, f"API 返回房间列表中找不到 room_id={room_id}"
        assert room["status"] in ("ended", "finished"), \
            f"期望 status 为 ended/finished，实际: '{room['status']}'"

    async def test_hk_tiles_visible_after_game_ends(self, page, base_url):
        """游戏结束后对手手牌被翻开（end-game reveal），可见 tile-img 元素。"""
        await _create_and_start_hk_game(page, base_url)
        await wait_for_game_over(page, timeout=120_000)

        tiles_count = await page.locator(".tile-img").count()
        assert tiles_count > 0, \
            "游戏结束后未看到任何翻开的牌（tile-img 为 0）"

    async def test_hk_no_bao_badge_visible(self, page, base_url):
        """港式游戏中不显示宝牌 badge（大连穷胡专属功能）。"""
        await _create_and_start_hk_game(page, base_url)

        # 等待游戏页面完全就绪
        await page.wait_for_selector(".tile[data-tile]")

        gp = GamePage(page)
        is_visible = await gp.bao_badge.is_visible()
        assert not is_visible, \
            "港式游戏中不应显示宝牌 badge，但检测到它是可见的"
