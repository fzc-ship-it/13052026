import asyncio
import logging
import argparse
import os
from src.scraper import BOEScraper
from src.database import DatabaseManager
from src.stealth_manager import StealthManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def handle_concluded_classification(scraper, db, ident, url):
    """Checks if a concluded auction should be 'Cesión de remate'."""
    try:
        portal_status = await scraper.get_portal_status_text(url)
        if "portal" in portal_status.lower():
            # Concluida por el portal - stays as PC
            db.update_auction_status(ident, "PC")
            logger.info(f"Auction {ident} concluded by portal.")
        else:
            no_bids = await scraper.check_no_bids(url)
            if no_bids:
                db.update_auction_status(ident, "CR") # Cesión de remate
                logger.info(f"Auction {ident} classified as Cesión de Remate (no bids).")
            else:
                db.update_auction_status(ident, "PC")
                logger.info(f"Auction {ident} concluded with bids.")
    except Exception as e:
        logger.error(f"Error classifying concluded auction {ident}: {e}")
        db.update_auction_status(ident, "PC")

async def run_sync(headless=True, days=0):
    db = DatabaseManager()
    scraper = BOEScraper(headless=headless)

    try:
        logger.info("Starting synchronization engine...")
        await scraper.start()

        # 1. SCAN PHASE: Get all current IDs for Upcoming and Active
        portal_data = {} # {id: {"url": url, "status": status}}

        # Scan Upcoming (PU) - Global search
        logger.info("--- STEP 1: Scanning UPCOMING auctions (Global) ---")
        await scraper.navigate_to_search()
        await scraper.select_property_type()
        await scraper.select_auction_status("PU")
        await scraper.perform_search()
        upcoming_scan = await scraper.scan_all_ids("PU")
        for ident, url in upcoming_scan.items():
            portal_data[ident] = {"url": url, "status": "PU"}

        # Scan Active (EJ) - Global search
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

        # Transition: Local Upcoming -> Active or Concluded
        for ident in local_upcoming:
            if ident in active_scan:
                logger.info(f"Transitioning {ident}: Upcoming -> Active")
                db.update_auction_status(ident, "EJ")
            elif ident not in upcoming_scan and ident not in active_scan:
                logger.info(f"Transitioning {ident}: Upcoming -> Concluded (Checking Remate)")
                url = local_upcoming[ident]
                await handle_concluded_classification(scraper, db, ident, url)

        # Transition: Local Active -> Concluded
        for ident in local_active:
            if ident not in active_scan:
                logger.info(f"Transitioning {ident}: Active -> Concluded (Checking Remate)")
                url = local_active[ident]
                await handle_concluded_classification(scraper, db, ident, url)

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
                    if not db.auction_exists(ident):
                        portal_data[ident] = {"url": url, "status": hist_status}
                    else:
                        # If exists, we might still want to check if it's "Cesión de remate"
                        # Only if it's currently listed as PC/FS in DB
                        pass

        # 4. DATA INTEGRITY PHASE: Identify incomplete records
        logger.info("--- STEP 5: Checking for incomplete records in DB ---")
        incomplete = db.get_incomplete_auctions()
        logger.info(f"Found {len(incomplete)} incomplete auctions.")

        # 5. EXTRACTION PHASE: Scrape details only for new or incomplete IDs
        incomplete_ids = {a['identificador'] for a in incomplete}
        to_process_ids = [ident for ident in portal_data if not db.auction_exists(ident) or ident in incomplete_ids]

        logger.info(f"--- STEP 6: Deep Scraping {len(to_process_ids)} auctions ---")

        processed_count = 0
        for ident in to_process_ids:
            try:
                url = portal_data.get(ident, {}).get("url")
                if not url:
                    url = next((a['url'] for a in incomplete if a['identificador'] == ident), None)

                if not url: continue

                status_info = portal_data.get(ident, {}).get("status", "EJ")

                details = await scraper.extract_auction_details(url)
                if details.get("identificador"):
                    # If scraping a NEW concluded auction, check for Remate classification
                    if status_info in ["PC", "FS"]:
                        portal_status = await scraper.get_portal_status_text(url)
                        if "portal" not in portal_status.lower():
                            no_bids = await scraper.check_no_bids(url)
                            if no_bids:
                                status_info = "CR"

                    db.save_full_auction(details, status_info)
                    logger.info(f"Successfully processed auction {ident} as {status_info}")
                    processed_count += 1
                else:
                    logger.warning(f"Skipping auction {ident}: Failed to extract minimal identity data.")

                # Global throttling between deep scrapes
                await StealthManager.human_delay(2000, 5000)

            except Exception as e:
                logger.error(f"Error processing auction {ident}: {e}")

        logger.info(f"SYNC COMPLETED. Total processed: {processed_count}")

    except Exception as e:
        logger.critical(f"Sync failed due to critical error: {e}")
    finally:
        await scraper.stop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BOE Auction Scraper Sync Engine")
    parser.add_argument("--visible", action="store_true", help="Run browser in visible mode")
    parser.add_argument("--days", type=int, default=0, help="Number of historical days to fetch")
    args = parser.parse_args()

    # Ensure logs directory exists
    os.makedirs("logs", exist_ok=True)

    asyncio.run(run_sync(headless=not args.visible, days=args.days))
