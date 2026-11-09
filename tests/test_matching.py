import unittest

from horizonarr.matching import best_release, clean, same_title, similarity


class MatchingTest(unittest.TestCase):
    def test_clean_strips_scene_noise(self):
        self.assertEqual(clean("Phantom.Blade.Zero-v301524.[FitGirl Repack] (MULTi12)"), "phantom blade zero")
        self.assertEqual(clean("Ratchet & Clank"), "ratchet and clank")

    def test_similarity_ignores_trailing_tags(self):
        self.assertGreater(similarity("Hades II", "Hades II v1.0.2 [GOG] (Windows)"), 0.9)
        self.assertLess(similarity("Hades II", "Hollow Knight Silksong"), 0.5)

    def test_best_release_needs_seeders_and_title(self):
        releases = [
            {"title": "Hades II [FitGirl Repack]", "seeders": 120, "size": 5_000_000_000, "indexer": "a"},
            {"title": "Hades II-RUNE", "seeders": 1, "size": 9_000_000_000, "indexer": "b"},
            {"title": "Hades OST FLAC", "seeders": 300, "size": 1_000_000_000, "indexer": "c"},
        ]
        best = best_release("Hades II", releases)
        self.assertEqual(best["indexer"], "a")
        self.assertIsNone(best_release("Hades II", [releases[1]]))

    def test_same_title(self):
        self.assertTrue(same_title("Dune", "Dune"))
        self.assertTrue(same_title("Grand Theft Auto VI", "Grand Theft Auto VI Deluxe"))
        self.assertFalse(same_title("Mario", "Mario Kart 8"))


if __name__ == "__main__":
    unittest.main()
