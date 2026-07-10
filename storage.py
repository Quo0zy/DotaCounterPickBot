import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HeroMatchups:
    name: str
    good_against: list[str]
    bad_against: list[str]


def normalize_name(value: str) -> str:
    value = value.casefold().replace("ё", "е").strip()
    return "".join(char for char in value if char.isalnum())


class MatchupRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS heroes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    normalized_name TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS matchups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hero_id INTEGER NOT NULL,
                    opponent_name TEXT NOT NULL,
                    normalized_opponent_name TEXT NOT NULL,
                    relation TEXT NOT NULL CHECK (relation IN ('good', 'bad')),
                    rank INTEGER NOT NULL CHECK (rank BETWEEN 1 AND 3),
                    FOREIGN KEY (hero_id) REFERENCES heroes(id) ON DELETE CASCADE,
                    UNIQUE (hero_id, relation, rank),
                    UNIQUE (hero_id, relation, normalized_opponent_name)
                );
                """
            )

    def upsert_hero(self, name: str, good_against: list[str], bad_against: list[str]) -> None:
        normalized_name = normalize_name(name)
        if not normalized_name:
            raise ValueError("Название героя не может быть пустым.")

        self._validate_matchups(good_against, bad_against)

        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO heroes (name, normalized_name)
                VALUES (?, ?)
                ON CONFLICT(normalized_name) DO UPDATE SET
                    name = excluded.name,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (name.strip(), normalized_name),
            )
            cursor = connection.execute(
                "SELECT id FROM heroes WHERE normalized_name = ?",
                (normalized_name,),
            )
            hero_id = int(cursor.fetchone()["id"])

            connection.execute("DELETE FROM matchups WHERE hero_id = ?", (hero_id,))
            self._insert_matchups(connection, hero_id, "good", good_against)
            self._insert_matchups(connection, hero_id, "bad", bad_against)

    def get_hero(self, name: str) -> HeroMatchups | None:
        normalized_name = normalize_name(name)
        if not normalized_name:
            return None

        with self.connect() as connection:
            hero = connection.execute(
                "SELECT id, name FROM heroes WHERE normalized_name = ?",
                (normalized_name,),
            ).fetchone()
            if hero is None:
                return None

            rows = connection.execute(
                """
                SELECT opponent_name, relation
                FROM matchups
                WHERE hero_id = ?
                ORDER BY relation, rank
                """,
                (hero["id"],),
            ).fetchall()

        good_against = [row["opponent_name"] for row in rows if row["relation"] == "good"]
        bad_against = [row["opponent_name"] for row in rows if row["relation"] == "bad"]
        return HeroMatchups(hero["name"], good_against, bad_against)

    def list_heroes(self) -> list[str]:
        with self.connect() as connection:
            rows = connection.execute("SELECT name FROM heroes ORDER BY name COLLATE NOCASE").fetchall()
        return [row["name"] for row in rows]

    def seed_from_file(self, seed_path: Path) -> int:
        with seed_path.open("r", encoding="utf-8-sig") as file:
            payload = json.load(file)

        heroes = payload.get("heroes", [])
        seeded_count = 0
        for hero in heroes:
            self.upsert_hero(
                str(hero["name"]),
                [str(name) for name in hero["good_against"]],
                [str(name) for name in hero["bad_against"]],
            )
            seeded_count += 1

        return seeded_count

    def hero_count(self) -> int:
        with self.connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM heroes").fetchone()
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

    def _insert_matchups(
        self,
        connection: sqlite3.Connection,
        hero_id: int,
        relation: str,
        opponents: list[str],
    ) -> None:
        for rank, opponent_name in enumerate(opponents, 1):
            connection.execute(
                """
                INSERT INTO matchups (hero_id, opponent_name, normalized_opponent_name, relation, rank)
                VALUES (?, ?, ?, ?, ?)
                """,
                (hero_id, opponent_name.strip(), normalize_name(opponent_name), relation, rank),
            )

    def _validate_matchups(self, good_against: list[str], bad_against: list[str]) -> None:
        if len(good_against) != 3 or len(bad_against) != 3:
            raise ValueError("Нужно указать ровно 3 хороших и ровно 3 плохих матчапа.")

        all_names = good_against + bad_against
        normalized_names = [normalize_name(name) for name in all_names]
        if any(not name for name in normalized_names):
            raise ValueError("В списках матчапов есть пустое название героя.")

        if len(normalized_names) != len(set(normalized_names)):
            raise ValueError("Один и тот же герой не должен повторяться в матчапах.")
