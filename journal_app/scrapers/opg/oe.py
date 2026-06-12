# scrapers/opg/oe.py - Optics Express

from scrapers.opg._base import OPGBaseScraper

class OeScraper(OPGBaseScraper):
    journal_id = "oe"
    journal_name = "Optics Express"
    journal_name_cn = "光学快报"
    code = "oe"
    list_url = "https://opg.optica.org/oe/issue.cfm"

scraper = OeScraper()

if __name__ == "__main__":
    scraper.run_standalone()
