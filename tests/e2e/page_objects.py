"""Page Object Models for the Mahjong game."""
from playwright.async_api import Page


class LobbyPage:
    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url

    async def goto(self):
        await self.page.goto(self.base_url)
        await self.page.wait_for_selector("#rooms-tbody")

    async def room_count(self) -> int:
        rows = await self.page.locator("#rooms-tbody tr").count()
        return rows

    async def get_room_rulesets(self) -> list[str]:
        """返回大厅中所有房间的规则集标签文字。"""
        cells = await self.page.locator("#rooms-tbody td:nth-child(2)").all()
        return [(await c.inner_text()).strip() for c in cells]

    async def ruleset_badge_exists(self, ruleset: str) -> bool:
        text = "大连" if ruleset == "dalian" else "港式"
        return await self.page.locator(f"#rooms-tbody td:nth-child(2) :text('{text}')").count() > 0


class GamePage:
    def __init__(self, page: Page):
        self.page = page

    @property
    def ruleset_badge(self):
        return self.page.locator("#ruleset-badge")

    @property
    def bao_badge(self):
        return self.page.locator("#bao-badge")

    @property
    def game_over_modal(self):
        return self.page.locator("#game-over-modal")

    @property
    def winner_name(self):
        return self.page.locator("#winner-name")

    @property
    def win_type_label(self):
        return self.page.locator("#win-type-label")

    @property
    def play_again_btn(self):
        return self.page.locator("#btn-play-again")

    @property
    def scores_body(self):
        return self.page.locator("#scores-body")

    @property
    def my_hand(self):
        return self.page.locator("#my-hand .tile[data-tile]")

    @property
    def tenpai_badges(self):
        return self.page.locator(".tenpai-badge")

    async def is_game_over(self) -> bool:
        return await self.page.locator("#game-over-modal:not(.hidden)").count() > 0

    async def ruleset_text(self) -> str:
        el = self.page.locator("#ruleset-badge")
        if await el.is_visible():
            return (await el.inner_text()).strip()
        return ""
