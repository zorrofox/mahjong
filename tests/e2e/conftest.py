"""E2E test fixtures for the Mahjong game."""
import os
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest
import pytest_asyncio
from playwright.async_api import async_playwright

PROJECT_ROOT = Path(__file__).parent.parent.parent
BACKEND_DIR  = PROJECT_ROOT / "backend"


def find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


# ── Session-scoped SYNC fixtures (no event loop issues) ────────────────────

@pytest.fixture(scope="session")
def server():
    """Start the backend server once for the whole test session."""
    port = find_free_port()
    env = os.environ.copy()
    env.update({
        "MJ_AI_DELAY_MIN":      "0.05",
        "MJ_AI_DELAY_MAX":      "0.15",
        "MJ_CLAIM_TIMEOUT":     "1.5",   # 声索窗口只等 1.5s，加速全局完成
        "MJ_AI_TAKEOVER_GRACE": "2.0",
    })
    proc = subprocess.Popen(
        ["python3", "-m", "uvicorn", "main:app",
         "--port", str(port), "--log-level", "warning"],
        cwd=BACKEND_DIR,
        env=env,
    )
    base = f"http://localhost:{port}"
    # Wait up to 20s for the server to be ready
    for _ in range(40):
        try:
            urllib.request.urlopen(f"{base}/api/rooms", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        proc.kill()
        raise RuntimeError("Server did not start in time")

    yield {"port": port, "base_url": base}

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def base_url(server):
    return server["base_url"]


# ── Function-scoped ASYNC fixtures (each test gets its own browser/page) ───
# Using function scope avoids pytest-asyncio session/loop conflicts.
# Browser launch is fast (<1s), so per-test overhead is acceptable.

@pytest_asyncio.fixture
async def page(base_url):
    """Fresh browser page for each test."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(base_url=base_url)
        pg  = await ctx.new_page()
        yield pg
        await ctx.close()
        await browser.close()


@pytest_asyncio.fixture
async def lobby_page(page, base_url):
    """Page already navigated to the lobby."""
    await page.goto(base_url)
    await page.wait_for_selector("#rooms-tbody", timeout=10_000)
    return page
