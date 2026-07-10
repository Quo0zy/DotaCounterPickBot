import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HeroStats:
    name: str
    win_rate: float
    pick_rate: float
    meta_rank: int
    total_heroes: int


def normalize_name(value: str) -> str:
    value = value.casefold().replace("ё", "е").strip()
    return "".join(char for char in value if char.isalnum())


class HeroStatsRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS heroes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    normalized_name TEXT NOT NULL UNIQUE,
                    win_rate REAL,
                    pick_rate REAL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._ensure_column(connection, "heroes", "win_rate", "REAL")
            self._ensure_column(connection, "heroes", "pick_rate", "REAL")

    def upsert_hero(self, name: str, win_rate: float, pick_rate: float) -> None:
        clean_name, normalized_name, win_rate, pick_rate = self._validate_hero(
            name, win_rate, pick_rate
        )
        with self.connect() as connection:
            self._upsert_hero(
                connection,
                clean_name,
                normalized_name,
                win_rate,
                pick_rate,
            )

    def get_hero(self, name: str) -> HeroStats | None:
        normalized_name = normalize_name(name)
        if not normalized_name:
            return None

        with self.connect() as connection:
            row = connection.execute(
                """
                WITH ranked AS (
                    SELECT
                        name,
                        normalized_name,
                        win_rate,
                        pick_rate,
                        RANK() OVER (ORDER BY win_rate DESC) AS meta_rank,
                        COUNT(*) OVER () AS total_heroes
                    FROM heroes
                    WHERE win_rate IS NOT NULL AND pick_rate IS NOT NULL
                )
                SELECT name, win_rate, pick_rate, meta_rank, total_heroes
                FROM ranked
                WHERE normalized_name = ?
                """,
                (normalized_name,),
            ).fetchone()

        if row is None:
            return None
        return HeroStats(
            name=str(row["name"]),
            win_rate=float(row["win_rate"]),
            pick_rate=float(row["pick_rate"]),
            meta_rank=int(row["meta_rank"]),
            total_heroes=int(row["total_heroes"]),
        )

    def list_heroes(self) -> list[str]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT name
                FROM heroes
                WHERE win_rate IS NOT NULL AND pick_rate IS NOT NULL
                ORDER BY name COLLATE NOCASE
                """
            ).fetchall()
        return [str(row["name"]) for row in rows]

    def seed_from_file(self, seed_path: Path) -> int:
        with seed_path.open("r", encoding="utf-8-sig") as file:
            payload = json.load(file)

        if str(payload.get("rank", "")).upper() != "IMMORTAL":
            raise ValueError("Seed-файл должен содержать статистику только ранга IMMORTAL.")

        heroes = payload.get("heroes")
        if not isinstance(heroes, list) or not heroes:
            raise ValueError("В seed-файле нет статистики героев.")

        expected_count = payload.get("hero_count")
        if expected_count is not None and int(expected_count) != len(heroes):
            raise ValueError("hero_count не совпадает с числом героев в seed-файле.")

        prepared: list[tuple[str, str, float, float]] = []
        normalized_names: set[str] = set()
        for hero in heroes:
            clean_name, normalized_name, win_rate, pick_rate = self._validate_hero(
                str(hero["name"]),
                float(hero["win_rate"]),
                float(hero["pick_rate"]),
            )
            if normalized_name in normalized_names:
                raise ValueError(f"Герой {clean_name} повторяется в seed-файле.")
            normalized_names.add(normalized_name)
            prepared.append((clean_name, normalized_name, win_rate, pick_rate))

        with self.connect() as connection:
            for clean_name, normalized_name, win_rate, pick_rate in prepared:
                self._upsert_hero(
                    connection,
                    clean_name,
                    normalized_name,
                    win_rate,
                    pick_rate,
                )

            placeholders = ",".join("?" for _ in normalized_names)
            connection.execute(
                f"DELETE FROM heroes WHERE normalized_name NOT IN ({placeholders})",
                tuple(normalized_names),
            )

            # Старые матчапы могли остаться после предыдущей версии базы.
            table_exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'matchups'"
            ).fetchone()
            if table_exists is not None:
                connection.execute("DELETE FROM matchups")

        return len(prepared)

    def hero_count(self) -> int:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM heroes
                WHERE win_rate IS NOT NULL AND pick_rate IS NOT NULL
                """
            ).fetchone()
        return int(row["count"])

    def delete_hero(self, name: str) -> bool:
        normalized_name = normalize_name(name)
        if not normalized_name:
            return False

        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM heroes WHERE normalized_name = ?",
                (normalized_name,),
            )
            return cursor.rowcount > 0

    def _upsert_hero(
        self,
        connection: sqlite3.Connection,
        name: str,
        normalized_name: str,
        win_rate: float,
        pick_rate: float,
    ) -> None:
        connection.execute(
            """
            INSERT INTO heroes (name, normalized_name, win_rate, pick_rate)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(normalized_name) DO UPDATE SET
                name = excluded.name,
                win_rate = excluded.win_rate,
                pick_rate = excluded.pick_rate,
                updated_at = CURRENT_TIMESTAMP
            """,
            (name, normalized_name, win_rate, pick_rate),
        )

    def _validate_hero(
        self,
        name: str,
        win_rate: float,
        pick_rate: float,
    ) -> tuple[str, str, float, float]:
        clean_name = name.strip()
        normalized_name = normalize_name(clean_name)
        if not normalized_name:
            raise ValueError("Название героя не может быть пустым.")

        win_rate = float(win_rate)
        pick_rate = float(pick_rate)
        if not 0 <= win_rate <= 100:
            raise ValueError("Винрейт должен быть от 0 до 100 процентов.")
        if not 0 <= pick_rate <= 100:
            raise ValueError("Пикрейт должен быть от 0 до 100 процентов.")
        return clean_name, normalized_name, win_rate, pick_rate

    def _ensure_column(
        self,
        connection: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = {
            str(row["name"])
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


# Старое имя оставлено как алиас, чтобы внешние импорты проекта не сломались.
MatchupRepository = HeroStatsRepository
