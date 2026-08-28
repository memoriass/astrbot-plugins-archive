from __future__ import annotations

from time import time

from ..plugin.db import Database
from .models import SessionStream, UserIdentity


class IdentityStorage:
    """Storage for identity profiles and session streams."""

    def __init__(self, db: Database):
        self.db = db

    def initialize(self) -> None:
        """Create identity and session tables."""
        with self.db.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS identity_profiles (
                    global_user_id TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    platform_user_id TEXT NOT NULL,
                    nickname TEXT NOT NULL,
                    role TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS session_streams (
                    unified_msg_origin TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    message_type TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    group_id TEXT,
                    last_active_at INTEGER NOT NULL
                );
                """
            )

    def upsert_identity(self, identity: UserIdentity) -> None:
        now = int(time())
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO identity_profiles VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(global_user_id) DO UPDATE SET
                    nickname=excluded.nickname,
                    role=excluded.role,
                    updated_at=excluded.updated_at
                """,
                (
                    identity.global_user_id,
                    identity.platform,
                    identity.platform_user_id,
                    identity.nickname,
                    identity.role,
                    now,
                ),
            )

    def upsert_session(self, session: SessionStream) -> None:
        now = int(time())
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO session_streams VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(unified_msg_origin) DO UPDATE SET
                    message_type=excluded.message_type,
                    session_id=excluded.session_id,
                    group_id=excluded.group_id,
                    last_active_at=excluded.last_active_at
                """,
                (
                    session.unified_msg_origin,
                    session.platform,
                    session.message_type,
                    session.session_id,
                    session.group_id,
                    now,
                ),
            )
