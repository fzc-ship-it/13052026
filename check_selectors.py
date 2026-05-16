import asyncio
from src.scraper import BOEScraper

async def run():
    scraper = BOEScraper(headless=True)
    await scraper.start()
    url = "https://subastas.boe.es/detalleSubasta.php?idSub=SUB-JA-2026-259457"
    await scraper.page.goto(url)

    # Try finding "Fecha de inicio"
    try:
        # Tables might use classtablaFormulario or just tags
        ths = await scraper.page.query_selector_all("th")
        for th in ths:
            text = await th.inner_text()
            if "Fecha de inicio" in text:
                td = await scraper.page.evaluate("(element) => element.nextElementSibling.innerText", th)
                print(f"Found Fecha de inicio via sibling: {td}")
    except Exception as e:
        print(f"Error: {e}")

    await scraper.stop()

if __name__ == "__main__":
    asyncio.run(run())
