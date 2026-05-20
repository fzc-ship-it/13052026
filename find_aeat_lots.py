import asyncio
import re
from src.scraper import BOEScraper

async def main():
    scraper = BOEScraper(headless=True)
    await scraper.start()
    await scraper.navigate_to_search()
    # AEAT is usually "AGENCIA TRIBUTARIA"
    # I'll just search for Active Inmuebles and look for "AGENCIA TRIBUTARIA" in the results
    await scraper.select_property_type()
    await scraper.select_auction_status("EJ")
    await scraper.perform_search()

    links = await scraper.get_auction_links()
    for link in links[:20]:
        await scraper._safe_goto(link)
        content = await scraper.page.content()
        if "AGENCIA TRIBUTARIA" in content and "Lotes" in content:
            # Check if it has lots
            lotes_text = await scraper.page.evaluate("""
                () => {
                    const ths = Array.from(document.querySelectorAll('th'));
                    const lotTh = ths.find(th => th.innerText.includes('Lotes'));
                    return lotTh ? lotTh.nextElementSibling.innerText : '';
                }
            """)
            if "Sin lotes" not in lotes_text and lotes_text.strip() != "":
                print(f"Found AEAT auction with lots: {link}")
                print(f"Lotes text: {lotes_text}")

                # Check Tab 3
                await scraper._safe_goto(scraper._get_tab_url(link, "3"))
                await scraper.page.wait_for_selector("table")
                h4 = await scraper.page.query_selector("h4")
                if h4: print(f"Tab 3 H4: {await h4.inner_text()}")

                # Check Lot 1
                lot_url = scraper._get_lot_url(link, 1)
                await scraper._safe_goto(lot_url)
                h4_lot = await scraper.page.query_selector("h4")
                if h4_lot: print(f"Lot 1 H4: {await h4_lot.inner_text()}")

                ths = await scraper.page.query_selector_all("th")
                for th in ths:
                    k = await th.inner_text()
                    v = await scraper.page.evaluate("el => el.nextElementSibling ? el.nextElementSibling.innerText : ''", th)
                    print(f"  {k}: {v}")
                break

    await scraper.stop()

asyncio.run(main())
