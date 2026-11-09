"""Prowlarr: is there a release of this game on your indexers?"""
import urllib.parse

from .. import net
from ..matching import best_release
from ..platforms import search_categories


class Prowlarr:
    def __init__(self, url, key):
        self.url, self.key = url, key

    def availability(self, game):
        q = urllib.parse.urlencode({"query": game["name"], "type": "search",
                                    "categories": search_categories(game["platforms"]), "limit": 100})
        results = net.request(f"{self.url}/api/v1/search?{q}", headers={"X-Api-Key": self.key}, timeout=150)
        return best_release(game["name"], results if isinstance(results, list) else [])
