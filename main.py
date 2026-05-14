import asyncio
import logging
import argparse
from src.scraper import BOEScraper
from src.database import DatabaseManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATUSES = ["PU", "EJ", "PC", "FS"] # Próxima, Activas, Concluidas, Finalizadas por Gestora

async def run_full_scraping():
    db = DatabaseManager()
    scraper = BOEScraper(headless=True)

    try:
        await scraper.start()
        await scraper.navigate_to_search()

        provinces = await scraper.get_provinces()

        for status in STATUSES:
            logger.info(f"--- Processing STATUS: {status} ---")
            for province in provinces:
                logger.info(f"Processing province: {province['name']} for status {status}")

                await scraper.navigate_to_search()
                await scraper.select_province(province['value'])
                await scraper.select_property_type()
                await scraper.select_auction_status(status)
                await scraper.perform_search()

                await process_results(scraper, db, status, province['name'])

    finally:
        await scraper.stop()

async def process_results(scraper, db, status_code, province_name):
    page_count = 1
    while True:
        links = await scraper.get_auction_links()
        if not links:
            logger.info("No results found.")
            break

        logger.info(f"Page {page_count}: Processing {len(links)} auctions.")
        for link in links:
            # Extract ID from URL for quick skip
            try:
                identificador = link.split("idSub=")[1].split("&")[0]
                if db.auction_exists(identificador):
                    logger.info(f"Auction {identificador} already in DB. Skipping.")
                    continue
            except IndexError:
                pass

            details = await scraper.extract_auction_details(link)
            details["provincia_search"] = province_name
            db.save_full_auction(details, status_code)

        if await scraper.has_next_page():
            page_count += 1
            await scraper.go_to_next_page()
        else:
            break

if __name__ == "__main__":
    asyncio.run(run_full_scraping())
