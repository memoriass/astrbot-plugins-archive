from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
from typing import Any


BOT_ONLY_PREFIXES = (
    "我在", "我给", "我确认", "我报告", "我进入", "我参与", "我建议",
    "我回复", "我提醒", "普拉娜", "机器人", "bot",
)
MECHANICAL_MARKERS = (
    "执行部门", "请稍候", "随时待命", "请吩咐", "工作线程",
    "系统协议", "启动外部", "任务已进入", "已彻底挂起",
)
PREFERENCE_MARKERS = ("喜欢", "偏好", "希望", "习惯", "常用", "不喜欢")


def normalize(text: str) -> str:
    return " ".join(str(text or "").strip().split())


def sanitize(content: str) -> str:
    text = normalize(content)
    text = re.split(
        r"[；，。]\s*我(?:在|回复|说明|建议|确认|提供|以|判断|报告|提醒|进入|参与)",
        text,
        maxsplit=1,
    )[0].rstrip("；，。 ")
    return text


def source_key(atom: sqlite3.Row) -> str:
    raw = f"{atom['id']}|{atom['parent_memory_id']}|{normalize(atom['content'])}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def classify(content: str) -> tuple[str, float] | None:
    text = sanitize(content)
    lowered = text.lower()
    if not text or any(marker.lower() in lowered for marker in MECHANICAL_MARKERS):
        return None
    if lowered.startswith(tuple(item.lower() for item in BOT_ONLY_PREFIXES)):
        return None
    if text.startswith(("零", "用户")):
        if any(marker in text for marker in PREFERENCE_MARKERS):
            return "user_preference", 0.62
        return "user_fact", 0.58
    return "task_fact", 0.46


def actor_from_session(session_id: str) -> str:
    match = re.search(r":(?:GroupMessage|FriendMessage):([^_!]+)", session_id)
    return f"aiocqhttp:{match.group(1)}" if match else ""


def ensure_target_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS livingmemory_migration_map (
            source_key TEXT PRIMARY KEY,
            source_atom_id INTEGER NOT NULL,
            source_parent_id INTEGER NOT NULL,
            target_memory_id INTEGER NOT NULL,
            migrated_at INTEGER NOT NULL
        )
        """
    )


def existing_contents(conn: sqlite3.Connection) -> set[str]:
    return {
        normalize(row[0])
        for row in conn.execute("SELECT content FROM episodic_memories")
        if normalize(row[0])
    }


def insert_memory(
    conn: sqlite3.Connection,
    atom: sqlite3.Row,
    kind: str,
    importance: float,
) -> int:
    content = sanitize(atom["content"])[:1000]
    scope_id = str(atom["session_id"] or "global")[:300]
    actor_id = actor_from_session(scope_id)
    created_at = int(float(atom["created_at"] or time.time()))
    source = f"livingmemory_migration:atom:{atom['id']}"
    cursor = conn.execute(
        """
        INSERT INTO episodic_memories(
            scope, scope_id, kind, content, importance, source,
            created_at, actor_id, subject
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "session",
            scope_id,
            kind,
            content,
            importance,
            source,
            created_at,
            actor_id,
            f"user:{actor_id}" if actor_id else "",
        ),
    )
    memory_id = int(cursor.lastrowid)
    try:
        conn.execute(
            """
            INSERT INTO episodic_memories_fts(
                rowid, memory_id, scope_id, kind, content
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (memory_id, memory_id, scope_id, kind, content),
        )
    except sqlite3.Error:
        pass
    ttl_days = max(30.0, min(float(atom["ttl_days"] or 90.0), 365.0))
    expires_at = created_at + int(ttl_days * 86400)
    metadata = json.dumps(
        {
            "migration_source": "livingmemory",
            "source_atom_id": atom["id"],
            "source_parent_memory_id": atom["parent_memory_id"],
            "source_persona_id": atom["persona_id"],
        },
        ensure_ascii=False,
    )
    atom_cursor = conn.execute(
        """
        INSERT INTO memory_atoms(
            parent_memory_id, scope, scope_id, atom_type, content,
            importance, confidence, source, created_at, last_accessed_at,
            last_reinforced_at, ttl_days, expires_at, status,
            reinforcement_count, decay_type, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 0, ?, ?)
        """,
        (
            memory_id,
            "session",
            scope_id,
            kind,
            content,
            importance,
            max(0.35, min(float(atom["confidence"] or 0.6), 0.9)),
            source,
            created_at,
            created_at,
            None,
            ttl_days,
            expires_at,
            str(atom["decay_type"] or "exponential"),
            metadata,
        ),
    )
    target_atom_id = int(atom_cursor.lastrowid)
    try:
        conn.execute(
            """
            INSERT INTO memory_atoms_fts(
                rowid, atom_id, scope_id, atom_type, content
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (target_atom_id, target_atom_id, scope_id, kind, content),
        )
    except sqlite3.Error:
        pass
    return memory_id


def upsert_profile_semantic(
    conn: sqlite3.Connection,
    atom: sqlite3.Row,
    kind: str,
    content: str,
    subject_aliases: dict[str, list[str]],
) -> bool:
    if kind not in {"user_fact", "user_preference"}:
        return False
    actor_id = actor_from_session(str(atom["session_id"] or ""))
    if not actor_id:
        return False
    predicate_prefix = "legacy_preference" if kind == "user_preference" else "legacy_fact"
    for subject in [actor_id, *subject_aliases.get(actor_id, [])]:
        conn.execute(
            """
            INSERT INTO semantic_memories(
                scope_id, subject, predicate, object_value,
                confidence, source, updated_at
            ) VALUES ('global', ?, ?, ?, ?, ?, ?)
            ON CONFLICT(scope_id, subject, predicate) DO UPDATE SET
                object_value=excluded.object_value,
                confidence=max(semantic_memories.confidence, excluded.confidence),
                source=excluded.source,
                updated_at=excluded.updated_at
            """,
            (
                subject,
                f"{predicate_prefix}_{atom['id']}",
                content[:1000],
                max(0.45, min(float(atom["confidence"] or 0.6), 0.9)),
                f"livingmemory_migration:atom:{atom['id']}",
                int(time.time()),
            ),
        )
    return True


def migrate(
    source: Path,
    target: Path,
    *,
    execute: bool,
    subject_aliases: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    source_conn = sqlite3.connect(source)
    source_conn.row_factory = sqlite3.Row
    target_conn = sqlite3.connect(target)
    target_conn.row_factory = sqlite3.Row
    ensure_target_schema(target_conn)
    aliases = subject_aliases or {}
    if execute:
        target_conn.execute(
            """
            UPDATE episodic_memories
            SET actor_id=replace(actor_id, 'llonebot:', 'aiocqhttp:'),
                subject=replace(subject, 'llonebot:', 'aiocqhttp:')
            WHERE source LIKE 'livingmemory_migration:%'
            """
        )
    existing = existing_contents(target_conn)
    mapped = {
        row[0]
        for row in target_conn.execute("SELECT source_key FROM livingmemory_migration_map")
    }
    stats = {
        "source_atoms": 0,
        "eligible": 0,
        "filtered": 0,
        "duplicate": 0,
        "migrated": 0,
        "profile_semantics": 0,
    }
    rows = source_conn.execute(
        """
        SELECT id, parent_memory_id, atom_type, content, importance, confidence,
               created_at, ttl_days, status, decay_type, session_id, persona_id
        FROM memory_atoms
        WHERE status='active'
        ORDER BY id
        """
    ).fetchall()
    stats["source_atoms"] = len(rows)
    for atom in rows:
        classification = classify(atom["content"])
        if classification is None:
            stats["filtered"] += 1
            continue
        stats["eligible"] += 1
        key = source_key(atom)
        content = sanitize(atom["content"])
        kind, importance = classification
        if key in mapped or content in existing:
            stats["duplicate"] += 1
            if execute and upsert_profile_semantic(
                target_conn, atom, kind, content, aliases
            ):
                stats["profile_semantics"] += 1
            continue
        if not execute:
            continue
        memory_id = insert_memory(target_conn, atom, kind, importance)
        if upsert_profile_semantic(target_conn, atom, kind, content, aliases):
            stats["profile_semantics"] += 1
        target_conn.execute(
            """
            INSERT INTO livingmemory_migration_map(
                source_key, source_atom_id, source_parent_id,
                target_memory_id, migrated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (key, atom["id"], atom["parent_memory_id"], memory_id, int(time.time())),
        )
        mapped.add(key)
        existing.add(content)
        stats["migrated"] += 1
    if execute:
        target_conn.commit()
    else:
        target_conn.rollback()
    source_conn.close()
    target_conn.close()
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate stable LivingMemory atoms into Plana Core.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--subject-alias",
        action="append",
        default=[],
        help="Map a source subject to another Core subject, for example source=target.",
    )
    args = parser.parse_args()
    aliases: dict[str, list[str]] = {}
    for item in args.subject_alias:
        source_subject, separator, target_subject = item.partition("=")
        if separator and source_subject.strip() and target_subject.strip():
            aliases.setdefault(source_subject.strip(), []).append(target_subject.strip())
    result = migrate(
        args.source,
        args.target,
        execute=args.execute,
        subject_aliases=aliases,
    )
    result["mode"] = "execute" if args.execute else "dry-run"
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
