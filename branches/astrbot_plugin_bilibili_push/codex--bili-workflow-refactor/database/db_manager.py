from __future__ import annotations

import sqlite3
from pathlib import Path

from .accounts import AccountStoreMixin
from .models import Subscription, Target
from .schema import init_schema
from .subscriptions import SubscriptionStoreMixin
from .targets import TargetStoreMixin


class DatabaseManager(SubscriptionStoreMixin, AccountStoreMixin, TargetStoreMixin):
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            init_schema(conn)
            self.sync_targets_from_subscriptions(conn)
            conn.commit()


__all__ = ["DatabaseManager", "Subscription", "Target"]
