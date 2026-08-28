"""Structured person profile storage."""

from __future__ import annotations

import json
from time import time
from typing import Any

from ..plugin.db import Database


class PersonInfo:
    """Structured user profile with dedicated fields."""

    __slots__ = (
        "user_id",
        "scope_id",
        "nickname",
        "birthday",
        "occupation",
        "location",
        "interests",
        "tags",
        "custom",
        "updated_at",
        "created_at",
    )

    def __init__(
        self,
        user_id: str,
        scope_id: str = "global",
        nickname: str = "",
        birthday: str = "",
        occupation: str = "",
        location: str = "",
        interests: list[str] | None = None,
        tags: list[str] | None = None,
        custom: dict[str, str] | None = None,
        updated_at: int = 0,
        created_at: int = 0,
    ):
        self.user_id = user_id
        self.scope_id = scope_id
        self.nickname = nickname
        self.birthday = birthday
        self.occupation = occupation
        self.location = location
        self.interests = interests or []
        self.tags = tags or []
        self.custom = custom or {}
        self.updated_at = updated_at
        self.created_at = created_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "scope_id": self.scope_id,
            "nickname": self.nickname,
            "birthday": self.birthday,
            "occupation": self.occupation,
            "location": self.location,
            "interests": self.interests,
            "tags": self.tags,
            "custom": self.custom,
            "updated_at": self.updated_at,
            "created_at": self.created_at,
        }

    def summary_text(self) -> str:
        parts = []
        if self.nickname:
            parts.append(f"nickname: {self.nickname}")
        if self.birthday:
            parts.append(f"birthday: {self.birthday}")
        if self.occupation:
            parts.append(f"occupation: {self.occupation}")
        if self.location:
            parts.append(f"location: {self.location}")
        if self.interests:
            parts.append(f"interests: {', '.join(self.interests[:8])}")
        if self.tags:
            parts.append(f"tags: {', '.join(self.tags[:8])}")
        if self.custom:
            for k, v in list(self.custom.items())[:5]:
                parts.append(f"{k}: {v}")
        return "; ".join(parts) if parts else ""


class PersonInfoStorage:
    """SQLite storage for structured user profiles."""

    def __init__(self, db: Database):
        self.db = db

    def initialize(self) -> None:
        with self.db.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS person_info (
                    user_id TEXT NOT NULL,
                    scope_id TEXT NOT NULL DEFAULT 'global',
                    nickname TEXT NOT NULL DEFAULT '',
                    birthday TEXT NOT NULL DEFAULT '',
                    occupation TEXT NOT NULL DEFAULT '',
                    location TEXT NOT NULL DEFAULT '',
                    interests TEXT NOT NULL DEFAULT '[]',
                    tags TEXT NOT NULL DEFAULT '[]',
                    custom TEXT NOT NULL DEFAULT '{}',
                    updated_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (user_id, scope_id)
                );
                """
            )

    def get(self, user_id: str, scope_id: str = "global") -> PersonInfo | None:
        """Get a user's profile."""
        with self.db.connect() as conn:
            row = conn.execute(
                """SELECT user_id, scope_id, nickname, birthday, occupation,
                          location, interests, tags, custom, updated_at, created_at
                   FROM person_info WHERE user_id=? AND scope_id=?""",
                (user_id, scope_id),
            ).fetchone()
        if not row:
            return None
        return self._row_to_person(row)

    def upsert(self, info: PersonInfo) -> None:
        """Create or update a user profile."""
        now = int(time())
        interests_json = json.dumps(info.interests[:20])
        tags_json = json.dumps(info.tags[:20])
        custom_json = json.dumps(dict(list(info.custom.items())[:20]))
        with self.db.connect() as conn:
            existing = conn.execute(
                "SELECT created_at FROM person_info WHERE user_id=? AND scope_id=?",
                (info.user_id, info.scope_id),
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE person_info SET nickname=?, birthday=?, occupation=?,
                       location=?, interests=?, tags=?, custom=?, updated_at=?
                       WHERE user_id=? AND scope_id=?""",
                    (
                        info.nickname[:100],
                        info.birthday[:50],
                        info.occupation[:100],
                        info.location[:100],
                        interests_json,
                        tags_json,
                        custom_json,
                        now,
                        info.user_id,
                        info.scope_id,
                    ),
                )
            else:
                conn.execute(
                    """INSERT INTO person_info
                       (user_id, scope_id, nickname, birthday, occupation, location,
                        interests, tags, custom, updated_at, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        info.user_id,
                        info.scope_id,
                        info.nickname[:100],
                        info.birthday[:50],
                        info.occupation[:100],
                        info.location[:100],
                        interests_json,
                        tags_json,
                        custom_json,
                        now,
                        now,
                    ),
                )

    def _row_to_person(self, row: tuple) -> PersonInfo:
        return PersonInfo(
            user_id=row[0],
            scope_id=row[1],
            nickname=row[2],
            birthday=row[3],
            occupation=row[4],
            location=row[5],
            interests=json.loads(row[6]) if row[6] else [],
            tags=json.loads(row[7]) if row[7] else [],
            custom=json.loads(row[8]) if row[8] else {},
            updated_at=row[9],
            created_at=row[10],
        )
