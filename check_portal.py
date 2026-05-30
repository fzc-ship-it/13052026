import asyncio
from src.scraper import BOEScraper

async def run():
    scraper = BOEScraper(headless=True)
    await scraper.start()
    await scraper.navigate_to_search()
    await scraper.select_property_type()
    await scraper.select_auction_status("EJ")
    await scraper.perform_search()
    links = await scraper.get_auction_links()
    if links:
        url = links[0]
        print(f"Opening: {url}")
        await scraper.page.goto(url)
        content = await scraper.page.inner_text("body")
        print(f"Content snippet: {content[:1000]}")
    await scraper.stop()

if __name__ == "__main__":
    asyncio.run(run())
