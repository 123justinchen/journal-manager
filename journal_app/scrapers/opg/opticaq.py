# scrapers/opg/opticaq.py - Optica Quantum

from scrapers.opg._base import OPGBaseScraper

class OpticaqScraper(OPGBaseScraper):
    journal_id = "opticaq"
    journal_name = "Optica Quantum"
    journal_name_cn = "Optica Quantum"
    code = "opticaq"
    list_url = "https://opg.optica.org/opticaq/issue.cfm"

scraper = OpticaqScraper()

if __name__ == "__main__":
    scraper.run_standalone()
