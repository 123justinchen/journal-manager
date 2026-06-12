# scrapers/nature/ncomms.py - Nature Communications

from scrapers.nature._base import NatureBaseScraper


class NcommsScraper(NatureBaseScraper):
    journal_id = "ncomms"
    journal_name = "Nature Communications"
    journal_name_cn = "自然通讯"
    code = "ncomms"
    nature_code = "ncomms"
    use_volume_navigation = False
    list_url = "https://www.nature.com/subjects/physical-sciences/ncomms"


scraper = NcommsScraper()

if __name__ == "__main__":
    scraper.run_standalone()
