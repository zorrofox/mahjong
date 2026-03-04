"""E2E test fixtures for the Mahjong game."""
import os
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

PROJECT_ROOT = Path(__file__).parent.parent.parent
BACKEND_DIR  = PROJECT_ROOT / "backend"


def find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def server():
    port = find_free_port()
    env = os.environ.copy()
    env.update({
        "MJ_AI_DELAY_MIN":      "0.05",
        "MJ_AI_DELAY_MAX":      "0.15",
        "MJ_CLAIM_TIMEOUT":     "5.0",
        "MJ_AI_TAKEOVER_GRACE": "3.0",
    })
    proc = subprocess.Popen(
        ["python3", "-m", "uvicorn", "main:app", "--port", str(port), "--log-level", "warning"],
        cwd=BACKEND_DIR,
        env=env,
    )
    # 等待服务就绪
    base = f"http://localhost:{port}"
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
    proc.wait(timeout=5)


@pytest.fixture(scope="session")
def base_url(server):
    return server["base_url"]


@pytest.fixture(scope="session")
async def browser():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True)
        yield b
        await b.close()


@pytest.fixture
async def page(browser, base_url):
    ctx = await browser.new_context(base_url=base_url)
    pg  = await ctx.new_page()
    yield pg
    await ctx.close()


@pytest.fixture
async def lobby_page(page, base_url):
    await page.goto(base_url)
    await page.wait_for_selector("#rooms-tbody", timeout=10_000)
    return page
