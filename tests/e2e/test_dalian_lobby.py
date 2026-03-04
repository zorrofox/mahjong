"""大连穷胡大厅相关 E2E 测试。"""
import pytest
import httpx
from page_objects import LobbyPage


@pytest.mark.asyncio
class TestDalianLobby:

    async def test_create_dalian_room_shows_badge(self, lobby_page, base_url):
        """创建大连房间后大厅显示「大连」标签。"""
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{base_url}/api/rooms",
                                     json={"name": "E2E-Dalian", "ruleset": "dalian"})
        assert resp.status_code == 201
        assert resp.json()["ruleset"] == "dalian"

        await lobby_page.reload()
        await lobby_page.wait_for_selector("#rooms-tbody")

        lp = LobbyPage(lobby_page, base_url)
        assert await lp.ruleset_badge_exists("dalian"), \
            "大厅未显示大连标签"

    async def test_dalian_room_api_fields(self, lobby_page, base_url):
        """创建大连房间时 API 返回正确的 ruleset 字段。"""
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{base_url}/api/rooms",
                                     json={"ruleset": "dalian", "name": "E2E-Field-Test"})
        room = resp.json()
        assert room["ruleset"] == "dalian"
        assert room["status"] == "waiting"
        assert room["max_players"] == 4

    async def test_hk_and_dalian_rooms_coexist(self, lobby_page, base_url):
        """港式和大连房间可以同时在大厅显示。"""
        async with httpx.AsyncClient() as client:
            await client.post(f"{base_url}/api/rooms",
                              json={"ruleset": "hk",     "name": "E2E-HK-Co"})
            await client.post(f"{base_url}/api/rooms",
                              json={"ruleset": "dalian", "name": "E2E-DL-Co"})

        await lobby_page.reload()
        await lobby_page.wait_for_selector("#rooms-tbody")

        lp = LobbyPage(lobby_page, base_url)
        assert await lp.ruleset_badge_exists("hk"),     "未找到港式房间"
        assert await lp.ruleset_badge_exists("dalian"), "未找到大连房间"
