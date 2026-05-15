import random
import asyncio
import os
from playwright.async_api import Page, BrowserContext
from playwright_stealth import Stealth

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edge/123.0.0.0"
]

SCREEN_RESOLUTIONS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 1080},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900}
]

class StealthManager:
    @staticmethod
    def get_random_user_agent():
        return random.choice(USER_AGENTS)

    @staticmethod
    def get_random_resolution():
        return random.choice(SCREEN_RESOLUTIONS)

    @staticmethod
    async def apply_stealth(page: Page):
        """Applies professional stealth settings and realistic behavior."""
        await Stealth().apply_stealth_async(page)

        # Add realistic headers
        await page.set_extra_http_headers({
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.google.com/",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1"
        })

    @staticmethod
    async def human_delay(min_ms=2000, max_ms=5000):
        """Simulates a human-like delay (throtled to 2-5s as requested)."""
        delay = random.uniform(min_ms, max_ms) / 1000.0
        await asyncio.sleep(delay)

    @staticmethod
    async def simulate_human_scroll(page: Page):
        """Simulates human-like scrolling behavior."""
        for _ in range(random.randint(2, 4)):
            scroll_amount = random.randint(300, 700)
            await page.mouse.wheel(0, scroll_amount)
            await asyncio.sleep(random.uniform(0.8, 2.0))

    @staticmethod
    async def random_mouse_move(page: Page):
        """Simulates random mouse movements to a random point."""
        width = page.viewport_size["width"]
        height = page.viewport_size["height"]
        x = random.randint(0, width)
        y = random.randint(0, height)
        # Move mouse in steps to simulate trajectory
        await page.mouse.move(x, y, steps=random.randint(5, 15))
        await asyncio.sleep(random.uniform(0.1, 0.5))

    @staticmethod
    def get_session_dir():
        """Returns the path to the persistent session directory."""
        path = os.path.join(os.getcwd(), "browser_session")
        if not os.path.exists(path):
            os.makedirs(path)
        return path
