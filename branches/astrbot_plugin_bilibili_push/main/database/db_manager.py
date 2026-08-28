from __future__ import annotations

import sqlite3
from pathlib import Path

from .accounts import AccountStoreMixin
from .aliases import AliasStoreMixin
from .models import Subscription, Target
from .schema import init_schema
from .subscriptions import SubscriptionStoreMixin
from .targets import TargetStoreMixin


class DatabaseManager(
    SubscriptionStoreMixin,
    AccountStoreMixin,
    AliasStoreMixin,
    TargetStoreMixin,
):
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            init_schema(conn)
            self.sync_targets_from_subscriptions(conn)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


__all__ = ["DatabaseManager", "Subscription", "Target"]
