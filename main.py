import asyncio
import logging
import argparse
from src.scraper import BOEScraper
from src.database import DatabaseManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_sync(headless=True):
    db = DatabaseManager()
    scraper = BOEScraper(headless=headless)

    try:
        await scraper.start()

        # 1. SCAN PHASE: Get all current IDs for Upcoming and Active
        portal_data = {} # {id: {"url": url, "status": status}}

        # Scan Upcoming (PU) - Global search (All provinces)
        logger.info("--- STEP 1: Scanning UPCOMING auctions (Global) ---")
        await scraper.navigate_to_search()
        await scraper.select_property_type()
        await scraper.select_auction_status("PU")
        await scraper.perform_search()
        upcoming_scan = await scraper.scan_all_ids("PU")
        for ident, url in upcoming_scan.items():
            portal_data[ident] = {"url": url, "status": "PU"}

        # Scan Active (EJ) - Global search (All provinces)
        logger.info("--- STEP 2: Scanning ACTIVE auctions (Global) ---")
        await scraper.navigate_to_search()
        await scraper.select_property_type()
        await scraper.select_auction_status("EJ")
        await scraper.perform_search()
        active_scan = await scraper.scan_all_ids("EJ")
        for ident, url in active_scan.items():
            portal_data[ident] = {"url": url, "status": "EJ"}

        # 2. TRANSITION PHASE: Compare with local DB
        logger.info("--- STEP 3: Handling transitions ---")

        # Get all local Upcoming/Active from DB
        local_upcoming = {a['identificador']: a['url'] for a in db.get_auctions_by_status(["Próxima apertura"])}
        local_active = {a['identificador']: a['url'] for a in db.get_auctions_by_status(["Celebrándose"])}

        # Transition: Local Upcoming -> Active if ID now in current_active
        for ident in local_upcoming:
            if ident in active_scan:
                logger.info(f"Transitioning {ident}: Upcoming -> Active")
                db.update_auction_status(ident, "EJ")
            elif ident not in upcoming_scan and ident not in active_scan:
                logger.info(f"Marking {ident} as Concluded (disappeared from lists)")
                db.update_auction_status(ident, "PC")

        # Transition: Local Active -> Concluded if ID no longer in current_active
        for ident in local_active:
            if ident not in active_scan:
                logger.info(f"Transitioning {ident}: Active -> Concluded")
                db.update_auction_status(ident, "PC")

        # 3. NEW AUCTIONS PHASE: Scraping details only for unseen IDs
        new_ids = [ident for ident in portal_data if not db.auction_exists(ident)]

        logger.info(f"--- STEP 4: Scraping {len(new_ids)} NEW auctions ---")

        for ident in new_ids:
            try:
                url = portal_data[ident]["url"]
                status = portal_data[ident]["status"]

                details = await scraper.extract_auction_details(url)
                db.save_full_auction(details, status)
                logger.info(f"Successfully saved new auction {ident}")
            except Exception as e:
                logger.error(f"Error processing new auction {ident}: {e}")

        logger.info("SYNC COMPLETED SUCCESSFULLY.")

    finally:
        await scraper.stop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BOE Auction Scraper Sync")
    parser.add_argument("--visible", action="store_true", help="Run browser in visible mode")
    args = parser.parse_args()

    asyncio.run(run_sync(headless=not args.visible))
