"""Structured user profile storage — person_info model.

Provides NachoBot-equivalent structured user profiles with dedicated fields
for birthday, occupation, interests, tags, and custom attributes.
Stored in a dedicated table separate from semantic SPO triples.
"""

from __future__ import annotations

import json
from time import time
from typing import Any

from ..db import Database


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
        """Generate a human-readable profile summary for prompt injection."""
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

    def update_field(self, user_id: str, scope_id: str, field: str, value: str) -> bool:
        """Update a single text field on a profile."""
        allowed = {"nickname", "birthday", "occupation", "location"}
        if field not in allowed:
            return False
        now = int(time())
        with self.db.connect() as conn:
            existing = conn.execute(
                "SELECT 1 FROM person_info WHERE user_id=? AND scope_id=?",
                (user_id, scope_id),
            ).fetchone()
            if not existing:
                # Auto-create minimal profile
                conn.execute(
                    """INSERT INTO person_info
                       (user_id, scope_id, nickname, birthday, occupation, location,
                        interests, tags, custom, updated_at, created_at)
                       VALUES (?, ?, '', '', '', '', '[]', '[]', '{}', ?, ?)""",
                    (user_id, scope_id, now, now),
                )
            conn.execute(
                f"UPDATE person_info SET {field}=?, updated_at=? WHERE user_id=? AND scope_id=?",  # noqa: S608
                (value[:100], now, user_id, scope_id),
            )
        return True

    def add_interest(self, user_id: str, scope_id: str, interest: str) -> bool:
        """Add an interest to a user's profile."""
        info = self.get(user_id, scope_id)
        if not info:
            info = PersonInfo(user_id=user_id, scope_id=scope_id)
        clean = interest.strip()[:50]
        if clean and clean not in info.interests:
            info.interests.append(clean)
            self.upsert(info)
            return True
        return False

    def add_tag(self, user_id: str, scope_id: str, tag: str) -> bool:
        """Add a tag to a user's profile."""
        info = self.get(user_id, scope_id)
        if not info:
            info = PersonInfo(user_id=user_id, scope_id=scope_id)
        clean = tag.strip()[:30]
        if clean and clean not in info.tags:
            info.tags.append(clean)
            self.upsert(info)
            return True
        return False

    def set_custom(self, user_id: str, scope_id: str, key: str, value: str) -> None:
        """Set a custom attribute on a user's profile."""
        info = self.get(user_id, scope_id)
        if not info:
            info = PersonInfo(user_id=user_id, scope_id=scope_id)
        info.custom[key[:50]] = value[:200]
        self.upsert(info)

    def list_profiles(self, scope_id: str, limit: int = 20) -> list[PersonInfo]:
        """List all profiles in a scope."""
        safe_limit = max(1, min(limit, 100))
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT user_id, scope_id, nickname, birthday, occupation,
                          location, interests, tags, custom, updated_at, created_at
                   FROM person_info WHERE scope_id=?
                   ORDER BY updated_at DESC LIMIT ?""",
                (scope_id, safe_limit),
            ).fetchall()
        return [self._row_to_person(row) for row in rows]

    def delete(self, user_id: str, scope_id: str = "global") -> bool:
        """Delete a user's profile."""
        with self.db.connect() as conn:
            affected = conn.execute(
                "DELETE FROM person_info WHERE user_id=? AND scope_id=?",
                (user_id, scope_id),
            ).rowcount
        return affected > 0

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
