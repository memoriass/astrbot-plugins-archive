from __future__ import annotations

import json
import sqlite3
import time


class AccountStoreMixin:
    def get_accounts(self) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT uid, name, face, cookies, valid, status_code,
                       cooldown_until, failure_count, created_at, updated_at
                FROM accounts
                ORDER BY created_at ASC, uid ASC
                """
            )
            return [self._account_from_row(row) for row in cursor]

    def upsert_account(self, account: dict) -> None:
        now = int(time.time())
        uid = str(account.get("uid") or "")
        if not uid:
            return
        existing = self.get_account(uid)
        cookies = account.get("cookies")
        if cookies is None and existing:
            cookies = existing.get("cookies") or {}
        created_at = int((existing or {}).get("created_at") or now)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO accounts (
                    uid, name, face, cookies, valid, status_code,
                    cooldown_until, failure_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uid,
                    str(account.get("name") or ""),
                    str(account.get("face") or ""),
                    json.dumps(cookies or {}, ensure_ascii=False),
                    1 if account.get("valid", True) else 0,
                    account.get("status_code"),
                    int(account.get("cooldown_until") or 0),
                    int(account.get("failure_count") or 0),
                    created_at,
                    now,
                ),
            )
            conn.commit()

    def get_account(self, uid: str) -> dict | None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT uid, name, face, cookies, valid, status_code,
                       cooldown_until, failure_count, created_at, updated_at
                FROM accounts
                WHERE uid = ?
                """,
                (str(uid),),
            )
            row = cursor.fetchone()
            return self._account_from_row(row) if row else None

    def remove_account(self, uid: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM accounts WHERE uid = ?",
                (str(uid),),
            )
            conn.commit()
            return cursor.rowcount > 0

    def set_account_valid(self, uid: str, valid: bool) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE accounts
                SET valid = ?, status_code = NULL, cooldown_until = 0,
                    failure_count = 0, updated_at = ?
                WHERE uid = ?
                """,
                (1 if valid else 0, int(time.time()), str(uid)),
            )
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def _account_from_row(row) -> dict:
        try:
            cookies = json.loads(row[3] or "{}")
        except json.JSONDecodeError:
            cookies = {}
        return {
            "uid": str(row[0] or ""),
            "name": str(row[1] or ""),
            "face": str(row[2] or ""),
            "cookies": cookies if isinstance(cookies, dict) else {},
            "valid": bool(row[4]),
            "status_code": row[5],
            "cooldown_until": int(row[6] or 0),
            "failure_count": int(row[7] or 0),
            "created_at": int(row[8] or 0),
            "updated_at": int(row[9] or 0),
        }
