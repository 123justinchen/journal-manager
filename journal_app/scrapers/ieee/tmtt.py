# scrapers/ieee/tmtt.py — IEEE Transactions on Microwave Theory and Techniques (DrissionPage TOC)
from scrapers.ieee._base import ieee_browser_scrape
from scrapers.base import BaseScraper

class _TMTTScraper(BaseScraper):
    journal_id = "tmtt"
    journal_name = "IEEE Transactions on Microwave Theory and Techniques"
    journal_name_cn = "IEEE 微波理论与技术汇刊"
    publisher = "IEEE"
    journal_type = "ieee"
    code = "tmtt"
    punumber = "22"
    list_url = "https://ieeexplore.ieee.org/xpl/mostRecentIssue.jsp?punumber=22"

    def scrape(self):
        return ieee_browser_scrape(self)

scraper = _TMTTScraper()
if __name__ == "__main__":
    scraper.run_standalone()
