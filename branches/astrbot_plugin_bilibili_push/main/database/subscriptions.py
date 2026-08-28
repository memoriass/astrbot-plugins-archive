from __future__ import annotations

import json
import sqlite3
from typing import Optional

from ..utils.logger import logger
from .models import Subscription


class SubscriptionStoreMixin:
    def add_subscription(self, sub: Subscription) -> bool:
        try:
            with self._connect() as conn:
                self._ensure_target(conn, sub.target_id)
                conn.execute(
                    """
                    INSERT INTO subscriptions (
                        uid, username, sub_type, target_id, categories, tags, enabled
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._subscription_values(sub),
                )
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False
        except Exception as exc:
            logger.error(f"添加订阅失败: {exc}")
            return False

    def remove_subscription(self, uid: str, sub_type: str, target_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                DELETE FROM subscriptions
                WHERE uid = ? AND sub_type = ? AND target_id = ?
                """,
                (str(uid), sub_type, target_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def set_subscription_enabled(
        self,
        uid: str,
        sub_type: str,
        target_id: str,
        enabled: bool,
    ) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE subscriptions
                SET enabled = ?
                WHERE uid = ? AND sub_type = ? AND target_id = ?
                """,
                (1 if enabled else 0, str(uid), sub_type, target_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def update_subscription(
        self,
        original_uid: str,
        original_sub_type: str,
        original_target_id: str,
        sub: Subscription,
    ) -> bool:
        try:
            with self._connect() as conn:
                self._ensure_target(conn, sub.target_id)
                cursor = conn.execute(
                    """
                    UPDATE subscriptions
                    SET uid = ?, username = ?, sub_type = ?, target_id = ?,
                        categories = ?, tags = ?, enabled = ?
                    WHERE uid = ? AND sub_type = ? AND target_id = ?
                    """,
                    (
                        *self._subscription_values(sub),
                        str(original_uid),
                        original_sub_type,
                        original_target_id,
                    ),
                )
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.IntegrityError:
            return False

    def get_subscriptions(self, target_id: Optional[str] = None) -> list[Subscription]:
        with self._connect() as conn:
            if target_id:
                cursor = conn.execute(
                    """
                    SELECT uid, username, sub_type, target_id,
                           categories, tags, enabled
                    FROM subscriptions
                    WHERE target_id = ?
                    """,
                    (target_id,),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT uid, username, sub_type, target_id,
                           categories, tags, enabled
                    FROM subscriptions
                    """
                )
            return [self._subscription_from_row(row) for row in cursor]

    def get_enabled_subscriptions(
        self, target_id: Optional[str] = None
    ) -> list[Subscription]:
        params = []
        where = ["s.enabled = 1", "COALESCE(t.enabled, 1) = 1"]
        if target_id:
            where.append("s.target_id = ?")
            params.append(target_id)
        with self._connect() as conn:
            cursor = conn.execute(
                f"""
                SELECT s.uid, s.username, s.sub_type, s.target_id,
                       s.categories, s.tags, s.enabled
                FROM subscriptions s
                LEFT JOIN targets t ON t.target_id = s.target_id
                WHERE {" AND ".join(where)}
                """,
                params,
            )
            return [self._subscription_from_row(row) for row in cursor]

    @staticmethod
    def _subscription_values(sub: Subscription) -> tuple:
        return (
            sub.uid,
            sub.username,
            sub.sub_type,
            sub.target_id,
            json.dumps(sub.categories),
            json.dumps(sub.tags),
            1 if sub.enabled else 0,
        )

    @staticmethod
    def _subscription_from_row(row) -> Subscription:
        return Subscription(
            uid=row[0],
            username=row[1],
            sub_type=row[2],
            target_id=row[3],
            categories=json.loads(row[4] or "[]"),
            tags=json.loads(row[5] or "[]"),
            enabled=bool(row[6]),
        )
