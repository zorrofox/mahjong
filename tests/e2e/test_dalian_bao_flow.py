"""大连穷胡宝牌「看宝/不看宝」流程 E2E 测试。

测试策略：
  - 创建大连房间并以人类身份加入，导航到游戏页使 JS 就绪
  - 通过 page.evaluate 调用 handleBaoDeclared() 模拟服务端揭宝事件
  - 通过 _mahjongTestExports 钩子读取内部状态（let 变量不在 window 上）
  - 测试三条路径：看宝 / 不看宝（手动关闭）/ 超时自动看宝
"""
import asyncio

import httpx
import pytest
import pytest_asyncio
from playwright.async_api import Page

BAO_TILE  = "BAMBOO_5"
PLAYER_ID = "human_bao_e2e"


# ── 辅助函数 ─────────────────────────────────────────────────────────────────

async def _create_and_join_dalian(base_url: str, player_id: str) -> str:
    """REST API 创建大连房间并加入，返回 room_id。"""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{base_url}/api/rooms",
            json={"name": "BaoFlowTest", "ruleset": "dalian"},
        )
        room_id = r.json()["id"]
        await client.post(f"{base_url}/api/rooms/{room_id}/join",
                          json={"player_id": player_id})
        await client.post(f"{base_url}/api/rooms/{room_id}/start")
    return room_id


async def _goto_game(page: Page, base_url: str, room_id: str, player_id: str) -> None:
    """导航到游戏页并等待 JS 测试钩子就绪（顶层变量，不依赖 DOMContentLoaded）。"""
    await page.goto(
        f"{base_url}/game.html?room={room_id}&player={player_id}",
    )
    # _baoTest 在脚本顶层立即赋值，脚本执行完即可用
    await page.wait_for_function(
        "typeof window._baoTest === 'object' && !!window._baoTest.resetState",
        timeout=15_000,
    )


async def _inject_bao(page: Page, bao_tile: str = BAO_TILE,
                      new_tenpai: bool = False, player_idx: int = 1,
                      dice: int = 3) -> None:
    """重置宝牌内部状态并模拟 bao_declared 事件。"""
    await page.evaluate(f"""() => {{
        window._baoTest.resetState();
        handleBaoDeclared({{
            bao_tile:   '{bao_tile}',
            player_idx: {player_idx},
            dice:       {dice},
            new_tenpai: {'true' if new_tenpai else 'false'},
            rerolled:   false,
        }});
    }}""")


async def _get_hide_bao(page: Page) -> bool:
    """读取内部 _hideBao 变量（通过顶层测试钩子）。"""
    return await page.evaluate("() => window._baoTest.getHideBao()")


async def _get_bao_peek_offered(page: Page) -> bool:
    """读取内部 _baoPeekOffered 变量（通过顶层测试钩子）。"""
    return await page.evaluate("() => window._baoTest.getBaoPeekOffered()")


async def _set_tenpai(page: Page, player_idx: int) -> None:
    """将指定玩家加入内部 _tenpaiPlayers（通过测试钩子，确保修改 let 变量）。"""
    await page.evaluate(f"() => window._baoTest.setTenpai({player_idx})")


# ── Fixture ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def bao_page(page, base_url):
    """大连游戏已启动，页面 + JS 钩子已就绪。"""
    room_id = await _create_and_join_dalian(base_url, PLAYER_ID)
    await _goto_game(page, base_url, room_id, PLAYER_ID)
    yield page


# ── 测试：初始状态 ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestBaoDefaultState:

    async def test_hide_bao_true_by_default(self, bao_page: Page):
        """游戏启动后默认处于不看宝状态（_hideBao=true）。"""
        hidden = await _get_hide_bao(bao_page)
        assert hidden is True, "默认应不看宝（_hideBao=true）"

    async def test_bao_badge_hidden_by_default(self, bao_page: Page):
        """宝牌尚未揭示时顶栏 badge 不可见。"""
        assert not await bao_page.locator("#bao-badge").is_visible()

    async def test_peek_overlay_hidden_by_default(self, bao_page: Page):
        """游戏启动时看宝确认弹窗不显示。"""
        assert not await bao_page.locator("#bao-peek-overlay").is_visible()


# ── 测试：弹窗弹出 ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestBaoPeekPrompt:

    async def test_peek_prompt_appears_on_bao_declared(self, bao_page: Page):
        """收到 bao_declared（含宝牌）且处于不看宝状态时，弹窗应弹出。"""
        await _inject_bao(bao_page)
        await bao_page.locator("#bao-peek-overlay").wait_for(state="visible", timeout=3_000)
        assert await bao_page.locator("#bao-peek-overlay").is_visible()

    async def test_peek_prompt_has_countdown_button(self, bao_page: Page):
        """弹窗内「看宝」按钮含倒计时文字。"""
        await _inject_bao(bao_page)
        btn = bao_page.locator("#btn-bao-peek-yes")
        await btn.wait_for(state="visible", timeout=3_000)
        text = await btn.inner_text()
        assert "看宝" in text and "(" in text, f"按钮应含「看宝 (N)」，实际：{text}"

    async def test_peek_prompt_has_dismiss_button(self, bao_page: Page):
        """弹窗内有「不看」按钮。"""
        await _inject_bao(bao_page)
        btn = bao_page.locator("#btn-bao-peek-no")
        await btn.wait_for(state="visible", timeout=3_000)
        text = await btn.inner_text()
        assert "不看" in text, f"按钮应含「不看」，实际：{text}"

    async def test_peek_prompt_not_shown_twice(self, bao_page: Page):
        """同一局弹窗只弹一次（_baoPeekOffered 防重复）。"""
        await _inject_bao(bao_page)
        await bao_page.locator("#bao-peek-overlay").wait_for(state="visible", timeout=3_000)
        await bao_page.locator("#btn-bao-peek-no").click()
        await bao_page.locator("#bao-peek-overlay").wait_for(state="hidden", timeout=3_000)

        # 再次触发（不重置状态）→ 不应再弹
        await bao_page.evaluate(f"""() => {{
            handleBaoDeclared({{
                bao_tile: '{BAO_TILE}', player_idx: 1, dice: 3,
                new_tenpai: false, rerolled: false,
            }});
        }}""")
        await asyncio.sleep(0.5)
        assert not await bao_page.locator("#bao-peek-overlay").is_visible(), \
            "同局内弹窗不应重复弹出"

    async def test_new_tenpai_also_triggers_peek_prompt(self, bao_page: Page):
        """后续上听（new_tenpai=true）也触发看宝弹窗。"""
        await _inject_bao(bao_page, new_tenpai=True)
        await bao_page.locator("#bao-peek-overlay").wait_for(state="visible", timeout=3_000)
        assert await bao_page.locator("#bao-peek-overlay").is_visible()


# ── 测试：点击「看宝」路径 ───────────────────────────────────────────────────

@pytest.mark.asyncio
class TestLookBao:

    async def test_click_look_closes_overlay(self, bao_page: Page):
        """点「看宝」后弹窗消失。"""
        await _inject_bao(bao_page)
        await bao_page.locator("#bao-peek-overlay").wait_for(state="visible", timeout=3_000)
        await bao_page.locator("#btn-bao-peek-yes").click()
        await bao_page.locator("#bao-peek-overlay").wait_for(state="hidden", timeout=3_000)
        assert not await bao_page.locator("#bao-peek-overlay").is_visible()

    async def test_click_look_shows_bao_badge(self, bao_page: Page):
        """点「看宝」后顶栏宝牌 badge 显示。"""
        await _inject_bao(bao_page)
        await bao_page.locator("#bao-peek-overlay").wait_for(state="visible", timeout=3_000)
        await bao_page.locator("#btn-bao-peek-yes").click()
        await bao_page.locator("#bao-badge").wait_for(state="visible", timeout=3_000)
        assert await bao_page.locator("#bao-badge").is_visible()

    async def test_click_look_sets_hide_bao_false(self, bao_page: Page):
        """点「看宝」后内部 _hideBao 变为 false。"""
        await _inject_bao(bao_page)
        await bao_page.locator("#bao-peek-overlay").wait_for(state="visible", timeout=3_000)
        await bao_page.locator("#btn-bao-peek-yes").click()
        await asyncio.sleep(0.3)
        assert await _get_hide_bao(bao_page) is False

    async def test_click_look_hides_topbar_button(self, bao_page: Page):
        """看宝后顶栏「看宝」按钮消失（已无需再看）。"""
        await _inject_bao(bao_page)
        await bao_page.locator("#bao-peek-overlay").wait_for(state="visible", timeout=3_000)
        await bao_page.locator("#btn-bao-peek-yes").click()
        await asyncio.sleep(0.3)
        assert not await bao_page.locator("#btn-hide-bao").is_visible()


# ── 测试：点击「不看」路径 ───────────────────────────────────────────────────

@pytest.mark.asyncio
class TestDismissBao:

    async def test_click_dismiss_closes_overlay(self, bao_page: Page):
        """点「不看」后弹窗消失。"""
        await _inject_bao(bao_page)
        await bao_page.locator("#bao-peek-overlay").wait_for(state="visible", timeout=3_000)
        await bao_page.locator("#btn-bao-peek-no").click()
        await bao_page.locator("#bao-peek-overlay").wait_for(state="hidden", timeout=3_000)
        assert not await bao_page.locator("#bao-peek-overlay").is_visible()

    async def test_click_dismiss_keeps_badge_hidden(self, bao_page: Page):
        """点「不看」后顶栏 badge 仍不显示。"""
        await _inject_bao(bao_page)
        await bao_page.locator("#bao-peek-overlay").wait_for(state="visible", timeout=3_000)
        await bao_page.locator("#btn-bao-peek-no").click()
        await asyncio.sleep(0.3)
        assert not await bao_page.locator("#bao-badge").is_visible()

    async def test_click_dismiss_keeps_hide_bao_true(self, bao_page: Page):
        """点「不看」后内部 _hideBao 仍为 true。"""
        await _inject_bao(bao_page)
        await bao_page.locator("#bao-peek-overlay").wait_for(state="visible", timeout=3_000)
        await bao_page.locator("#btn-bao-peek-no").click()
        await asyncio.sleep(0.3)
        assert await _get_hide_bao(bao_page) is True

    async def test_topbar_button_visible_when_tenpai_and_dismissed(self, bao_page: Page):
        """不看宝关闭弹窗 + 已听牌 → 顶栏「看宝」按钮可见（供后续主动看宝）。"""
        await _inject_bao(bao_page)
        await bao_page.locator("#bao-peek-overlay").wait_for(state="visible", timeout=3_000)
        await bao_page.locator("#btn-bao-peek-no").click()
        await asyncio.sleep(0.3)

        # 模拟本玩家上听
        my_idx = await bao_page.evaluate("() => window._baoTest.getMyPlayerIdx() ?? 0")
        await _set_tenpai(bao_page, my_idx)

        btn = bao_page.locator("#btn-hide-bao")
        await btn.wait_for(state="visible", timeout=3_000)
        assert await btn.is_visible()
        assert not await btn.is_disabled(), "已听牌时顶栏按钮应可点击"


# ── 测试：顶栏按钮主动看宝 ──────────────────────────────────────────────────

@pytest.mark.asyncio
class TestTopbarButton:

    async def test_topbar_button_reveals_bao_on_click(self, bao_page: Page):
        """不看宝关闭弹窗后，通过顶栏按钮主动看宝 → badge 显示、_hideBao=false。"""
        # 1. 注入并选「不看」
        await _inject_bao(bao_page)
        await bao_page.locator("#bao-peek-overlay").wait_for(state="visible", timeout=3_000)
        await bao_page.locator("#btn-bao-peek-no").click()
        await asyncio.sleep(0.3)

        # 2. 模拟上听（按钮才可用）
        my_idx = await bao_page.evaluate("() => window._baoTest.getMyPlayerIdx() ?? 0")
        await _set_tenpai(bao_page, my_idx)

        # 3. 点顶栏「看宝」
        btn = bao_page.locator("#btn-hide-bao")
        await btn.wait_for(state="visible", timeout=3_000)
        await btn.click()

        # 4. badge 出现，_hideBao=false，按钮消失
        await bao_page.locator("#bao-badge").wait_for(state="visible", timeout=3_000)
        assert await _get_hide_bao(bao_page) is False
        assert not await btn.is_visible(), "看宝后顶栏按钮应消失"

    async def test_topbar_button_disabled_when_not_tenpai(self, bao_page: Page):
        """未上听时顶栏「看宝」按钮不可见或禁用。"""
        # 只设置 _baoTile（通过 resetBaoState 重置 + 单独注入 baoTile）
        await bao_page.evaluate(f"""() => {{
            window._baoTest.resetState();
            // 模拟 _baoTile 被设置（但仍不在 tenpai）
            handleBaoDeclared({{
                bao_tile: null,  // server 不发给非听牌玩家
                player_idx: 1, dice: 3, new_tenpai: false, rerolled: false,
            }});
        }}""")
        await asyncio.sleep(0.2)
        btn = bao_page.locator("#btn-hide-bao")
        # 按钮应不可见（bao_tile=null 时 canSwitch=false）
        assert not await btn.is_visible() or await btn.is_disabled()


# ── 测试：超时自动看宝 ───────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestAutoReveal:

    async def test_auto_reveal_shows_bao_badge(self, bao_page: Page):
        """直接调用 revealBao()（等同超时）→ badge 显示。"""
        await _inject_bao(bao_page)
        await bao_page.locator("#bao-peek-overlay").wait_for(state="visible", timeout=3_000)
        await bao_page.evaluate("() => revealBao()")
        await bao_page.locator("#bao-badge").wait_for(state="visible", timeout=3_000)
        assert await bao_page.locator("#bao-badge").is_visible()

    async def test_auto_reveal_sets_hide_bao_false(self, bao_page: Page):
        """调用 revealBao() 后 _hideBao 为 false。"""
        await _inject_bao(bao_page)
        await bao_page.locator("#bao-peek-overlay").wait_for(state="visible", timeout=3_000)
        await bao_page.evaluate("() => revealBao()")
        await asyncio.sleep(0.3)
        assert await _get_hide_bao(bao_page) is False

    async def test_auto_reveal_closes_overlay(self, bao_page: Page):
        """调用 revealBao() 后弹窗关闭。"""
        await _inject_bao(bao_page)
        await bao_page.locator("#bao-peek-overlay").wait_for(state="visible", timeout=3_000)
        await bao_page.evaluate("() => revealBao()")
        await bao_page.locator("#bao-peek-overlay").wait_for(state="hidden", timeout=3_000)
        assert not await bao_page.locator("#bao-peek-overlay").is_visible()


# ── 测试：新局重置 ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestNewGameReset:

    async def test_bao_state_resets_on_new_game(self, bao_page: Page):
        """
        看宝后模拟新局 game_state（bao_tile=null, phase=drawing）→
        _hideBao 重置为 true，_baoPeekOffered 重置为 false。
        """
        # 1. 先看宝
        await _inject_bao(bao_page)
        await bao_page.locator("#bao-peek-overlay").wait_for(state="visible", timeout=3_000)
        await bao_page.evaluate("() => revealBao()")
        await asyncio.sleep(0.2)
        assert await _get_hide_bao(bao_page) is False, "前置：应已看宝"

        # 2. 模拟新局 game_state（最简字段）
        await bao_page.evaluate("""() => {
            handleGameState({
                phase: 'drawing', bao_tile: null, bao_declared: false,
                bao_revealed_count: 0, current_turn: 0, dealer_idx: 0,
                round_wind_idx: 0, ruleset: 'dalian', wall_count: 120,
                last_discard: null, winner: null, tenpai_players: [],
                available_actions: [], cumulative_scores: {},
                winning_hand_arranged: [],
                players: [
                    {id:'p0',hand:{tiles:[],hidden:false},melds:[],flowers:[],score:0},
                    {id:'p1',hand:{count:13,hidden:true},melds:[],flowers:[],score:0},
                    {id:'p2',hand:{count:13,hidden:true},melds:[],flowers:[],score:0},
                    {id:'p3',hand:{count:13,hidden:true},melds:[],flowers:[],score:0},
                ],
                discards: [[],[],[],[]],
            });
        }""")
        await asyncio.sleep(0.2)

        # 3. 验证重置
        assert await _get_hide_bao(bao_page) is True,    "新局后 _hideBao 应重置为 true"
        assert await _get_bao_peek_offered(bao_page) is False, \
            "新局后 _baoPeekOffered 应重置为 false"
        assert not await bao_page.locator("#bao-badge").is_visible(), \
            "新局后 badge 应隐藏"
