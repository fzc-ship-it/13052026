import asyncio
from src.scraper import BOEScraper

async def main():
    scraper = BOEScraper(headless=True)
    await scraper.start()
    for i in [1, 2]:
        url = f"https://subastas.boe.es/detalleSubasta.php?idSub=SUB-JA-2026-258782&ver=3&idLote={i}"
        await scraper._safe_goto(url)
        h4s = await scraper.page.query_selector_all("h4")
        print(f"--- Lot {i} ---")
        for j, h4 in enumerate(h4s):
            print(f"H4[{j}]: {await h4.inner_text()}")
    await scraper.stop()

asyncio.run(main())
