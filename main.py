import asyncio
import logging
import argparse
from src.scraper import BOEScraper
from src.database import DatabaseManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_sync():
    db = DatabaseManager()
    scraper = BOEScraper(headless=True)

    try:
        await scraper.start()

        # 1. SCAN PHASE: Get all current IDs for Upcoming and Active
        current_upcoming = set()
        current_active = set()

        provinces = await scraper.get_provinces()

        # Scan Upcoming (PU)
        logger.info("--- STEP 1: Scanning UPCOMING auctions ---")
        for province in provinces:
            await scraper.navigate_to_search()
            await scraper.select_province(province['value'])
            await scraper.select_property_type()
            await scraper.select_auction_status("PU")
            await scraper.perform_search()
            ids = await scraper.scan_all_ids("PU")
            current_upcoming.update(ids)

        # Scan Active (EJ)
        logger.info("--- STEP 2: Scanning ACTIVE auctions ---")
        for province in provinces:
            await scraper.navigate_to_search()
            await scraper.select_province(province['value'])
            await scraper.select_property_type()
            await scraper.select_auction_status("EJ")
            await scraper.perform_search()
            ids = await scraper.scan_all_ids("EJ")
            current_active.update(ids)

        # 2. TRANSITION PHASE: Compare with local DB
        logger.info("--- STEP 3: Handling transitions ---")

        # Get all local Upcoming/Active from DB
        local_upcoming = {a['identificador']: a['url'] for a in db.get_auctions_by_status(["Próxima apertura"])}
        local_active = {a['identificador']: a['url'] for a in db.get_auctions_by_status(["Celebrándose"])}

        # Transition: Local Upcoming -> Active if ID now in current_active
        for ident in local_upcoming:
            if ident in current_active:
                logger.info(f"Transitioning {ident}: Upcoming -> Active")
                db.update_auction_status(ident, "EJ")
            elif ident not in current_upcoming and ident not in current_active:
                # If it disappeared from both, mark as Concluded (safe assumption)
                logger.info(f"Marking {ident} as Concluded (disappeared from lists)")
                db.update_auction_status(ident, "PC")

        # Transition: Local Active -> Concluded if ID no longer in current_active
        for ident in local_active:
            if ident not in current_active:
                logger.info(f"Transitioning {ident}: Active -> Concluded")
                db.update_auction_status(ident, "PC")

        # 3. NEW AUCTIONS PHASE: Scraping details only for unseen IDs
        all_portal_ids = current_upcoming.union(current_active)
        new_ids = []

        # Find which IDs from portal are NOT in our DB at all
        for ident in all_portal_ids:
            if not db.auction_exists(ident):
                new_ids.append(ident)

        logger.info(f"--- STEP 4: Scraping {len(new_ids)} NEW auctions ---")

        # Since we only have IDs, we need to find their URLs.
        # Re-running search to get links is easiest or we could have stored them in STEP 1/2.
        # Let's optimize: perform search by ID if possible, or just re-scrape provinces only for new IDs.
        # Most efficient: perform search by ID for each new ID.

        for ident in new_ids:
            try:
                await scraper.navigate_to_search()
                # Use the ID search field (dato[14])
                await scraper.page.fill("input[name='dato[14]']", ident)
                await scraper.perform_search()

                links = await scraper.get_auction_links()
                if links:
                    details = await scraper.extract_auction_details(links[0])
                    # Determine status
                    status = "PU" if ident in current_upcoming else "EJ"
                    db.save_full_auction(details, status)
                    logger.info(f"Successfully saved new auction {ident}")
            except Exception as e:
                logger.error(f"Error processing new auction {ident}: {e}")

        logger.info("SYNC COMPLETED SUCCESSFULLY.")

    finally:
        await scraper.stop()

if __name__ == "__main__":
    asyncio.run(run_sync())
