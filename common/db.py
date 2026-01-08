"""
Async Database Utilities
------------------------
Provides asynchronous access to patient, case, and encounter data using
SQLite + aiosqlite. This module encapsulates schema initialization as well as
CRUD operations required by the MCP server and the A2A agents.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite


# ---------------------------------------------------------------------------
# Database configuration
# ---------------------------------------------------------------------------

DB_PATH = Path(os.getenv("A2A_DB_PATH", "./triage.db"))

_SCHEMA_SQL = """
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

_SEED_PATIENTS = [
    ("Ana Rivera", "1987-05-14", "stable"),
    ("Brian Lee", "1974-11-02", "monitoring"),
    ("Cara Singh", "1992-08-30", "urgent"),
]

_SEED_ENCOUNTERS = [
    (1, "phone", "Reported dizziness and mild headache"),
    (1, "chat", "Shared blood pressure readings"),
    (2, "phone", "Medication refill request"),
    (3, "email", "Reported chest tightness after exercise"),
]


# ---------------------------------------------------------------------------
# Initialization helpers
# ---------------------------------------------------------------------------

async def initialize_database(db_path: Path = DB_PATH) -> None:
    """
    Create schema if needed and populate sample rows when database is empty.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_SCHEMA_SQL)
        await db.commit()

        # Only insert seed data on first run
        row_count = await db.execute_fetchone("SELECT COUNT(*) FROM patients")
        if row_count and row_count[0] == 0:
            await db.executemany(
                "INSERT INTO patients(name, date_of_birth, status) VALUES (?, ?, ?)",
                _SEED_PATIENTS,
            )
            await db.executemany(
                "INSERT INTO encounters(patient_id, channel, notes) VALUES (?, ?, ?)",
                _SEED_ENCOUNTERS,
            )
            await db.commit()


async def open_connection(db_path: Path = DB_PATH) -> aiosqlite.Connection:
    """
    Ensure the DB is initialized, then return a new connection.
    """
    await initialize_database(db_path)
    return await aiosqlite.connect(db_path)


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

async def get_patient(patient_id: int) -> Optional[Dict[str, Any]]:
    """
    Retrieve a single patient by ID.
    """
    async with await open_connection() as db:
        row = await db.execute_fetchone(
            "SELECT id, name, date_of_birth, status, created_at FROM patients WHERE id = ?",
            (patient_id,),
        )
        if not row:
            return None
        return {
            "id": row[0],
            "name": row[1],
            "date_of_birth": row[2],
            "status": row[3],
            "created_at": row[4],
        }


async def list_patients(status: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Retrieve multiple patients, optionally filtered by status.
    """
    async with await open_connection() as db:
        if status:
            rows = await db.execute_fetchall(
                "SELECT id, name, date_of_birth, status, created_at "
                "FROM patients WHERE status = ? LIMIT ?",
                (status, limit),
            )
        else:
            rows = await db.execute_fetchall(
                "SELECT id, name, date_of_birth, status, created_at "
                "FROM patients LIMIT ?",
                (limit,),
            )
        return [
            {
                "id": r[0],
                "name": r[1],
                "date_of_birth": r[2],
                "status": r[3],
                "created_at": r[4],
            }
            for r in rows
        ]


async def update_patient(patient_id: int, changes: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Update allowed fields on a patient record.
    """
    allowed = {"name", "date_of_birth", "status"}
    clean_updates = {k: v for k, v in changes.items() if k in allowed}

    existing = await get_patient(patient_id)
    if not existing:
        return None
    if not clean_updates:
        return existing

    async with await open_connection() as db:
        for col, value in clean_updates.items():
            await db.execute(
                f"UPDATE patients SET {col} = ? WHERE id = ?",
                (value, patient_id),
            )
        await db.commit()

    return await get_patient(patient_id)


async def create_case(patient_id: int, complaint: str, urgency: str) -> Dict[str, Any]:
    """
    Insert a new case and return the resulting row.
    """
    async with await open_connection() as db:
        cursor = await db.execute(
            "INSERT INTO cases (patient_id, complaint, urgency, status) "
            "VALUES (?, ?, ?, 'open')",
            (patient_id, complaint, urgency),
        )
        await db.commit()
        case_id = cursor.lastrowid

        row = await db.execute_fetchone(
            "SELECT id, patient_id, complaint, urgency, status, created_at "
            "FROM cases WHERE id = ?",
            (case_id,),
        )
        return {
            "id": row[0],
            "patient_id": row[1],
            "complaint": row[2],
            "urgency": row[3],
            "status": row[4],
            "created_at": row[5],
        }


async def list_encounters(patient_id: int) -> List[Dict[str, Any]]:
    """
    Return encounter history newest → oldest.
    """
    async with await open_connection() as db:
        rows = await db.execute_fetchall(
            "SELECT id, channel, notes, created_at "
            "FROM encounters WHERE patient_id = ? ORDER BY created_at DESC",
            (patient_id,),
        )
        return [
            {
                "id": r[0],
                "channel": r[1],
                "notes": r[2],
                "created_at": r[3],
            }
            for r in rows
        ]


async def add_encounter(patient_id: int, notes: str, channel: str = "agent") -> Dict[str, Any]:
    """
    Insert a new encounter entry and return it.
    """
    async with await open_connection() as db:
        cursor = await db.execute(
            "INSERT INTO encounters (patient_id, channel, notes) VALUES (?, ?, ?)",
            (patient_id, channel, notes),
        )
        await db.commit()
        new_id = cursor.lastrowid

        row = await db.execute_fetchone(
            "SELECT id, channel, notes, created_at "
            "FROM encounters WHERE id = ?",
            (new_id,),
        )

        return {
            "id": row[0],
            "channel": row[1],
            "notes": row[2],
            "created_at": row[3],
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    "initialize_database",
    "open_connection",
    "get_patient",
    "list_patients",
    "update_patient",
    "create_case",
    "list_encounters",
    "add_encounter",
    "DB_PATH",
]
