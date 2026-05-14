import asyncio
import logging
import re
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
        logger.info(f"Navigating to {self.SEARCH_URL}")
        await self.page.goto(self.SEARCH_URL, wait_until="networkidle")
        await StealthManager.human_delay()

    async def get_provinces(self):
        provinces = await self.page.query_selector_all("select[name='dato[8]'] option")
        province_list = []
        for p in provinces:
            value = await p.get_attribute("value")
            text = await p.inner_text()
            if value and value != "":
                province_list.append({"value": value, "name": text.strip()})
        return province_list

    async def select_province(self, province_value):
        await self.page.select_option("select[name='dato[8]']", province_value)
        await StealthManager.human_delay(500, 1500)

    async def select_property_type(self):
        await self.page.click("input[name='dato[3]'][value='I']", force=True)
        await StealthManager.human_delay(500, 1500)

    async def select_auction_status(self, status):
        """PU: Próxima, EJ: Celebrándose, PC: Concluida, FS: Finalizada por Gestora"""
        logger.info(f"Selecting status: {status}")
        await self.page.click(f"input[name='dato[2]'][value='{status}']", force=True)
        await StealthManager.human_delay(500, 1500)

    async def perform_search(self):
        await self.page.click("input[name='accion'][value='Buscar']")
        await self.page.wait_for_load_state("networkidle")
        await StealthManager.human_delay()

    async def get_auction_links(self):
        links = await self.page.query_selector_all("a.resultado-busqueda-link-defecto")
        auction_links = []
        for link in links:
            href = await link.get_attribute("href")
            if href:
                if not href.startswith("http"):
                    href = self.BASE_URL + href.lstrip("./")
                auction_links.append(href)
        return auction_links

    async def has_next_page(self):
        next_button = await self.page.query_selector("li.siguiente a")
        return next_button is not None

    async def go_to_next_page(self):
        next_button = await self.page.query_selector("li.siguiente a")
        if next_button:
            await next_button.click()
            await self.page.wait_for_load_state("networkidle")
            await StealthManager.human_delay()

    async def extract_auction_details(self, url):
        """Comprehensive extraction of all tabs and lots."""
        logger.info(f"Extracting full details from {url}")
        await self.page.goto(url, wait_until="networkidle")

        details = {"url": url}

        # 1. Pestaña: Información General (ver=1)
        details.update(await self._extract_table_data())

        # 2. Pestaña: Autoridad Gestora (ver=2)
        tab_2_url = self._get_tab_url(url, "2")
        await self.page.goto(tab_2_url, wait_until="networkidle")
        details.update(await self._extract_table_data())

        # Check if multiple lots exist
        lotes_str = details.get("lotes", "Sin lotes")
        has_lotes = lotes_str != "Sin lotes" and lotes_str != ""

        if not has_lotes:
            # 3. Pestaña: Bienes (ver=3) - Single lot case
            tab_3_url = self._get_tab_url(url, "3")
            await self.page.goto(tab_3_url, wait_until="networkidle")
            details.update(await self._extract_table_data())
        else:
            # 4. Pestaña: Lotes (ver=3) - Multi-lot case
            num_lotes_match = re.search(r'(\d+)', lotes_str)
            num_lotes = int(num_lotes_match.group(1)) if num_lotes_match else 0

            lots_data = []
            for i in range(1, num_lotes + 1):
                lot_url = self._get_lot_url(url, i)
                logger.info(f"Processing lot {i}/{num_lotes} at {lot_url}")
                await self.page.goto(lot_url, wait_until="networkidle")

                lot_info = {"lote_numero": i}
                # Economic data is in Tab 3 (Lotes list or individual lot detail)
                lot_info.update(await self._extract_table_data())

                # Bien details for the lot are in ver=3 with idLote, but usually it requires another click
                # Or sometimes the data is already there. Let's try to extract from the lot page.
                # If "Referencia Catastral" is missing, we might need to check if there's a specific "Bien" link for the lot.

                lots_data.append(lot_info)

            details["lots_data"] = lots_data

        return details

    def _get_tab_url(self, base_url, ver_value):
        parsed = urlparse(base_url)
        query = parse_qs(parsed.query)
        query['ver'] = [ver_value]
        # Remove idLote if we are moving to a general tab
        if 'idLote' in query: del query['idLote']
        new_query = urlencode(query, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

    def _get_lot_url(self, base_url, lot_index):
        parsed = urlparse(base_url)
        query = parse_qs(parsed.query)
        query['ver'] = ["3"]
        query['idLote'] = [str(lot_index)]
        new_query = urlencode(query, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

    async def _extract_table_data(self):
        data = {}
        rows = await self.page.query_selector_all("tr")
        for row in rows:
            th = await row.query_selector("th")
            td = await row.query_selector("td")
            if th and td:
                key = await th.inner_text()
                value = await td.inner_text()
                clean_key = key.strip().lower().replace(" ", "_").replace(":", "").replace("\n", "")
                # Normalize specific common keys
                if "identificador" in clean_key: clean_key = "identificador"
                if "código_postal" in clean_key: clean_key = "código_postal"

                data[clean_key] = value.strip()
        return data
