"""游戏流程辅助函数。"""
import asyncio

import httpx
from playwright.async_api import Page


async def create_room(page: Page, base_url: str, ruleset: str = "hk", name: str = "") -> str:
    """
    在大厅创建房间，返回 room_id。
    处理两次 prompt 对话框（房间名 + 规则集选择）。
    """
    rule_choice = "2" if ruleset == "dalian" else "1"

    # 设置 dialog 处理器（按顺序处理两次 prompt）
    dialogs = []

    async def handle_dialog(dialog):
        dialogs.append(dialog)
        if len(dialogs) == 1:
            await dialog.accept(name)          # 房间名
        else:
            await dialog.accept(rule_choice)   # 规则集

    page.on("dialog", handle_dialog)
    await page.click("#btn-create-room")

    # 等待跳转到 game.html
    await page.wait_for_url("**/game.html**", timeout=10_000)
    page.remove_listener("dialog", handle_dialog)

    # 从 URL 提取 room_id
    url = page.url
    params = dict(p.split("=") for p in url.split("?", 1)[1].split("&"))
    return params["room"]


async def start_game(page: Page) -> None:
    """点击 Start Game 按钮，等待游戏开始（手牌出现）。"""
    btn = page.locator("#btn-start")
    if await btn.is_visible():
        await btn.click()
    await page.wait_for_selector(".tile[data-tile]", timeout=15_000)


async def wait_for_game_over(page: Page, timeout: int = 90_000) -> dict:
    """
    等待结算弹窗出现，返回结算信息。
    """
    await page.wait_for_selector("#game-over-modal:not(.hidden)", timeout=timeout)

    # 提取结算数据
    winner = await page.locator("#winner-name").inner_text()
    win_type = await page.locator("#win-type-label").inner_text()

    # 提取各玩家筹码变化（本局 + 累计）
    rows = await page.locator("#scores-body tr").all()
    scores = []
    for row in rows:
        cells = await row.locator("td").all()
        if len(cells) >= 3:
            name   = (await cells[0].inner_text()).strip()
            delta  = (await cells[1].inner_text()).strip()
            chips  = (await cells[2].inner_text()).strip()
            scores.append({"name": name, "delta": delta, "chips": int(chips.replace(",", ""))})

    # 番数明细
    han_visible = await page.locator("#han-breakdown-section").is_visible()
    han_breakdown = []
    han_total_text = ""
    if han_visible:
        items = await page.locator("#han-body tr").all()
        for item in items:
            cells = await item.locator("td").all()
            if len(cells) >= 2:
                han_breakdown.append({
                    "name": (await cells[0].inner_text()).strip(),
                    "fan":  (await cells[1].inner_text()).strip(),
                })
        han_total_text = await page.locator("#han-total").inner_text()

    return {
        "winner": winner,
        "win_type": win_type,
        "scores": scores,
        "han_breakdown": han_breakdown,
        "han_total_text": han_total_text,
        "is_draw": "流局" in win_type or "Draw" in win_type,
    }


async def chips_are_zero_sum(scores: list[dict], initial: int = 1000) -> bool:
    """验证所有玩家筹码总和 = n × initial_chips。"""
    total = sum(s["chips"] for s in scores)
    return total == initial * len(scores)


async def api_get(base_url: str, path: str) -> dict:
    """直接调用 REST API（用于验证）。"""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{base_url}{path}", timeout=5)
        resp.raise_for_status()
        return resp.json()


async def wait_for_my_turn_or_game_over(page: Page, timeout: int = 90_000) -> str:
    """
    等待轮到自己出牌 或 游戏结束。
    返回 "discard" | "game_over"。
    """
    locator = page.locator("#btn-discard:not([disabled]), #game-over-modal:not(.hidden)")
    await locator.first.wait_for(timeout=timeout)

    if await page.locator("#game-over-modal:not(.hidden)").is_visible():
        return "game_over"
    return "discard"


async def discard_first_tile(page: Page) -> None:
    """选中第一张手牌并点击 Discard 打。"""
    tiles = await page.locator("#my-hand .tile[data-tile]").all()
    if tiles:
        await tiles[0].click()
    btn = page.locator("#btn-discard")
    await btn.wait_for(state="enabled", timeout=5_000)
    await btn.click()
