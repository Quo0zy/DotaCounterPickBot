import tempfile
import unittest
import json
from pathlib import Path

from storage import MatchupRepository, normalize_name


class MatchupRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.repository = MatchupRepository(self.db_path)
        self.repository.initialize()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_normalize_name_ignores_case_spaces_and_symbols(self) -> None:
        self.assertEqual(normalize_name("Anti-Mage"), normalize_name("anti mage"))

    def test_upsert_and_get_hero(self) -> None:
        self.repository.upsert_hero(
            "Anti-Mage",
            ["Medusa", "Zeus", "Sniper"],
            ["Axe", "Legion Commander", "Bloodseeker"],
        )

        hero = self.repository.get_hero("anti mage")

        self.assertIsNotNone(hero)
        self.assertEqual(hero.name, "Anti-Mage")
        self.assertEqual(hero.good_against, ["Medusa", "Zeus", "Sniper"])
        self.assertEqual(hero.bad_against, ["Axe", "Legion Commander", "Bloodseeker"])

    def test_upsert_requires_three_good_and_three_bad_matchups(self) -> None:
        with self.assertRaises(ValueError):
            self.repository.upsert_hero("Pudge", ["Sniper"], ["Viper", "Ursa", "Slark"])

    def test_delete_hero_removes_it_from_database(self) -> None:
        self.repository.upsert_hero(
            "Pudge",
            ["Sniper", "Drow Ranger", "Crystal Maiden"],
            ["Viper", "Ursa", "Slark"],
        )

        self.assertTrue(self.repository.delete_hero("pudge"))
        self.assertIsNone(self.repository.get_hero("Pudge"))

    def test_seed_from_file_loads_heroes(self) -> None:
        seed_path = Path(self.temp_dir.name) / "seed.json"
        seed_path.write_text(
            json.dumps(
                {
                    "heroes": [
                        {
                            "name": "Axe",
                            "good_against": ["Phantom Assassin", "Meepo", "Broodmother"],
                            "bad_against": ["Ursa", "Viper", "Venomancer"],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        self.assertEqual(self.repository.seed_from_file(seed_path), 1)
        self.assertEqual(self.repository.hero_count(), 1)
        self.assertEqual(self.repository.get_hero("axe").bad_against, ["Ursa", "Viper", "Venomancer"])


if __name__ == "__main__":
    unittest.main()
