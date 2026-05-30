import random
import asyncio
import os
import shutil
from playwright.async_api import Page, BrowserContext
from playwright_stealth import Stealth

# Focus on updated Windows desktop profiles (Chrome and Edge)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0"
]

SCREEN_RESOLUTIONS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
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

        # Determine UA for dynamic header matching if needed
        # For simplicity, we use standardized desktop headers
        await page.set_extra_http_headers({
            "Accept-Language": "es-ES,es;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.google.com/",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none", # Changed to none as if starting fresh
            "Sec-Fetch-User": "?1",
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": "\"Windows\""
        })

    @staticmethod
    async def human_delay(min_ms=1000, max_ms=3000):
        """Simulates a human-like delay."""
        delay = random.uniform(min_ms, max_ms) / 1000.0
        await asyncio.sleep(delay)

    @staticmethod
    async def simulate_human_scroll(page: Page):
        """Simulates human-like scrolling behavior."""
        for _ in range(random.randint(1, 3)):
            scroll_amount = random.randint(200, 500)
            await page.mouse.wheel(0, scroll_amount)
            await asyncio.sleep(random.uniform(0.5, 1.5))

    @staticmethod
    async def random_mouse_move(page: Page):
        """Simulates random mouse movements to a random point."""
        viewport = page.viewport_size
        if not viewport: return

        width = viewport["width"]
        height = viewport["height"]
        x = random.randint(0, width)
        y = random.randint(0, height)
        await page.mouse.move(x, y, steps=random.randint(3, 10))

    @staticmethod
    def clean_temp_data():
        """Ensures absolute cleaning of temporary browser data if any was used."""
        temp_dir = os.path.join(os.getcwd(), "temp_browser")
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass
        return temp_dir
