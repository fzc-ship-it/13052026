import asyncio
import logging
import re
import os
import random
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
        """Comprehensive extraction with strict verification and retries for missing fields."""
        logger.info(f"Extracting full details from {url}")

        max_retries = 3
        details = {"url": url}

        # We define required fields to trigger a retry if they are missing
        critical_fields = ["identificador"] # Relaxed for now, will check dates later
        data_selector = "div#idBloqueDatos1 table, table.tablaFormulario, table"

        for attempt in range(max_retries):
            # Reset details each retry to ensure fresh load
            details = {"url": url}

            try:
                # Tab 1: Información General
                await self._safe_goto(url)
                await self.page.wait_for_selector(data_selector, timeout=15000)
                details.update(await self._extract_table_data())

                # Check for critical fields in Tab 1
                missing_critical = [f for f in critical_fields if not details.get(f)]
                if missing_critical:
                    logger.warning(f"Attempt {attempt}: Missing critical fields {missing_critical}. Retrying...")
                    await asyncio.sleep(3)
                    continue

                # Tab 2: Autoridad Gestora
                await StealthManager.human_delay(1500, 3500)
                await self._safe_goto(self._get_tab_url(url, "2"))
                await self.page.wait_for_selector(data_selector, timeout=10000)
                gestora_data = await self._extract_table_data()
                details.update(gestora_data)

                # Tab 3: Bienes / Lotes
                await StealthManager.human_delay(1500, 3500)
                await self._safe_goto(self._get_tab_url(url, "3"))
                # In Tab 3, it might be a list of lots or direct Bien data
                await self.page.wait_for_selector(data_selector, timeout=10000)

                lotes_str = details.get("lotes", "Sin lotes")
                has_lotes = False
                if lotes_str != "Sin lotes" and lotes_str != "":
                    match = re.search(r'(\d+)', lotes_str)
                    if match and int(match.group(1)) > 1:
                        has_lotes = True

                if not has_lotes:
                    # Single lot
                    h4 = await self.page.query_selector("h4")
                    bienes_data = await self._extract_table_data()
                    if h4:
                        bienes_data["bien"] = await h4.inner_text()
                    details["tipologia"] = self._extract_tipologia(bienes_data.get("bien", ""))
                    details.update(bienes_data)

                    if not details.get("descripcion"):
                         logger.warning(f"Attempt {attempt}: Property description empty. Retrying...")
                         await asyncio.sleep(5)
                         continue
                else:
                    # Multi lot
                    num_lotes = int(re.search(r'(\d+)', lotes_str).group(1))
                    lots_data = []
                    for i in range(1, num_lotes + 1):
                        lot_url = self._get_lot_url(url, i)
                        await StealthManager.human_delay(1000, 2000)
                        await self._safe_goto(lot_url)
                        await self.page.wait_for_selector("table.tablaFormulario", timeout=10000)
                        lot_info = {"lote_numero": i}
                        lot_table = await self._extract_table_data()
                        lot_info.update(lot_table)
                        lot_info["tipologia"] = self._extract_tipologia(lot_table.get("bien", ""))
                        lots_data.append(lot_info)
                    details["lots_data"] = lots_data

                # If we reach here, we successfully extracted all stages
                return details

            except Exception as e:
                logger.error(f"Attempt {attempt} failed for {url}: {e}")
                if attempt == max_retries - 1:
                    await self.log_diagnostic(f"final_fail_{details.get('identificador', 'unknown')}")
                    return details
                await asyncio.sleep(5)

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
        # Strategy: find all THs and their next siblings
        ths = await self.page.query_selector_all("th")
        for th in ths:
            try:
                key_raw = await th.inner_text()
                if not key_raw: continue

                # Get the value from the next sibling TD
                value = await self.page.evaluate("(element) => element.nextElementSibling ? element.nextElementSibling.innerText : ''", th)

                from unidecode import unidecode
                clean_key = unidecode(key_raw.strip().lower().replace(" ", "_").replace(":", "").replace("\n", ""))

                # Standardization mapping
                mapping = {
                    "identificador": "identificador",
                    "codigo_postal": "codigo_postal",
                    "tasacion": "tasacion",
                    "puja_minima": "puja_minima",
                    "deposito": "importe_del_deposito",
                    "valor_subasta": "valor_subasta",
                    "cantidad_reclamada": "cantidad_reclamada",
                    "fecha_de_inicio": "fecha_de_inicio",
                    "fecha_de_conclusion": "fecha_de_conclusion",
                    "codigo": "codigo",
                    "telefono": "telefono",
                    "correo_electronico": "correo_electronico",
                    "descripcion": "descripcion",
                    "direccion": "direccion",
                    "vivienda_habitual": "vivienda_habitual",
                    "situacion_posesoria": "situacion_posesoria"
                }

                for k, v in mapping.items():
                    if k in clean_key:
                        clean_key = v
                        break

                if value:
                    data[clean_key] = value.strip()
            except Exception:
                continue
        return data
