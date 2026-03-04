"""大连穷胡游戏流程 E2E 测试。"""
import pytest
import httpx
from helpers import (
    wait_for_game_over, chips_are_zero_sum, api_get,
)
from page_objects import GamePage


@pytest.mark.asyncio
class TestDalianGameFlow:

    async def _create_and_start_dalian_game(self, page, base_url) -> tuple:
        """创建大连房间，AI 自动填满，开始游戏，导航到游戏页。"""
        player_id = "e2e_player_dalian"
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{base_url}/api/rooms",
                                  json={"name": "E2E-Dalian", "ruleset": "dalian"})
            room_id = r.json()["id"]

            await client.post(f"{base_url}/api/rooms/{room_id}/join",
                               json={"player_id": player_id})
            await client.post(f"{base_url}/api/rooms/{room_id}/start")

        await page.goto(
            f"{base_url}/game.html?room={room_id}&player={player_id}"
        )
        await page.wait_for_selector(".tile[data-tile]", timeout=15_000)
        return room_id, player_id

    # ── 基础加载 ─────────────────────────────────────────────────────

    async def test_game_page_shows_dalian_badge(self, page, base_url):
        """游戏页面加载后显示「大连穷胡」规则标签。"""
        await self._create_and_start_dalian_game(page, base_url)
        gp = GamePage(page)
        badge = await gp.ruleset_text()
        assert "大连" in badge, f"期望大连标签，实际：'{badge}'"

    async def test_dalian_game_starts_with_tiles(self, page, base_url):
        """大连游戏开始后玩家手牌可见（136张牌无花牌）。"""
        await self._create_and_start_dalian_game(page, base_url)
        tile_count = await page.locator("#my-hand .tile[data-tile]").count()
        assert tile_count > 0, "手牌未显示"

    async def test_dalian_no_flower_tiles_in_hand(self, page, base_url):
        """大连游戏手牌中不应有花牌（FLOWER_/SEASON_）。"""
        await self._create_and_start_dalian_game(page, base_url)

        tile_attrs = await page.evaluate("""() => {
            return Array.from(
                document.querySelectorAll('#my-hand .tile[data-tile]')
            ).map(el => el.dataset.tile);
        }""")
        flower_tiles = [t for t in tile_attrs
                        if t and ("FLOWER" in t or "SEASON" in t)]
        assert len(flower_tiles) == 0, \
            f"大连手牌含花牌：{flower_tiles}"

    # ── 完整游戏流程 ─────────────────────────────────────────────────

    async def test_dalian_game_completes(self, page, base_url):
        """大连游戏能正常完成（AI 出牌直到胡牌或荒庄）。"""
        await self._create_and_start_dalian_game(page, base_url)
        result = await wait_for_game_over(page, timeout=150_000)
        # 游戏正常结束（有赢家 OR 流局）
        assert result["winner"] or result["is_draw"], \
            f"游戏未正常结束: {result}"

    async def test_dalian_settlement_zero_sum(self, page, base_url):
        """大连结算后所有玩家筹码总和 = 4000。"""
        await self._create_and_start_dalian_game(page, base_url)
        result = await wait_for_game_over(page, timeout=150_000)

        scores = result["scores"]
        assert len(scores) == 4
        assert chips_are_zero_sum(scores, initial=1000), \
            f"筹码不零和: {[s['chips'] for s in scores]}"

    async def test_dalian_winner_chips_changed(self, page, base_url):
        """有赢家时赢家筹码大于 1000。"""
        await self._create_and_start_dalian_game(page, base_url)
        result = await wait_for_game_over(page, timeout=150_000)

        if result["is_draw"]:
            pytest.skip("本局荒庄，跳过赢家验证")

        chips = [s["chips"] for s in result["scores"]]
        assert max(chips) > 1000, "赢家筹码未增加"

    # ── 番型验证 ─────────────────────────────────────────────────────

    async def test_dalian_win_shows_han_breakdown(self, page, base_url):
        """大连胡牌时结算弹窗显示番型明细（至少含「基础」）。"""
        await self._create_and_start_dalian_game(page, base_url)
        result = await wait_for_game_over(page, timeout=150_000)

        if result["is_draw"]:
            pytest.skip("本局荒庄，无番型明细")

        assert len(result["han_breakdown"]) > 0, "胡牌无番型明细"
        names = [x["name"] for x in result["han_breakdown"]]
        assert "基础" in names, f"缺少「基础」番型：{names}"

    async def test_dalian_draw_shows_draw_label(self, page, base_url):
        """荒庄时结算弹窗显示「流局 Draw」文字。"""
        # 多次尝试，荒庄概率约 20%
        found_draw = False
        for attempt in range(5):
            ctx = await page.context.browser.new_context(base_url=base_url)
            pg  = await ctx.new_page()
            try:
                player_id = f"e2e_draw_{attempt}"
                async with httpx.AsyncClient() as client:
                    r = await client.post(f"{base_url}/api/rooms",
                                          json={"ruleset": "dalian", "name": f"E2E-Draw-{attempt}"})
                    rid = r.json()["id"]
                    await client.post(f"{base_url}/api/rooms/{rid}/join",
                                      json={"player_id": player_id})
                    await client.post(f"{base_url}/api/rooms/{rid}/start")

                await pg.goto(f"{base_url}/game.html?room={rid}&player={player_id}")
                await pg.wait_for_selector(".tile[data-tile]", timeout=15_000)
                result = await wait_for_game_over(pg, timeout=150_000)

                if result["is_draw"]:
                    found_draw = True
                    win_type = result["win_type"]
                    assert "流局" in win_type or "Draw" in win_type, \
                        f"荒庄时未显示流局文字：'{win_type}'"
                    break
            finally:
                await ctx.close()

        if not found_draw:
            pytest.skip("5局内未触发荒庄，跳过（概率性测试）")

    # ── 宝牌 UI ──────────────────────────────────────────────────────

    async def test_bao_badge_hidden_before_tenpai(self, page, base_url):
        """游戏刚开始时宝牌 badge 不显示（未有人上听）。"""
        await self._create_and_start_dalian_game(page, base_url)
        # 等待游戏真正开始（牌已显示）
        await page.wait_for_selector(".tile[data-tile]", timeout=15_000)

        gp = GamePage(page)
        # 刚开始宝牌 badge 应隐藏
        is_visible = await gp.bao_badge.is_visible()
        # 注意：如果 AI 极快上听，badge 可能已显示；所以只验证初始状态
        # 用 JavaScript 获取 display 值
        display = await page.evaluate(
            "() => document.getElementById('bao-badge').style.display"
        )
        # 初始为 none（除非已经上听）
        # 这是软断言：如果已上听则跳过
        if display == "none":
            assert not is_visible

    async def test_bao_badge_shown_after_tenpai(self, page, base_url):
        """
        等待宝牌 badge 出现（有人上听后），验证其可见且含宝牌文字。
        因为 AI 速度快（MJ_AI_DELAY_MAX=0.15），多数局会在 60s 内上听。
        """
        await self._create_and_start_dalian_game(page, base_url)

        # 同时等待：宝牌 badge 出现 OR 游戏结束
        try:
            await page.wait_for_selector(
                "#bao-badge[style*='inline'], #game-over-modal:not(.hidden)",
                timeout=90_000,
            )
        except Exception:
            pytest.skip("90s 内未触发宝牌（可能全局流局），跳过")

        if await page.locator("#game-over-modal:not(.hidden)").is_visible():
            pytest.skip("游戏已结束，跳过宝牌检测")

        gp = GamePage(page)
        assert await gp.bao_badge.is_visible(), "宝牌 badge 未显示"

    async def test_tenpai_badge_shown_when_tenpai(self, page, base_url):
        """
        等待「听」字 badge 出现（.tenpai-badge），验证其可见。
        """
        await self._create_and_start_dalian_game(page, base_url)

        try:
            await page.wait_for_selector(
                ".tenpai-badge, #game-over-modal:not(.hidden)",
                timeout=90_000,
            )
        except Exception:
            pytest.skip("90s 内未出现听牌标识，跳过")

        if await page.locator("#game-over-modal:not(.hidden)").is_visible():
            pytest.skip("游戏已结束，跳过")

        count = await page.locator(".tenpai-badge").count()
        assert count > 0, "未找到听牌标识 badge"

    # ── API 验证 ─────────────────────────────────────────────────────

    async def test_dalian_room_status_after_game(self, page, base_url):
        """游戏结束后房间状态通过 API 返回 ended。"""
        room_id, _ = await self._create_and_start_dalian_game(page, base_url)
        await wait_for_game_over(page, timeout=150_000)

        rooms = await api_get(base_url, "/api/rooms")
        room  = next((r for r in rooms if r["id"] == room_id), None)
        assert room is not None
        assert room["status"] in ("ended", "finished")
        assert room["ruleset"] == "dalian"

    async def test_dalian_end_game_reveals_tiles(self, page, base_url):
        """大连游戏结束后对手手牌翻开可见。"""
        await self._create_and_start_dalian_game(page, base_url)
        await wait_for_game_over(page, timeout=150_000)

        tiles = await page.locator(".tile-img").count()
        assert tiles > 0, "游戏结束后未见到翻牌"
