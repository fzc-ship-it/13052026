import asyncio
import logging
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from playwright.async_api import async_playwright
from src.stealth_manager import StealthManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BOEScraper:
    BASE_URL = "https://subastas.boe.es/"
    SEARCH_URL = "https://subastas.boe.es/subastas_ava.php"

    def __init__(self, headless=True):
        self.headless = headless
        self.browser = None
        self.context = None

    async def start(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        self.context = await self.browser.new_context(
            user_agent=StealthManager.get_random_user_agent(),
            viewport={"width": 1280, "height": 720}
        )
        self.page = await self.context.new_page()
        await StealthManager.apply_stealth(self.page)

    async def stop(self):
        if self.browser:
            await self.browser.close()
        if hasattr(self, 'playwright'):
            await self.playwright.stop()

    async def navigate_to_search(self):
        """Navigates to the advanced search page."""
        logger.info(f"Navigating to {self.SEARCH_URL}")
        await self.page.goto(self.SEARCH_URL, wait_until="networkidle")
        await StealthManager.human_delay()

    async def get_provinces(self):
        """Extracts available provinces from the dropdown."""
        provinces = await self.page.query_selector_all("select[name='dato[8]'] option")
        province_list = []
        for p in provinces:
            value = await p.get_attribute("value")
            text = await p.inner_text()
            if value and value != "":
                province_list.append({"value": value, "name": text.strip()})
        return province_list

    async def select_province(self, province_value):
        """Selects a province in the search form."""
        logger.info(f"Selecting province with value: {province_value}")
        await self.page.select_option("select[name='dato[8]']", province_value)
        await StealthManager.human_delay(500, 1500)

    async def select_property_type(self):
        """Selects 'Inmuebles' as the property type."""
        logger.info("Selecting property type: Inmuebles")
        await self.page.click("input[name='dato[3]'][value='I']", force=True)
        await StealthManager.human_delay(500, 1500)

    async def select_auction_status(self, status):
        """Selects the auction status.
        '': Any, 'EJ': Celebrándose (Active), 'PC': Concluida (Finished)
        """
        logger.info(f"Selecting status: {status}")
        await self.page.click(f"input[name='dato[2]'][value='{status}']", force=True)
        await StealthManager.human_delay(500, 1500)

    async def set_date_range(self, date_type, start_date, end_type):
        """Sets date range for search.
        date_type: 'inicio' or 'fin'
        start_date, end_type: string 'YYYY-MM-DD'
        """
        field_idx = "18" if date_type == "inicio" else "17"
        logger.info(f"Setting {date_type} date range: {start_date} to {end_type}")
        await self.page.fill(f"input[name='dato[{field_idx}][0]']", start_date)
        await self.page.fill(f"input[name='dato[{field_idx}][1]']", end_type)
        await StealthManager.human_delay(500, 1500)

    async def perform_search(self):
        """Clicks the search button."""
        logger.info("Performing search...")
        await self.page.click("input[name='accion'][value='Buscar']")
        await self.page.wait_for_load_state("networkidle")
        await StealthManager.human_delay()

    async def get_auction_links(self):
        """Extracts links to individual auctions from the results page."""
        links = await self.page.query_selector_all("a.resultado-busqueda-link-defecto")
        auction_links = []
        for link in links:
            href = await link.get_attribute("href")
            if href:
                # Ensure absolute URL
                if not href.startswith("http"):
                    href = self.BASE_URL + href.lstrip("./")
                auction_links.append(href)
        logger.info(f"Found {len(auction_links)} auction links on current page.")
        return auction_links

    async def has_next_page(self):
        """Checks if there is a next page of results."""
        next_button = await self.page.query_selector("li.siguiente a")
        return next_button is not None

    async def go_to_next_page(self):
        """Navigates to the next page of results."""
        next_button = await self.page.query_selector("li.siguiente a")
        if next_button:
            logger.info("Navigating to next page...")
            await next_button.click()
            await self.page.wait_for_load_state("networkidle")
            await StealthManager.human_delay()

    async def extract_auction_details(self, url):
        """Extracts detailed information from a single auction page."""
        logger.info(f"Extracting details from {url}")
        await self.page.goto(url, wait_until="networkidle")
        await StealthManager.simulate_human_scroll(self.page)

        details = {"url": url}

        # Identification - Tab 1
        details.update(await self._extract_table_data())

        # Tabs for details: ver=2 (General), ver=3 (Property), ver=4 (Bids)
        tabs = [
            {"name": "informacion_general", "ver": "2"},
            {"name": "bienes", "ver": "3"},
            {"name": "pujas", "ver": "4"}
        ]

        for tab in tabs:
            tab_url = self._get_tab_url(url, tab["ver"])
            await self.page.goto(tab_url, wait_until="networkidle")
            tab_data = await self._extract_table_data()
            details.update(tab_data)

            # Special check for "sin pujas" in the 'pujas' tab
            if tab["name"] == "pujas":
                details["sin_pujas"] = await self._check_if_no_bids()

        return details

    def _get_tab_url(self, base_url, ver_value):
        """Robustly manipulates the URL to switch between tabs."""
        parsed = urlparse(base_url)
        query = parse_qs(parsed.query)
        query['ver'] = [ver_value]
        new_query = urlencode(query, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

    async def _check_if_no_bids(self):
        """Checks the bids tab for the 'No hay pujas' message."""
        content = await self.page.content()
        # Common message when no bids are present
        return "No hay pujas para esta subasta" in content or "No existen pujas" in content

    async def _extract_table_data(self):
        """Helper to extract key-value pairs from tables in the BOE portal."""
        data = {}
        rows = await self.page.query_selector_all("tr")
        for row in rows:
            th = await row.query_selector("th")
            td = await row.query_selector("td")
            if th and td:
                key = await th.inner_text()
                value = await td.inner_text()
                # Clean keys: normalize to snake_case for DB
                clean_key = key.strip().lower().replace(" ", "_").replace(":", "")
                data[clean_key] = value.strip()
        return data
