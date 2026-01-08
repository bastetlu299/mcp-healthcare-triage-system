"""
Database interface layer used by the MCP server and A2A agents.

This module centralizes all data reads/writes to the SQLite database,
providing a clean API for the MCP tool handlers to interact with patients,
cases, and encounter history.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from database_setup import DatabaseSetup


# -----------------------------------------------------------------------------
#  Database initialization & configuration
# -----------------------------------------------------------------------------

_setup = DatabaseSetup()
_setup.initialize()  # ensures the DB file + schema exist
DB_PATH: Path = _setup.db_path


def _open_db() -> sqlite3.Connection:
    """
    Return a SQLite connection with row access configured as dict-like objects.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# -----------------------------------------------------------------------------
#  Query Functions
# -----------------------------------------------------------------------------

def get_patient(patient_id: int) -> Optional[Dict[str, Any]]:
    """
    Fetch a single patient record by ID.
    """
    with _open_db() as db:
        row = db.execute(
            """
            SELECT id, name, date_of_birth, status, created_at
            FROM patients
            WHERE id = ?
            """,
            (patient_id,),
        ).fetchone()
        return dict(row) if row else None


def list_patients(status: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Retrieve multiple patients, optionally filtered by status.
    """
    with _open_db() as db:
        if status:
            rows = db.execute(
                """
                SELECT id, name, date_of_birth, status, created_at
                FROM patients
                WHERE status = ?
                LIMIT ?
                """,
                (status, limit),
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT id, name, date_of_birth, status, created_at
                FROM patients
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [dict(r) for r in rows]


def modify_patient(patient_id: int, changes: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Update permitted patient fields. Returns updated record or None if missing.
    """
    allowed = {"name", "date_of_birth", "status"}
    updates = {k: v for k, v in changes.items() if k in allowed}

    # nothing to update → return original
    if not updates:
        return get_patient(patient_id)

    with _open_db() as db:
        exists = db.execute(
            "SELECT 1 FROM patients WHERE id = ?", (patient_id,)
        ).fetchone()
        if not exists:
            return None

        assignments = ", ".join([f"{col} = ?" for col in updates])
        values = list(updates.values()) + [patient_id]

        db.execute(
            f"UPDATE patients SET {assignments} WHERE id = ?",
            values,
        )
        db.commit()

    return get_patient(patient_id)


def new_case(patient_id: int, complaint: str, urgency: str) -> Dict[str, Any]:
    """
    Insert a new triage case and return the full case entry.
    """
    with _open_db() as db:
        cur = db.execute(
            """
            INSERT INTO cases (patient_id, complaint, urgency, status)
            VALUES (?, ?, ?, 'open')
            """,
            (patient_id, complaint, urgency),
        )
        case_id = cur.lastrowid
        db.commit()

        row = db.execute(
            """
            SELECT id, patient_id, complaint, urgency, status, created_at
            FROM cases
            WHERE id = ?
            """,
            (case_id,),
        ).fetchone()

        return dict(row)


def patient_history(patient_id: int) -> List[Dict[str, Any]]:
    """
    Retrieve encounter records for a patient, newest first.
    """
    with _open_db() as db:
        rows = db.execute(
            """
            SELECT id, channel, notes, created_at
            FROM encounters
            WHERE patient_id = ?
            ORDER BY created_at DESC
            """,
            (patient_id,),
        ).fetchall()

        return [dict(r) for r in rows]


# -----------------------------------------------------------------------------
#  Backwards-compatible aliases for legacy imports
# -----------------------------------------------------------------------------

def fetch_patient(patient_id: int) -> Optional[Dict[str, Any]]:
    return get_patient(patient_id)


def fetch_patients(status: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    return list_patients(status=status, limit=limit)


def update_patient_record(patient_id: int, changes: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return modify_patient(patient_id, changes)


def create_case_record(patient_id: int, complaint: str, urgency: str) -> Dict[str, Any]:
    return new_case(patient_id, complaint, urgency)


def fetch_history(patient_id: int) -> List[Dict[str, Any]]:
    return patient_history(patient_id)


# -----------------------------------------------------------------------------
#  Public API for import
# -----------------------------------------------------------------------------

__all__ = [
    "DB_PATH",
    "get_patient",
    "list_patients",
    "modify_patient",
    "new_case",
    "patient_history",
    "fetch_patient",
    "fetch_patients",
    "update_patient_record",
    "create_case_record",
    "fetch_history",
]
