# scrapers/opg/ao.py - Applied Optics

from scrapers.opg._base import OPGBaseScraper

class AoScraper(OPGBaseScraper):
    journal_id = "ao"
    journal_name = "Applied Optics"
    journal_name_cn = "应用光学"
    code = "ao"
    list_url = "https://opg.optica.org/ao/issue.cfm"

scraper = AoScraper()

if __name__ == "__main__":
    scraper.run_standalone()
