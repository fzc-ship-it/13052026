import asyncio
import logging
import argparse
from datetime import datetime, timedelta
from src.scraper import BOEScraper
from src.database import DatabaseManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_daily_scraping(days=1):
    db = DatabaseManager()
    scraper = BOEScraper(headless=True)

    # Calculate date range for "daily" scraping
    today = datetime.now()
    yesterday = today - timedelta(days=days)
    date_str = yesterday.strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")

    try:
        await scraper.start()
        await scraper.navigate_to_search()

        provinces = await scraper.get_provinces()

        for province in provinces:
            logger.info(f"Processing province: {province['name']}")

            # 1. Scrape Active Inmuebles starting recently
            await scraper.navigate_to_search()
            await scraper.select_province(province['value'])
            await scraper.select_property_type()
            await scraper.select_auction_status("EJ")
            await scraper.set_date_range("inicio", date_str, today_str)
            await scraper.perform_search()
            await process_results(scraper, db, province['name'])

            # 2. Scrape Finished Inmuebles ending recently
            await scraper.navigate_to_search()
            await scraper.select_province(province['value'])
            await scraper.select_property_type()
            await scraper.select_auction_status("PC")
            await scraper.set_date_range("fin", date_str, today_str)
            await scraper.perform_search()
            await process_results(scraper, db, province['name'])

    finally:
        await scraper.stop()

async def process_results(scraper, db, province_name):
    while True:
        links = await scraper.get_auction_links()
        if not links: break

        for link in links:
            identificador = link.split("idSub=")[1].split("&")[0]
            # Even if it exists, we might want to update it if it's finished now
            # For simplicity in this robust version, we always extract if not known
            # or if we want to ensure we have the latest status/bids.
            if not db.auction_exists(identificador):
                details = await scraper.extract_auction_details(link)
                details["provincia_search"] = province_name
                db.save_auction(details)

        if await scraper.has_next_page():
            await scraper.go_to_next_page()
        else:
            break

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BOE Auction Scraper")
    parser.add_argument("--days", type=int, default=1, help="Number of days to look back")
    args = parser.parse_args()

    asyncio.run(run_daily_scraping(days=args.days))
