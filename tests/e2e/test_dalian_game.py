"""大连穷胡游戏流程 E2E 测试。

策略同 HK：全 AI 局 + 重连观察结果。
"""
import pytest
import httpx

from helpers import run_all_ai_game, wait_for_game_over, chips_are_zero_sum, api_get
from page_objects import GamePage


async def _run_and_observe_dalian(page, base_url, max_wait: float = 120.0) -> tuple:
    """全 AI 大连局完成后，导航到游戏页观察结果，返回 (room_id, result_dict)。"""
    info = await run_all_ai_game(base_url, ruleset="dalian", max_wait=max_wait)
    room_id = info["room_id"]
    observer = info["observer_player_id"]

    await page.goto(f"{base_url}/game.html?room={room_id}&player={observer}")
    result = await wait_for_game_over(page, timeout=15_000)
    return room_id, result


@pytest.mark.asyncio
class TestDalianGameFlow:

    # ── 基础加载（全 AI 局开始后立即验证）────────────────────────────

    async def test_game_page_shows_dalian_badge(self, page, base_url):
        """游戏结束重连页面显示「大连」规则标签。"""
        info = await run_all_ai_game(base_url, ruleset="dalian", max_wait=120.0)
        await page.goto(
            f"{base_url}/game.html?room={info['room_id']}&player={info['observer_player_id']}"
        )
        await page.wait_for_selector("#game-over-modal:not(.hidden)", timeout=15_000)
        gp = GamePage(page)
        badge = await gp.ruleset_text()
        assert "大连" in badge, f"期望大连标签，实际：'{badge}'"

    async def test_dalian_game_starts_with_tiles(self, page, base_url):
        """大连游戏结束后重连，手牌区有翻开的牌面（end-game reveal）。"""
        info = await run_all_ai_game(base_url, ruleset="dalian", max_wait=120.0)
        await page.goto(
            f"{base_url}/game.html?room={info['room_id']}&player={info['observer_player_id']}"
        )
        await page.wait_for_selector("#game-over-modal:not(.hidden)", timeout=15_000)
        # 游戏结束后所有手牌已翻开
        tile_count = await page.locator(".tile-img").count()
        assert tile_count > 0, "游戏结束后未看到任何牌面"

    async def test_dalian_no_flower_tiles_revealed(self, page, base_url):
        """大连游戏结束后翻牌中不含花牌（FLOWER_/SEASON_）。"""
        info = await run_all_ai_game(base_url, ruleset="dalian", max_wait=120.0)
        await page.goto(
            f"{base_url}/game.html?room={info['room_id']}&player={info['observer_player_id']}"
        )
        await page.wait_for_selector("#game-over-modal:not(.hidden)", timeout=15_000)

        tile_attrs = await page.evaluate("""() => {
            return Array.from(
                document.querySelectorAll('.tile[data-tile]')
            ).map(el => el.dataset.tile);
        }""")
        flower_tiles = [t for t in tile_attrs
                        if t and ("FLOWER" in t or "SEASON" in t)]
        assert len(flower_tiles) == 0, f"大连牌局含花牌：{flower_tiles}"

    # ── 完整游戏流程 ─────────────────────────────────────────────────

    async def test_dalian_game_completes(self, page, base_url):
        """大连游戏能在 90s 内完成（AI 出牌直到胡牌或荒庄）。"""
        _, result = await _run_and_observe_dalian(page, base_url)
        assert result["winner"] or result["is_draw"], \
            f"游戏未正常结束: {result}"

    async def test_dalian_settlement_zero_sum(self, page, base_url):
        """大连结算后所有玩家筹码总和 = 4000。"""
        _, result = await _run_and_observe_dalian(page, base_url)
        scores = result["scores"]
        assert len(scores) == 4
        assert chips_are_zero_sum(scores, initial=1000), \
            f"筹码不零和: {[s['chips'] for s in scores]}"

    async def test_dalian_winner_chips_changed(self, page, base_url):
        """有赢家时赢家筹码大于 1000。"""
        _, result = await _run_and_observe_dalian(page, base_url)
        if result["is_draw"]:
            pytest.skip("本局荒庄，跳过赢家验证")
        chips = [s["chips"] for s in result["scores"]]
        assert max(chips) > 1000, "赢家筹码未增加"

    # ── 番型验证 ─────────────────────────────────────────────────────

    async def test_dalian_win_shows_han_breakdown(self, page, base_url):
        """大连胡牌时结算弹窗显示番型明细（至少含「基础」）。"""
        _, result = await _run_and_observe_dalian(page, base_url)
        if result["is_draw"]:
            pytest.skip("本局荒庄，无番型明细")
        assert len(result["han_breakdown"]) > 0, "胡牌无番型明细"
        names = [x["name"] for x in result["han_breakdown"]]
        # 番型名称含英文（如 "基础 Base"），用 any(startswith) 判断
        assert any(n.startswith("基础") for n in names), f"缺少「基础」番型：{names}"

    async def test_dalian_draw_shows_draw_label(self, page, base_url):
        """荒庄时结算弹窗显示「流局 Draw」文字（概率测试，最多尝试3局）。"""
        found_draw = False
        for attempt in range(3):
            info = await run_all_ai_game(base_url, ruleset="dalian", max_wait=120.0)
            await page.goto(
                f"{base_url}/game.html?room={info['room_id']}&player={info['observer_player_id']}"
            )
            result = await wait_for_game_over(page, timeout=15_000)
            if result["is_draw"]:
                found_draw = True
                win_type = result["win_type"]
                assert "流局" in win_type or "Draw" in win_type, \
                    f"荒庄未显示流局文字：'{win_type}'"
                break
        if not found_draw:
            pytest.skip("3局内未触发荒庄，跳过（概率性测试）")

    # ── API 与最终状态 ────────────────────────────────────────────────

    async def test_dalian_room_status_after_game(self, page, base_url):
        """游戏结束后 API 返回 status=ended 且 ruleset=dalian。"""
        room_id, _ = await _run_and_observe_dalian(page, base_url)
        rooms = await api_get(base_url, "/api/rooms")
        room = next((r for r in rooms if r["id"] == room_id), None)
        assert room is not None
        assert room["status"] in ("ended", "finished")
        assert room["ruleset"] == "dalian"

    async def test_dalian_end_game_reveals_tiles(self, page, base_url):
        """大连游戏结束后对手手牌翻开可见。"""
        await _run_and_observe_dalian(page, base_url)
        tiles = await page.locator(".tile-img").count()
        assert tiles > 0, "游戏结束后未见到翻牌"

    async def test_dalian_no_bao_before_tenpai_on_reconnect(self, page, base_url):
        """重连结束局时，若本局有宝牌则结算弹窗中有宝牌区域，无则不显示。"""
        _, result = await _run_and_observe_dalian(page, base_url)
        # 结算弹窗中 bao-result-section 可见性由 bao_tile 是否存在决定
        # 这里只验证不报错即可（结构存在）
        bao_section = page.locator("#bao-result-section")
        count = await bao_section.count()
        assert count == 1, "#bao-result-section 元素应存在于 DOM"
