# scrapers/rss/olt.py - Optics & Laser Technology

from scrapers.elsevier._base import ElsevierBaseScraper


class OltScraper(ElsevierBaseScraper):
    journal_id = "olt"
    journal_name = "Optics & Laser Technology"
    journal_name_cn = "光学与激光技术"
    code = "olt"
    journal_url = "https://www.sciencedirect.com/journal/optics-and-laser-technology"
    list_url = journal_url


scraper = OltScraper()

if __name__ == "__main__":
    scraper.run_standalone()
