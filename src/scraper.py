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

    async def scan_all_ids(self, status):
        """Quickly scans all result pages for a status and returns a set of IDs."""
        all_ids = set()
        logger.info(f"Scanning all IDs for status {status}...")
        while True:
            links = await self.get_auction_links()
            for link in links:
                try:
                    # Extract idSub from URL
                    match = re.search(r'idSub=([^&]+)', link)
                    if match:
                        all_ids.add(match.group(1))
                except Exception:
                    pass

            if await self.has_next_page():
                await self.go_to_next_page()
            else:
                break
        return all_ids

    async def extract_auction_details(self, url):
        """Comprehensive extraction with retries and missing data fixes."""
        logger.info(f"Extracting full details from {url}")

        # Retry mechanism for navigation and initial data
        max_retries = 3
        details = {"url": url}

        for attempt in range(max_retries):
            try:
                await self.page.goto(url, wait_until="networkidle", timeout=30000)
                await StealthManager.human_delay(1000, 2000)

                # Tab 1: Información General
                general_data = await self._extract_table_data()
                if "identificador" not in general_data:
                    raise Exception("Identification data missing")

                details.update(general_data)

                # Check for mandatory dates with small additional wait if missing
                if not details.get("fecha_de_inicio") or not details.get("fecha_de_conclusión"):
                    await asyncio.sleep(2)
                    details.update(await self._extract_table_data())

                break
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed to extract Tab 1 for {url}: {e}")
                    return details
                await asyncio.sleep(2)

        # 2. Pestaña: Autoridad Gestora (ver=2)
        tab_2_url = self._get_tab_url(url, "2")
        try:
            await self.page.goto(tab_2_url, wait_until="networkidle")
            details.update(await self._extract_table_data())
        except Exception:
            pass

        # Determine if single or multi lot
        lotes_str = details.get("lotes", "Sin lotes")
        has_lotes = lotes_str != "Sin lotes" and lotes_str != "" and "1" not in lotes_str # Simple check
        if lotes_str != "Sin lotes":
            match = re.search(r'(\d+)', lotes_str)
            if match and int(match.group(1)) <= 1:
                has_lotes = False

        if not has_lotes:
            # Pestaña: Bienes (ver=3) - Single lot
            tab_3_url = self._get_tab_url(url, "3")
            try:
                await self.page.goto(tab_3_url, wait_until="networkidle")
                bienes_data = await self._extract_table_data()
                details.update(bienes_data)
                details["tipologia"] = self._extract_tipologia(bienes_data.get("bien", ""))
            except Exception:
                pass
        else:
            # Pestaña: Lotes (ver=3) - Multi-lot
            num_lotes = int(re.search(r'(\d+)', lotes_str).group(1))
            lots_data = []
            for i in range(1, num_lotes + 1):
                lot_url = self._get_lot_url(url, i)
                try:
                    await self.page.goto(lot_url, wait_until="networkidle")
                    lot_info = {"lote_numero": i}
                    lot_table = await self._extract_table_data()
                    lot_info.update(lot_table)
                    lot_info["tipologia"] = self._extract_tipologia(lot_table.get("bien", ""))
                    lots_data.append(lot_info)
                except Exception:
                    pass
            details["lots_data"] = lots_data

        return details

    def _extract_tipologia(self, bien_text):
        """Extracts text inside parenthesis, e.g., 'Inmueble (Vivienda)' -> 'Vivienda'"""
        match = re.search(r'\(([^)]+)\)', bien_text)
        if match:
            return match.group(1).strip()
        return bien_text.replace("Inmueble", "").replace("-", "").strip()

    def _get_tab_url(self, base_url, ver_value):
        parsed = urlparse(base_url)
        query = parse_qs(parsed.query)
        query['ver'] = [ver_value]
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
                if "identificador" in clean_key: clean_key = "identificador"
                if "código_postal" in clean_key: clean_key = "código_postal"
                data[clean_key] = value.strip()
        return data
