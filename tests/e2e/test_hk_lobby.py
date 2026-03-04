"""港式麻将大厅功能 E2E 测试。"""
import pytest
import httpx

from helpers import api_get
from page_objects import LobbyPage


@pytest.mark.asyncio
class TestHKLobby:

    async def test_lobby_loads(self, lobby_page, base_url):
        """大厅页面正常加载，标题和关键元素可见。"""
        title = await lobby_page.title()
        assert "麻將" in title or "Mahjong" in title or "麻将" in title

        assert await lobby_page.locator("#btn-create-room").is_visible()
        assert await lobby_page.locator("#rooms-tbody").is_visible()

    async def test_create_hk_room_appears_in_lobby(self, lobby_page, base_url):
        """创建港式房间后在大厅的规则列显示「港式」标签。"""
        lp = LobbyPage(lobby_page, base_url)

        # 记录创建前的房间数
        before = await lp.room_count()

        # 通过 API 直接创建（避免 prompt 对话框影响测试）
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{base_url}/api/rooms",
                json={"name": "E2E-HK-Test", "ruleset": "hk"},
            )
        assert resp.status_code == 201

        # 刷新大厅并等待
        await lobby_page.reload()
        await lobby_page.wait_for_selector("#rooms-tbody")

        after = await lp.room_count()
        assert after > before

        # 验证港式标签存在
        assert await lp.ruleset_badge_exists("hk"), \
            "大厅中未找到「港式」规则标签"

    async def test_hk_room_shows_waiting_status(self, lobby_page, base_url):
        """新创建的港式房间 API 返回状态应为 waiting，规则集为 hk。"""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{base_url}/api/rooms",
                json={"name": "E2E-Status-Test", "ruleset": "hk"},
            )
        assert resp.status_code == 201
        room = resp.json()
        assert room["ruleset"] == "hk", f"期望 ruleset=hk，得到 {room['ruleset']}"
        assert room["status"] == "waiting", f"期望 status=waiting，得到 {room['status']}"

    async def test_multiple_rooms_visible(self, lobby_page, base_url):
        """创建两个房间，大厅中都可见（房间数 >= 2）。"""
        async with httpx.AsyncClient() as client:
            for i in range(2):
                await client.post(
                    f"{base_url}/api/rooms",
                    json={"name": f"E2E-Multi-{i}", "ruleset": "hk"},
                )

        await lobby_page.reload()
        await lobby_page.wait_for_selector("#rooms-tbody")

        lp = LobbyPage(lobby_page, base_url)
        count = await lp.room_count()
        # 至少有 2 个房间（可能有更多来自其他测试）
        assert count >= 2, f"期望至少 2 个房间，实际显示 {count} 个"
