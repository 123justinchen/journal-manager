# scrapers/opg/optica.py - Optica

from scrapers.opg._base import OPGBaseScraper

class OpticaScraper(OPGBaseScraper):
    journal_id = "optica"
    journal_name = "Optica"
    journal_name_cn = "Optica"
    code = "optica"
    list_url = "https://opg.optica.org/optica/issue.cfm"

scraper = OpticaScraper()

if __name__ == "__main__":
    scraper.run_standalone()
