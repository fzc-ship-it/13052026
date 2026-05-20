import asyncio
import logging
import re
import os
import random
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from unidecode import unidecode
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
        self.page = None

    async def start(self):
        self.playwright = await async_playwright().start()

        # Absolute cleaning of previous sessions
        StealthManager.clean_temp_data()

        # Launch non-persistent browser for 100% fresh identity
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--window-position=0,0",
                "--ignore-certificate-errors",
                "--disable-extensions"
            ]
        )

        resolution = StealthManager.get_random_resolution()
        self.context = await self.browser.new_context(
            user_agent=StealthManager.get_random_user_agent(),
            viewport=resolution,
            locale="es-ES",
            timezone_id="Europe/Madrid"
        )

        self.page = await self.context.new_page()
        await StealthManager.apply_stealth(self.page)

    async def stop(self):
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        StealthManager.clean_temp_data()

    async def _safe_goto(self, url, wait_until="domcontentloaded"):
        """Wrapper for goto with diagnostic logs and standardized domcontentloaded."""
        try:
            await self.page.goto(url, wait_until=wait_until, timeout=45000)
            # Short randomized delay after load to look human
            await asyncio.sleep(random.uniform(0.5, 1.5))
        except Exception as e:
            logger.error(f"Failed to navigate to {url}: {e}")
            await self.log_diagnostic(f"goto_fail_{int(asyncio.get_event_loop().time())}")
            raise

    async def log_diagnostic(self, name):
        """Saves screenshot and HTML for debugging."""
        log_dir = os.path.join(os.getcwd(), "logs")
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        try:
            screenshot_path = os.path.join(log_dir, f"{name}.png")
            html_path = os.path.join(log_dir, f"{name}.html")
            await self.page.screenshot(path=screenshot_path)
            content = await self.page.content()
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"Diagnostic logs saved: {screenshot_path}")
        except Exception:
            pass

    async def navigate_to_search(self):
        logger.info(f"Navigating to {self.SEARCH_URL}")
        await self._safe_goto(self.SEARCH_URL)

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
        selector = "input[name='dato[3]'][value='I']"
        await self.page.locator(selector).scroll_into_view_if_needed()
        await self.page.click(selector, force=True)
        await StealthManager.human_delay(500, 1500)

    async def select_auction_status(self, status):
        logger.info(f"Selecting status: {status}")
        selector = f"input[name='dato[2]'][value='{status}']"
        await self.page.locator(selector).scroll_into_view_if_needed()
        await self.page.click(selector, force=True)
        await StealthManager.human_delay(500, 1500)

    async def set_date_range(self, date_type, start_date, end_date):
        field_idx = "18" if date_type == "inicio" else "17"
        logger.info(f"Setting {date_type} date range: {start_date} to {end_date}")

        d1 = start_date.split("-")
        d1_fmt = f"{d1[2]}{d1[1]}{d1[0]}" # DDMMYYYY
        d2 = end_date.split("-")
        d2_fmt = f"{d2[2]}{d2[1]}{d2[0]}" # DDMMYYYY

        await self.page.focus(f"input[name='dato[{field_idx}][0]']")
        await self.page.keyboard.type(d1_fmt, delay=random.randint(40, 100))
        await self.page.focus(f"input[name='dato[{field_idx}][1]']")
        await self.page.keyboard.type(d2_fmt, delay=random.randint(40, 100))
        await StealthManager.human_delay(800, 1800)

    async def perform_search(self):
        logger.info("Performing search...")
        await self.page.click("input[name='accion'][value='Buscar']")
        await self.page.wait_for_load_state("domcontentloaded")
        await StealthManager.human_delay(1000, 2500)

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
        # The BOE portal uses text 'siguiente' for pagination links
        next_button = await self.page.query_selector("a:has-text('siguiente')")
        return next_button is not None

    async def go_to_next_page(self):
        next_button = await self.page.query_selector("a:has-text('siguiente')")
        if next_button:
            logger.info("Navigating to next page of results...")
            await next_button.click()
            await self.page.wait_for_load_state("domcontentloaded")
            await StealthManager.human_delay(1000, 2500)

    async def scan_all_ids(self, status):
        all_data = {}
        logger.info(f"Scanning all IDs for status {status}...")
        while True:
            links = await self.get_auction_links()
            for link in links:
                match = re.search(r'idSub=([^&]+)', link)
                if match:
                    all_data[match.group(1)] = link

            if await self.has_next_page():
                await self.go_to_next_page()
            else:
                break
        return all_data

    async def extract_auction_details(self, url):
        """Comprehensive extraction with strict verification of 13 key fields."""
        logger.info(f"Extracting full details from {url}")

        max_retries = 3
        details = {"url": url}

        # Verification requirements for the 13 critical fields
        # Note: 'autoridad_gestora_codigo' is mapped as 'codigo' in extraction
        critical_fields = [
            "identificador", "fecha_de_inicio", "fecha_de_conclusion",
            "tasacion", "puja_minima", "importe_del_deposito", "cantidad_reclamada",
            "codigo", "telefono", "correo_electronico",
            "descripcion", "direccion"
        ]

        data_selector = "div#idBloqueDatos1 table, table.tablaFormulario, table"

        for attempt in range(max_retries):
            try:
                # Reset details for this attempt
                current_attempt_data = {"url": url}

                # Tab 1: Información General
                await self._safe_goto(url, wait_until="domcontentloaded")
                await self.page.wait_for_selector(data_selector, timeout=15000)
                tab1_data = await self._extract_table_data()
                current_attempt_data.update(tab1_data)

                # Verify Tab 1 critical fields
                t1_critical = ["identificador", "fecha_de_inicio", "fecha_de_conclusion", "valor_subasta"]
                if not any(current_attempt_data.get(f) for f in t1_critical):
                    logger.warning(f"Tab 1 empty on attempt {attempt}. Retrying...")
                    await asyncio.sleep(2)
                    continue

                # Tab 2: Autoridad Gestora
                await StealthManager.human_delay(1200, 2500)
                await self._safe_goto(self._get_tab_url(url, "2"), wait_until="domcontentloaded")
                await self.page.wait_for_selector(data_selector, timeout=10000)
                current_attempt_data.update(await self._extract_table_data())

                # Tab 3: Bienes / Lotes
                await StealthManager.human_delay(1200, 2500)
                await self._safe_goto(self._get_tab_url(url, "3"), wait_until="domcontentloaded")
                await self.page.wait_for_selector(data_selector, timeout=10000)

                lotes_str = current_attempt_data.get("lotes", "Sin lotes")
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
                    current_attempt_data["tipologia"] = self._extract_tipologia(bienes_data.get("bien", ""))
                    current_attempt_data.update(bienes_data)
                else:
                    # Multi lot
                    num_lotes = int(re.search(r'(\d+)', lotes_str).group(1))
                    lots_data = []
                    for i in range(1, num_lotes + 1):
                        lot_url = self._get_lot_url(url, i)
                        await StealthManager.human_delay(800, 1500)
                        await self._safe_goto(lot_url, wait_until="domcontentloaded")
                        await self.page.wait_for_selector(data_selector, timeout=10000)

                        lot_header = await self.page.query_selector("h4")
                        lot_header_text = await lot_header.inner_text() if lot_header else ""

                        lot_table = await self._extract_table_data()
                        lot_info = {"lote_numero": i}
                        lot_info.update(lot_table)

                        # Ensure 'bien' is captured from the H4 header if not in table
                        if not lot_info.get("bien"):
                            lot_info["bien"] = lot_header_text

                        lot_info["tipologia"] = self._extract_tipologia(lot_info.get("bien", ""))
                        lots_data.append(lot_info)
                    current_attempt_data["lots_data"] = lots_data

                # FINAL VALIDATION: Check if we have the critical data
                # We are flexible with some fields like email if not present, but
                # description and dates are mandatory for a "complete" record.
                if current_attempt_data.get("descripcion") or (has_lotes and current_attempt_data.get("lots_data")):
                    return current_attempt_data
                else:
                    logger.warning(f"Incomplete extraction on attempt {attempt}. Retrying...")
                    await asyncio.sleep(2)

            except Exception as e:
                logger.error(f"Attempt {attempt} failed for {url}: {e}")
                if attempt == max_retries - 1:
                    await self.log_diagnostic(f"fail_{current_attempt_data.get('identificador', 'unknown')}")
                    return current_attempt_data
                await asyncio.sleep(3)

        return details


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
        try:
            ths = await self.page.query_selector_all("th")
            for th in ths:
                try:
                    key_raw = await th.inner_text()
                    if not key_raw: continue

                    value = await self.page.evaluate("(element) => element.nextElementSibling ? element.nextElementSibling.innerText : ''", th)

                    clean_key = unidecode(key_raw.strip().lower().replace(" ", "_").replace(":", "").replace("\n", ""))

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
                        "inicio_de_la_subasta": "fecha_de_inicio",
                        "conclusion_de_la_subasta": "fecha_de_conclusion",
                        "codigo": "codigo",
                        "telefono": "telefono",
                        "correo_electronico": "correo_electronico",
                        "descripcion": "descripcion",
                        "direccion": "direccion",
                        "vivienda_habitual": "vivienda_habitual",
                        "situacion_posesoria": "situacion_posesoria",
                        "bien": "bien",
                        "tipo_de_bien": "bien",
                        "clase_de_bien": "bien"
                    }

                    for k, v in mapping.items():
                        if k in clean_key:
                            clean_key = v
                            break

                    if value:
                        data[clean_key] = value.strip()
                except Exception:
                    continue
        except Exception:
            pass
        return data

    def _extract_tipologia(self, bien_text):
        if not bien_text: return ""
        # Common pattern: "Inmueble (Vivienda)" -> "Vivienda"
        match = re.search(r'\(([^)]+)\)', bien_text)
        if match:
            return match.group(1).strip()

        # Fallback for patterns like "Bien 1 - Inmueble Vivienda" or just "Vivienda"
        # If there are no parens, we take everything after the last "-" or just the whole string if short
        if " - " in bien_text:
            parts = bien_text.split(" - ")
            candidate = parts[-1].strip()
            return candidate

        return bien_text.strip()
