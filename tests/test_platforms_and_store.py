import calendar
import json
import os
import tempfile
import time
import unittest

from horizonarr import platforms
from horizonarr.sources.igdb import IGDB
from horizonarr.store import Store


class PlatformsTest(unittest.TestCase):
    def test_add_choices_ordered_by_priority(self):
        self.assertEqual(platforms.add_choices([167, 6, 130]), [6, 130, 167])
        self.assertEqual(platforms.add_choices([19]), [19])
        self.assertEqual(platforms.add_choices([999999]), [])

    def test_pick_for_add_prefers_pc_then_newest_nintendo(self):
        self.assertEqual(platforms.pick_for_add([167, 6, 130]), 6)
        self.assertEqual(platforms.pick_for_add([130, 508]), 508)
        self.assertEqual(platforms.pick_for_add([19]), 19)

    def test_search_categories(self):
        self.assertEqual(platforms.search_categories([6, 167]), "4000")
        self.assertEqual(platforms.search_categories([130]), "1000")


class IgdbNormaliseTest(unittest.TestCase):
    def test_to_game_keeps_only_dates_in_window(self):
        start, end = calendar.timegm((2026, 1, 1, 0, 0, 0)), calendar.timegm((2026, 2, 1, 0, 0, 0))
        raw = {"id": 1, "name": "X", "summary": "s" * 900, "videos": [{"video_id": "abc"}],
               "release_dates": [{"date": start + 10, "platform": 6}, {"date": end + 99, "platform": 130}],
               "external_games": [{"uid": "123", "external_game_source": 1}]}
        g = IGDB.to_game(raw, {6, 130}, start, end)
        self.assertEqual(g["platforms"], [6])
        self.assertEqual(g["date"], start + 10)
        self.assertEqual(g["steam"], "123")
        self.assertEqual(g["video"], "abc")
        self.assertEqual(len(g["summary"]), 600)


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.store = Store(self.dir)

    def test_games_lists_and_follows(self):
        self.store.put_games([{"id": 5, "name": "A", "date": 1}, {"id": 7, "name": "B", "date": 2}])
        self.store.put_list("recent", [7, 5])
        ids, _ = self.store.get_list("recent")
        self.assertEqual([g["name"] for g in self.store.get_games(ids)], ["B", "A"])
        self.store.follow(5)
        self.store.update_follow(5, last_price=9.99)
        self.assertEqual(self.store.follows()[5]["last_price"], 9.99)
        self.store.follow(5, on=False)
        self.assertEqual(self.store.follows(), {})

    def test_import_old_radar_json(self):
        now = time.time()
        path = os.path.join(self.dir, "radar.json")
        with open(path, "w") as f:
            json.dump({"games": {"1": {"id": 1, "name": "Old", "date": now - 100, "platforms": [6], "hypes": 3,
                                       "genres": [], "avail": None, "avail_checked": int(now)},
                                 "2": {"id": 2, "name": "Soon", "date": now + 100, "platforms": [6], "hypes": 1,
                                       "genres": []}}}, f)
        self.assertEqual(self.store.import_radar_json(path), 2)
        self.assertEqual(self.store.get_list("recent")[0], [1])
        self.assertEqual(self.store.get_list("upcoming")[0], [2])
        self.assertIn(1, self.store.get_avail([1]))
        self.assertEqual(self.store.import_radar_json(path), 0)  # only once


if __name__ == "__main__":
    unittest.main()
