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


async def _kick_start_ws(base_url: str, room_id: str,
                          player_id: str = "ai_player_1") -> None:
    """
    短暂 WebSocket 连接触发服务端的 _run_ai_turn 任务。
    断开后 AI_TAKEOVER_GRACE 秒内 AI 接管该座位，游戏继续。
    """
    import websockets
    ws_url = base_url.replace("http://", "ws://") + f"/ws/{room_id}/{player_id}"
    try:
        async with websockets.connect(ws_url, open_timeout=5,
                                       ping_interval=None) as ws:
            await asyncio.sleep(0.3)   # 给服务器足够时间启动 AI 循环
            # 主动关闭 → 服务端启动 AI 接管倒计时
    except Exception:
        pass  # 连接失败时忽略（游戏可能已结束）


async def run_all_ai_game(base_url: str, ruleset: str = "hk",
                          poll_interval: float = 0.5,
                          max_wait: float = 90.0) -> dict:
    """
    创建"全 AI"局并等待游戏结束。

    流程：
    1. 以 "e2e_kick" 身份加入房间（非 ai_player_ 前缀，确保 AI 接管机制生效）
    2. 开始游戏（剩余 3 座由 AI 填满）
    3. 短暂 WS 连接触发 _run_ai_turn（纯 REST 启动后游戏静止）
    4. 断开后 AI_TAKEOVER_GRACE=2s → e2e_kick 被 AI 接管
    5. 4 个 AI 全部就位，游戏自动跑完
    6. 轮询 /api/rooms 直到 status=ended

    返回 {"room_id": str, "observer_player_id": str}
      observer_player_id = "e2e_kick"，重连时会触发 is_reconnect=True game_over
    """
    kick_pid = "e2e_kick"
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{base_url}/api/rooms",
                              json={"name": "E2E-AllAI", "ruleset": ruleset})
        room_id = r.json()["id"]

        # 加入房间（作为 kick 玩家，非 ai_player_ 前缀）
        await client.post(f"{base_url}/api/rooms/{room_id}/join",
                          json={"player_id": kick_pid})

        # 开始游戏（AI 填满剩余 3 座）
        await client.post(f"{base_url}/api/rooms/{room_id}/start")

    # 短暂 WS 连接触发 _run_ai_turn；断开后 AI 接管 e2e_kick（非 ai_player_ 前缀才会接管）
    await _kick_start_ws(base_url, room_id, player_id=kick_pid)

    # 等待 AI 接管（MJ_AI_TAKEOVER_GRACE=2.0s）后再轮询
    await asyncio.sleep(2.5)

    async with httpx.AsyncClient() as client:
        waited = 0.0
        while waited < max_wait:
            await asyncio.sleep(poll_interval)
            waited += poll_interval
            rooms_resp = await client.get(f"{base_url}/api/rooms")
            rooms = rooms_resp.json()
            room = next((rm for rm in rooms if rm["id"] == room_id), None)
            if room and room["status"] in ("ended", "finished"):
                return {"room_id": room_id, "observer_player_id": kick_pid}

    raise TimeoutError(f"All-AI game did not finish within {max_wait}s")


async def wait_for_game_over(page: Page, timeout: int = 90_000) -> dict:
    """
    等待结算弹窗出现，返回结算信息。
    适用于：页面通过重连（is_reconnect=True）触发 game_over 事件的场景。
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


def chips_are_zero_sum(scores: list[dict], initial: int = 1000) -> bool:
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
