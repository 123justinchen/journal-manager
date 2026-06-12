# scrapers/wiley/iet_map.py - IET Microwaves, Antennas and Propagation

from scrapers.wiley._base import WileyTOCScraper


class IETMAPScraper(WileyTOCScraper):
    journal_id = "iet_map"
    journal_name = "IET Microwaves, Antennas and Propagation"
    journal_name_cn = "IET 微波、天线与传播"
    code = "iet_map"
    toc_id = "17518733"
    toc_domain = "ietresearch.onlinelibrary.wiley.com"
    list_url = "https://ietresearch.onlinelibrary.wiley.com/toc/17518733/current"


scraper = IETMAPScraper()

if __name__ == "__main__":
    scraper.run_standalone()
