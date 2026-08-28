from __future__ import annotations

import sqlite3

from .models import MEMORY_KIND_BRIDGE_HANDOFF


def migrate_legacy_bridge_handoff(conn: sqlite3.Connection) -> None:
    legacy_ids = [
        int(row[0])
        for row in conn.execute(
            "SELECT id FROM episodic_memories WHERE kind=?",
            ("arona_handoff",),
        ).fetchall()
    ]
    if not legacy_ids:
        return
    conn.execute(
        "UPDATE episodic_memories SET kind=? WHERE kind=?",
        (MEMORY_KIND_BRIDGE_HANDOFF, "arona_handoff"),
    )
    try:
        conn.execute(
            "UPDATE episodic_memories_fts SET kind=? WHERE kind=?",
            (MEMORY_KIND_BRIDGE_HANDOFF, "arona_handoff"),
        )
    except Exception:  # noqa: BLE001
        pass
    placeholders = ",".join("?" * len(legacy_ids))
    conn.execute(
        f"UPDATE memory_atoms SET atom_type=? WHERE parent_memory_id IN ({placeholders}) AND atom_type=?",  # noqa: S608
        ("handoff", *legacy_ids, "unknown"),
    )
