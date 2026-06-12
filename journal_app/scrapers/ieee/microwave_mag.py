# scrapers/ieee/microwave_mag.py — IEEE Microwave Magazine (DrissionPage TOC)
from scrapers.ieee._base import ieee_browser_scrape
from scrapers.base import BaseScraper

class _MICROWAVE_MAGScraper(BaseScraper):
    journal_id = "microwave_mag"
    journal_name = "IEEE Microwave Magazine"
    journal_name_cn = "IEEE 微波杂志"
    publisher = "IEEE"
    journal_type = "ieee"
    code = "microwave_mag"
    punumber = "6668"
    list_url = "https://ieeexplore.ieee.org/xpl/mostRecentIssue.jsp?punumber=6668"

    def scrape(self):
        return ieee_browser_scrape(self)

scraper = _MICROWAVE_MAGScraper()
if __name__ == "__main__":
    scraper.run_standalone()
