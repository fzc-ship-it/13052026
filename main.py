import asyncio
import logging
import argparse
from src.scraper import BOEScraper
from src.database import DatabaseManager
from src.stealth_manager import StealthManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_sync(headless=True, days=0):
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

        # 3. HISTORICAL PHASE (Optional)
        if days > 0:
            from datetime import datetime, timedelta
            today = datetime.now()
            start_date = today - timedelta(days=days)
            date_str = start_date.strftime("%Y-%m-%d")
            today_str = today.strftime("%Y-%m-%d")

            for hist_status in ["PC", "FS"]:
                logger.info(f"--- STEP 4: Scanning HISTORICAL {hist_status} auctions ({days} days) ---")
                await scraper.navigate_to_search()
                await scraper.select_property_type()
                await scraper.select_auction_status(hist_status)
                await scraper.set_date_range("fin", date_str, today_str)
                await scraper.perform_search()
                hist_scan = await scraper.scan_all_ids(hist_status)
                for ident, url in hist_scan.items():
                    if ident not in portal_data:
                        portal_data[ident] = {"url": url, "status": hist_status}

        # 4. DATA INTEGRITY PHASE: Re-scrape incomplete records
        logger.info("--- STEP 5: Checking for incomplete records in DB ---")
        incomplete = db.get_incomplete_auctions()
        logger.info(f"Found {len(incomplete)} incomplete auctions. Adding to scrape list.")

        # 5. NEW AUCTIONS PHASE: Scraping details only for unseen or incomplete IDs
        # portal_data contains current Active/Upcoming/Historical IDs
        # We process those that are not in DB, OR are in the 'incomplete' list

        incomplete_ids = {a['identificador'] for a in incomplete}
        to_process = [ident for ident in portal_data if not db.auction_exists(ident) or ident in incomplete_ids]

        logger.info(f"--- STEP 6: Scraping {len(to_process)} NEW or INCOMPLETE auctions ---")

        for ident in to_process:
            try:
                url = portal_data.get(ident, {}).get("url")
                if not url:
                    # If it's just incomplete but not in the current portal scan, we use its old URL
                    url = next((a['url'] for a in incomplete if a['identificador'] == ident), None)

                if not url: continue

                # Determine status: from current scan, or keep current if just fixing data
                status_info = portal_data.get(ident, {}).get("status")
                if not status_info:
                    # Get current status from DB to preserve it
                    # (Simplified: we use "EJ" as fallback if we don't know)
                    status_info = "EJ"

                details = await scraper.extract_auction_details(url)
                db.save_full_auction(details, status_info)
                logger.info(f"Successfully updated/saved auction {ident}")

                # Global throttling between deep scrapes to avoid ban
                await StealthManager.human_delay(2000, 5000)

            except Exception as e:
                logger.error(f"Error processing auction {ident}: {e}")

        logger.info("SYNC COMPLETED SUCCESSFULLY.")

    finally:
        await scraper.stop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BOE Auction Scraper Sync")
    parser.add_argument("--visible", action="store_true", help="Run browser in visible mode")
    parser.add_argument("--days", type=int, default=0, help="Number of historical days to fetch (for Concluded auctions)")
    args = parser.parse_args()

    asyncio.run(run_sync(headless=not args.visible, days=args.days))
