# scrapers/opg/ome.py - Optical Materials Express

from scrapers.opg._base import OPGBaseScraper

class OmeScraper(OPGBaseScraper):
    journal_id = "ome"
    journal_name = "Optical Materials Express"
    journal_name_cn = "光学材料快报"
    code = "ome"
    list_url = "https://opg.optica.org/ome/issue.cfm"

scraper = OmeScraper()

if __name__ == "__main__":
    scraper.run_standalone()
