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

    stats = {"new": 0, "transitions": 0, "re_evaluated": 0}

    try:
        logger.info("Starting INCREMENTAL synchronization engine...")
        await scraper.start()

        # 1. SCAN PHASE: Quick scan of IDs currently on the portal
        portal_data = {}

        logger.info("--- STEP 1: Scanning UPCOMING auctions (Global) ---")
        await scraper.navigate_to_search()
        await scraper.select_property_type()
        await scraper.select_auction_status("PU")
        await scraper.perform_search()
        upcoming_scan, pu_complete = await scraper.scan_all_results("PU")
        portal_data.update(upcoming_scan)

        logger.info("--- STEP 2: Scanning ACTIVE auctions (Global) ---")
        await scraper.navigate_to_search()
        await scraper.select_property_type()
        await scraper.select_auction_status("EJ")
        await scraper.perform_search()
        active_scan, ej_complete = await scraper.scan_all_results("EJ")
        portal_data.update(active_scan)

        # 2. TRANSITION PHASE: Detect status changes for local records
        logger.info("--- STEP 3: Handling transitions and conclusions ---")

        local_upcoming = {a['identificador']: a['url'] for a in db.get_auctions_by_status(["Próxima apertura"])}
        local_active = {a['identificador']: a['url'] for a in db.get_auctions_by_status(["Celebrándose"])}

        # Transition: Upcoming -> Active
        for ident in local_upcoming:
            if ident in active_scan:
                logger.info(f"Transition: {ident} is now ACTIVE")
                db.update_auction_status(ident, "EJ")
                stats["transitions"] += 1
            elif pu_complete and ej_complete and ident not in portal_data:
                # ONLY transition to concluded if we are SURE we scanned everything
                logger.info(f"Transition: {ident} (UPCOMING) DISAPPEARED - Likely concluded or closed")
                url = local_upcoming[ident]
                await handle_concluded_classification(scraper, db, ident, url)
                stats["transitions"] += 1

        # Transition: Active -> Concluded
        for ident in local_active:
            if ej_complete and ident not in active_scan:
                # ONLY transition to concluded if we are SURE the active scan was full
                logger.info(f"Transition: {ident} (ACTIVE) is now CONCLUDED")
                url = local_active[ident]
                await handle_concluded_classification(scraper, db, ident, url)
                stats["transitions"] += 1

        # 3. HISTORICAL PHASE (Optional): Fetch recently closed auctions
        if days > 0:
            from datetime import datetime, timedelta
            today = datetime.now()
            start_date = today - timedelta(days=days)
            date_str = start_date.strftime("%Y-%m-%d")
            today_str = today.strftime("%Y-%m-%d")

            # Pre-fetch candidates for re-evaluation to avoid N+1 queries in loop
            local_concluded_ids = {a['identificador'] for a in db.get_auctions_by_status(["Concluida", "Finalizada"])}

            for hist_status in ["PC", "FS"]:
                logger.info(f"--- STEP 4: Scanning HISTORICAL {hist_status} auctions ({days} days) ---")
                await scraper.navigate_to_search()
                await scraper.select_property_type()
                await scraper.select_auction_status(hist_status)
                await scraper.set_date_range("fin", date_str, today_str)
                await scraper.perform_search()
                hist_scan, hist_complete = await scraper.scan_all_results(hist_status)

                for ident, data in hist_scan.items():
                    if not db.auction_exists(ident):
                        portal_data[ident] = {"url": data["url"], "status": hist_status}
                    elif ident in local_concluded_ids:
                        # Re-evaluate recently concluded auctions if they are not yet Remate
                        logger.info(f"Re-evaluating historical auction {ident} for Remate classification")
                        await handle_concluded_classification(scraper, db, ident, data["url"])
                        stats["re_evaluated"] += 1
                        # Remove from local list to avoid double evaluation in same run if seen again
                        local_concluded_ids.remove(ident)

        # 4. DATA INTEGRITY PHASE: Identify incomplete records
        logger.info("--- STEP 5: Checking for incomplete records in DB ---")
        incomplete = db.get_incomplete_auctions()
        logger.info(f"Found {len(incomplete)} incomplete auctions.")

        # 5. EXTRACTION PHASE: Scrape details only for new or incomplete IDs
        incomplete_ids = {a['identificador'] for a in incomplete}

        # We process:
        # 1. New auctions found in portal scan
        # 2. Auctions we know are incomplete
        to_process_ids = list(set([ident for ident in portal_data if not db.auction_exists(ident)] + list(incomplete_ids)))

        logger.info(f"--- STEP 6: Deep Scraping {len(to_process_ids)} auctions ---")

        processed_count = 0
        for ident in to_process_ids:
            try:
                item = portal_data.get(ident, {})
                url = item.get("url")

                if not url:
                    # Fallback for incomplete auctions not in current scan
                    url = next((a['url'] for a in incomplete if a['identificador'] == ident), None)

                if not url: continue

                # Get status from current scan, or preserve local status if re-scraping incomplete
                status_info = item.get("status_code")
                if not status_info:
                    # Try to get existing status from DB if it's just an incomplete record re-scrape
                    local_info = next((a for a in db.get_auctions_by_status(["Próxima apertura", "Celebrándose", "Concluida", "Finalizada", "Cesión de remate"]) if a['identificador'] == ident), None)
                    if local_info:
                        # Map descriptive status back to code for save_full_auction
                        rev_map = {v: k for k, v in db.STATUS_MAPPING.items()}
                        status_info = rev_map.get(local_info["estado_proceso"], "EJ")
                    else:
                        status_info = "EJ"

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

        logger.info(f"SYNC COMPLETED.")
        # Final counts in DB
        counts = db.get_status_counts()
        logger.info(f"SYNC COMPLETED SUCCESSFULLY.")
        logger.info(f"--- SUMMARY OF CHANGES IN THIS RUN ---")
        logger.info(f" - New auctions added: {processed_count}")
        logger.info(f" - Status transitions detected: {stats['transitions']}")
        logger.info(f" - Records re-evaluated/repaired: {stats['re_evaluated']}")
        logger.info(f"--- DATABASE TOTALS (All runs combined) ---")
        for status, count in counts.items():
            logger.info(f" - {status}: {count}")

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
