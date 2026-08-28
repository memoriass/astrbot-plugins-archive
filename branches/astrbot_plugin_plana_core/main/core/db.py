from __future__ import annotations

import sqlite3
from pathlib import Path


class Database:
    """Shared database connection factory for Plana Core.

    All storage modules should use this factory to obtain connections
    instead of managing their own connection logic.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        """Create and return a new SQLite connection."""
        return sqlite3.connect(self.db_path)
