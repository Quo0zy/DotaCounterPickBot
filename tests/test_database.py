import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from storage import HeroStatsRepository, normalize_name


class HeroStatsRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.repository = HeroStatsRepository(self.db_path)
        self.repository.initialize()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_normalize_name_ignores_case_spaces_and_symbols(self) -> None:
        self.assertEqual(normalize_name("Anti-Mage"), normalize_name("anti mage"))

    def test_upsert_and_get_hero_stats(self) -> None:
        self.repository.upsert_hero("Anti-Mage", 49.25, 8.5)

        hero = self.repository.get_hero("anti mage")

        self.assertIsNotNone(hero)
        self.assertEqual(hero.name, "Anti-Mage")
        self.assertEqual(hero.win_rate, 49.25)
        self.assertEqual(hero.pick_rate, 8.5)
        self.assertEqual(hero.meta_rank, 1)
        self.assertEqual(hero.total_heroes, 1)

    def test_rank_is_calculated_by_win_rate(self) -> None:
        self.repository.upsert_hero("Axe", 51.0, 10.0)
        self.repository.upsert_hero("Bane", 54.0, 3.0)
        self.repository.upsert_hero("Chen", 49.0, 1.0)

        axe = self.repository.get_hero("Axe")

        self.assertEqual(axe.meta_rank, 2)
        self.assertEqual(axe.total_heroes, 3)

    def test_upsert_rejects_invalid_percentage(self) -> None:
        with self.assertRaises(ValueError):
            self.repository.upsert_hero("Pudge", 101, 25)

    def test_delete_hero_removes_it_from_database(self) -> None:
        self.repository.upsert_hero("Pudge", 50.0, 25.0)

        self.assertTrue(self.repository.delete_hero("pudge"))
        self.assertIsNone(self.repository.get_hero("Pudge"))

    def test_seed_from_file_loads_immortal_stats_and_removes_stale_rows(self) -> None:
        self.repository.upsert_hero("Stale Hero", 50.0, 1.0)
        seed_path = Path(self.temp_dir.name) / "seed.json"
        seed_path.write_text(
            json.dumps(
                {
                    "rank": "IMMORTAL",
                    "hero_count": 2,
                    "heroes": [
                        {"name": "Axe", "win_rate": 52.5, "pick_rate": 18.0},
                        {"name": "Bane", "win_rate": 51.0, "pick_rate": 5.0},
                    ],
                }
            ),
            encoding="utf-8",
        )

        self.assertEqual(self.repository.seed_from_file(seed_path), 2)
        self.assertEqual(self.repository.hero_count(), 2)
        self.assertIsNone(self.repository.get_hero("Stale Hero"))
        self.assertEqual(self.repository.get_hero("Axe").win_rate, 52.5)

    def test_seed_rejects_a_different_rank(self) -> None:
        seed_path = Path(self.temp_dir.name) / "seed.json"
        seed_path.write_text(
            json.dumps(
                {
                    "rank": "DIVINE",
                    "heroes": [
                        {"name": "Axe", "win_rate": 52.5, "pick_rate": 18.0}
                    ],
                }
            ),
            encoding="utf-8",
        )

        with self.assertRaises(ValueError):
            self.repository.seed_from_file(seed_path)

    def test_initialize_migrates_the_previous_heroes_table(self) -> None:
        legacy_path = Path(self.temp_dir.name) / "legacy.db"
        with sqlite3.connect(legacy_path) as connection:
            connection.execute(
                """
                CREATE TABLE heroes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    normalized_name TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

        repository = HeroStatsRepository(legacy_path)
        repository.initialize()

        with repository.connect() as connection:
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(heroes)")
            }
        self.assertIn("win_rate", columns)
        self.assertIn("pick_rate", columns)


if __name__ == "__main__":
    unittest.main()
