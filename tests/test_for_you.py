import tempfile
import unittest

from horizonarr.app import App
from horizonarr.config import Config


class FakeIGDB:
    def similar(self, ids):
        return {1: [10, 11, 2], 2: [10, 12]}  # 2 is owned, 10 is suggested twice

    def by_ids(self, ids):
        names = {1: "Owned A", 2: "Owned B", 10: "Ten", 11: "Eleven", 12: "Twelve"}
        return [{"id": i, "name": names[i], "rating_count": 100 - i, "hypes": 0, "platforms": [6], "date": 1,
                 "genres": []} for i in ids if i in names]


class FakeRetroArr:
    def owned_seeds(self):
        return [1, 2], {1, 2}


class ForYouTest(unittest.TestCase):
    def test_ranks_by_mentions_and_skips_owned(self):
        cfg = Config()
        cfg.data_dir = tempfile.mkdtemp()
        cfg.igdb_client_id = cfg.igdb_client_secret = ""
        app = App(cfg)
        app.igdb, app.retroarr = FakeIGDB(), FakeRetroArr()
        app.refresh_for_you()
        ids, _ = app.store.get_list("foryou")
        self.assertEqual(ids[0], 10)
        self.assertNotIn(2, ids)
        self.assertEqual(set(ids), {10, 11, 12})
        self.assertEqual(app.store.get("foryou_because")["10"], "Owned A")


if __name__ == "__main__":
    unittest.main()
