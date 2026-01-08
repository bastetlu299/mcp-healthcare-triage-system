from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Tuple


class DatabaseSetup:
    """Helper to initialize the healthcare triage SQLite database."""

    def __init__(self, db_path: Path | str = "triage.db") -> None:
        self.db_path = Path(db_path)

    def initialize(self) -> None:
        """Create tables and seed sample data if empty."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS patients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    date_of_birth TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS cases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_id INTEGER NOT NULL,
                    complaint TEXT NOT NULL,
                    urgency TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(patient_id) REFERENCES patients(id)
                );

                CREATE TABLE IF NOT EXISTS encounters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_id INTEGER NOT NULL,
                    channel TEXT NOT NULL,
                    notes TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(patient_id) REFERENCES patients(id)
                );
                """
            )
            conn.commit()

            cursor = conn.execute("SELECT COUNT(*) FROM patients")
            count = cursor.fetchone()[0]
            if count == 0:
                patients: Iterable[Tuple[str, str, str]] = [
                    ("Ana Rivera", "1987-05-14", "stable"),
                    ("Brian Lee", "1974-11-02", "monitoring"),
                    ("Cara Singh", "1992-08-30", "urgent"),
                ]
                encounters: Iterable[Tuple[int, str, str]] = [
                    (1, "phone", "Reported dizziness and mild headache"),
                    (1, "chat", "Shared blood pressure readings"),
                    (2, "phone", "Medication refill request"),
                    (3, "email", "Reported chest tightness after exercise"),
                ]
                conn.executemany(
                    "INSERT INTO patients(name, date_of_birth, status) VALUES(?,?,?)",
                    patients,
                )
                conn.executemany(
                    "INSERT INTO encounters(patient_id, channel, notes) VALUES(?,?,?)",
                    encounters,
                )
                conn.commit()


if __name__ == "__main__":
    DatabaseSetup().initialize()
    print("Database initialized at triage.db")
