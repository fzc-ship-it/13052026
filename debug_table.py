import asyncio
from src.scraper import BOEScraper
from unidecode import unidecode

async def run():
    scraper = BOEScraper(headless=True)
    await scraper.start()
    # Use the HTML we saved in logs
    with open("logs/final_fail_unknown.html", "r", encoding="utf-8") as f:
        html = f.read()
    await scraper.page.set_content(html)

    data = await scraper._extract_table_data()
    print(f"Extracted keys: {list(data.keys())}")
    print(f"Identificador: {data.get('identificador')}")

    await scraper.stop()

if __name__ == "__main__":
    asyncio.run(run())
