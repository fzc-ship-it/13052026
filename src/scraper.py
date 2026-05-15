import asyncio
import logging
import re
import os
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
        self.playwright = None

    async def start(self):
        self.playwright = await async_playwright().start()

        # Use Persistent Context to manage cookies and session
        session_dir = StealthManager.get_session_dir()
        resolution = StealthManager.get_random_resolution()

        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=session_dir,
            headless=self.headless,
            user_agent=StealthManager.get_random_user_agent(),
            viewport=resolution,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox"
            ]
        )

        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        await StealthManager.apply_stealth(self.page)

    async def stop(self):
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()

    async def _safe_goto(self, url, wait_until="networkidle"):
        """Wrapper for goto with diagnostic logs on failure."""
        try:
            await self.page.goto(url, wait_until=wait_until, timeout=60000)
            await StealthManager.random_mouse_move(self.page)
        except Exception as e:
            await self.log_diagnostic(f"goto_fail_{int(asyncio.get_event_loop().time())}")
            logger.error(f"Failed to navigate to {url}: {e}")
            raise

    async def log_diagnostic(self, name):
        """Saves screenshot and HTML for debugging."""
        log_dir = os.path.join(os.getcwd(), "logs")
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        screenshot_path = os.path.join(log_dir, f"{name}.png")
        html_path = os.path.join(log_dir, f"{name}.html")

        await self.page.screenshot(path=screenshot_path)
        content = await self.page.content()
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Diagnostic logs saved: {screenshot_path}")

    async def navigate_to_search(self):
        logger.info(f"Navigating to {self.SEARCH_URL}")
        await self._safe_goto(self.SEARCH_URL)
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
        await StealthManager.human_delay()

    async def select_property_type(self):
        # Click with human movement simulation
        selector = "input[name='dato[3]'][value='I']"
        await self.page.locator(selector).scroll_into_view_if_needed()
        await StealthManager.random_mouse_move(self.page)
        await self.page.click(selector, force=True)
        await StealthManager.human_delay()

    async def select_auction_status(self, status):
        logger.info(f"Selecting status: {status}")
        selector = f"input[name='dato[2]'][value='{status}']"
        await self.page.locator(selector).scroll_into_view_if_needed()
        await StealthManager.random_mouse_move(self.page)
        await self.page.click(selector, force=True)
        await StealthManager.human_delay()

    async def set_date_range(self, date_type, start_date, end_date):
        field_idx = "18" if date_type == "inicio" else "17"
        logger.info(f"Setting {date_type} date range: {start_date} to {end_date}")

        d1 = start_date.split("-")
        d1_fmt = f"{d1[2]}{d1[1]}{d1[0]}" # DDMMYYYY
        d2 = end_date.split("-")
        d2_fmt = f"{d2[2]}{d2[1]}{d2[0]}" # DDMMYYYY

        # Typing with human delays between keys
        await self.page.focus(f"input[name='dato[{field_idx}][0]']")
        await self.page.keyboard.type(d1_fmt, delay=random.randint(50, 150))
        await self.page.focus(f"input[name='dato[{field_idx}][1]']")
        await self.page.keyboard.type(d2_fmt, delay=random.randint(50, 150))

        await StealthManager.human_delay()

    async def clear_date_ranges(self):
        logger.info("Clearing all date ranges...")
        for field_idx in ["17", "18"]:
            await self.page.fill(f"input[name='dato[{field_idx}][0]']", "")
            await self.page.fill(f"input[name='dato[{field_idx}][1]']", "")

    async def perform_search(self):
        logger.info("Performing search...")
        await StealthManager.random_mouse_move(self.page)
        await self.page.click("input[name='accion'][value='Buscar']")
        await self.page.wait_for_load_state("networkidle")

        # Check if 0 results
        content = await self.page.content()
        if "No se han encontrado subastas" in content:
            logger.warning("Zero results found in search.")
            await self.log_diagnostic("zero_results")

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
            await StealthManager.random_mouse_move(self.page)
            await next_button.click()
            await self.page.wait_for_load_state("networkidle")
            await StealthManager.human_delay()

    async def scan_all_ids(self, status):
        all_data = {}
        logger.info(f"Scanning all IDs for status {status}...")
        while True:
            links = await self.get_auction_links()
            if not links:
                # If no links but page loaded, might be a block or truly 0
                await self.log_diagnostic(f"no_links_{status}")

            for link in links:
                try:
                    match = re.search(r'idSub=([^&]+)', link)
                    if match:
                        all_data[match.group(1)] = link
                except Exception:
                    pass

            if await self.has_next_page():
                await self.go_to_next_page()
            else:
                break
        return all_data

    async def extract_auction_details(self, url):
        logger.info(f"Extracting full details from {url}")

        max_retries = 3
        details = {"url": url}

        for attempt in range(max_retries):
            try:
                await self._safe_goto(url)
                await StealthManager.simulate_human_scroll(self.page)

                # Tab 1: Información General
                general_data = await self._extract_table_data()
                if "identificador" not in general_data:
                    logger.warning(f"Attempt {attempt}: Data table not found. Waiting/Pausing...")
                    if not self.headless:
                        print("!!! CAPTCHA OR BLOCK DETECTED !!! Resolve it and then continue in terminal.")
                        await self.page.pause()
                    await asyncio.sleep(5)
                    continue

                details.update(general_data)
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    await self.log_diagnostic(f"extract_fail_{details.get('identificador', 'unknown')}")
                    return details
                await asyncio.sleep(5)

        # Tabs 2, 3...
        for ver in ["2", "3"]:
            try:
                tab_url = self._get_tab_url(url, ver)
                await self._safe_goto(tab_url)
                data = await self._extract_table_data()

                if ver == "3":
                    # Capture the "Bien" text from the H4 header if it's a single lot
                    h4 = await self.page.query_selector("h4")
                    if h4:
                        bien_header = await h4.inner_text()
                        data["bien"] = bien_header
                    details["tipologia"] = self._extract_tipologia(data.get("bien", ""))

                details.update(data)
            except Exception:
                pass

        # Check for lots
        lotes_str = details.get("lotes", "Sin lotes")
        if lotes_str != "Sin lotes" and lotes_str != "":
            match = re.search(r'(\d+)', lotes_str)
            if match and int(match.group(1)) > 1:
                num_lotes = int(match.group(1))
                lots_data = []
                for i in range(1, num_lotes + 1):
                    lot_url = self._get_lot_url(url, i)
                    try:
                        await self._safe_goto(lot_url)
                        lot_info = {"lote_numero": i}
                        lot_table = await self._extract_table_data()
                        lot_info.update(lot_table)
                        lot_info["tipologia"] = self._extract_tipologia(lot_table.get("bien", ""))
                        lots_data.append(lot_info)
                        await StealthManager.human_delay(1000, 3000)
                    except Exception:
                        pass
                details["lots_data"] = lots_data

        return details

    def _extract_tipologia(self, bien_text):
        match = re.search(r'\(([^)]+)\)', bien_text)
        return match.group(1).strip() if match else ""

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
                from unidecode import unidecode
                clean_key = unidecode(key.strip().lower().replace(" ", "_").replace(":", "").replace("\n", ""))

                if "identificador" in clean_key: clean_key = "identificador"
                if "codigo_postal" in clean_key: clean_key = "codigo_postal"
                if "tasacion" in clean_key: clean_key = "tasacion"
                if "puja_minima" in clean_key: clean_key = "puja_minima"
                if "deposito" in clean_key: clean_key = "importe_del_deposito"
                if "valor_subasta" in clean_key: clean_key = "valor_subasta"
                if "cantidad_reclamada" in clean_key: clean_key = "cantidad_reclamada"

                data[clean_key] = value.strip()
        return data
