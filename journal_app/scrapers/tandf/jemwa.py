# scrapers/tandf/jemwa.py - J. Electromagnetic Waves and Applications

from scrapers.tandf._base import TandFBaseScraper


class JEMWAScraper(TandFBaseScraper):
    journal_id = "jemwa"
    journal_name = "J. Electromagnetic Waves and Applications"
    journal_name_cn = "电磁波与应用杂志"
    code = "jemwa"
    list_url = "https://www.tandfonline.com/toc/tewa20/current"


scraper = JEMWAScraper()

if __name__ == "__main__":
    scraper.run_standalone()
