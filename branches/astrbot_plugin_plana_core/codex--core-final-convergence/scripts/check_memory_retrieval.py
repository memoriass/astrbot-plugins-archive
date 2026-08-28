from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import types
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
PKG = "astrbot_plugin_plana_core"


def _ensure_package(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]  # type: ignore[attr-defined]
    sys.modules[name] = module


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"load_failed={path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_ensure_package(PKG, ROOT)
_ensure_package(f"{PKG}.plugin", ROOT / "plugin")
_ensure_package(f"{PKG}.memory", ROOT / "memory")
_load(f"{PKG}.plugin.db", ROOT / "plugin" / "db.py")
_load(f"{PKG}.memory.models", ROOT / "memory" / "models.py")
_load(f"{PKG}.memory.audit", ROOT / "memory" / "audit.py")
_load(f"{PKG}.memory.search_index", ROOT / "memory" / "search_index.py")
storage_module = _load(f"{PKG}.memory.storage", ROOT / "memory" / "storage.py")
maintenance_module = _load(
    f"{PKG}.memory.maintenance", ROOT / "memory" / "maintenance.py"
)
recall_module = _load(f"{PKG}.memory.recall", ROOT / "memory" / "recall.py")
db_module = sys.modules[f"{PKG}.plugin.db"]

Database = db_module.Database
MemoryStorage = storage_module.MemoryStorage
MemoryMaintenance = maintenance_module.MemoryMaintenance
PlanaRecallEngine = recall_module.PlanaRecallEngine


class StorageFacade:
    def __init__(self, db, memory_storage) -> None:
        self.db = db
        self.memory_storage = memory_storage

    def search_memories(self, scope: str, query: str, limit: int):
        return self.memory_storage.search_memories(scope, query, limit)

    def search_memories_by_kind(self, scope: str, query: str, kind: str, limit: int):
        return self.memory_storage.search_memories_by_kind(scope, query, kind, limit)

    def recent_memories(self, scope: str, limit: int):
        return self.memory_storage.recent_memories(scope, limit)

    def recent_memories_by_kind(self, scope: str, kind: str, limit: int):
        return self.memory_storage.recent_memories_by_kind(scope, kind, limit)

    def search_atoms(self, scope: str, query: str, limit: int, atom_type: str = ""):
        return self.memory_storage.search_atoms(scope, query, limit, atom_type)

    def recent_atoms(self, scope: str, limit: int, atom_type: str = ""):
        return self.memory_storage.recent_atoms(scope, limit, atom_type)

    def search_semantics(self, _scope: str, _query: str, _limit: int):
        return []

    def table_counts(self) -> dict[str, int]:
        return {}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def _create_maintenance_tables(db) -> None:
    with db.connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS concept_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                strength INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS task_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope_id TEXT NOT NULL,
                status TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            );
            """
        )


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="plana-memory-retrieval-"))
    try:
        db = Database(tmp / "plana.sqlite3")
        memory_storage = MemoryStorage(db)
        memory_storage.initialize()
        _create_maintenance_tables(db)
        storage = StorageFacade(db, memory_storage)
        runtime = SimpleNamespace(
            storage=storage,
            concept_graph=SimpleNamespace(
                storage=SimpleNamespace(load_all_nodes=lambda: [])
            ),
        )

        memory_storage.add_memory(
            "scope",
            "scope",
            "user_fact",
            "User likes vector index diagnostics and precise recall plans.",
            0.9,
            "test",
        )
        memory_storage.add_memory(
            "scope",
            "scope",
            "user_fact",
            "User likes vector index diagnostics and precise recall plans.",
            0.8,
            "test",
        )
        memory_storage.add_memory(
            "scope",
            "scope",
            "user_preference",
            "用户喜欢蓝色主题与记忆画布。",
            0.7,
            "test",
        )
        memory_storage.add_memory(
            "scope",
            "other",
            "user_fact",
            "Other scope should not leak into retrieval.",
            1.0,
            "test",
        )

        sparse = memory_storage.search_memories("scope", "vector diagnostics", 5)
        require(sparse and sparse[0].scope_id == "scope", f"sparse={sparse}")
        first_memory_id = sparse[0].id
        atoms = memory_storage.atoms_for_memory(first_memory_id)
        require(atoms and atoms[0].status == "active", f"atoms={atoms}")
        atom_hits = memory_storage.search_atoms("scope", "vector diagnostics", 5)
        require(
            atom_hits and atom_hits[0].parent_memory_id == first_memory_id,
            f"atom_hits={atom_hits}",
        )
        old_expires = atom_hits[0].expires_at
        reinforced = memory_storage.reinforce_atom(atom_hits[0].id, confidence=0.95)
        require(reinforced, f"reinforced={reinforced}")
        reinforced_atom = memory_storage.atoms_for_memory(first_memory_id)[0]
        require(
            reinforced_atom.reinforcement_count == 1,
            f"reinforced_atom={reinforced_atom}",
        )
        require(
            reinforced_atom.expires_at > old_expires,
            f"expires={old_expires}->{reinforced_atom.expires_at}",
        )
        chinese = memory_storage.search_memories_by_kind(
            "scope", "蓝色主题", "user_preference", 5
        )
        require(len(chinese) == 1, f"chinese={chinese}")

        maintenance = MemoryMaintenance(SimpleNamespace(storage=storage))
        rebuilt = maintenance.rebuild_indexes()
        require(rebuilt["ok"], f"rebuilt={rebuilt}")
        sparse_after = memory_storage.search_memories("scope", "vector diagnostics", 5)
        require(len(sparse_after) >= 2, f"sparse_after={sparse_after}")

        recall = PlanaRecallEngine(runtime, include_semantic=False, include_concept=False)
        fused = recall.recall("scope", "vector diagnostics 蓝色主题", "", 5)
        require(fused["explain"]["fusion"] == "reciprocal_rank_fusion+mmr", fused)
        require(fused["routes"].get("atom", 0) >= 1, f"atom_route={fused}")
        atom_result = next(
            (item for item in fused["results"] if item["route"] == "atom"),
            None,
        )
        require(atom_result is not None, f"atom_result={fused}")
        atom_meta = atom_result["metadata"]
        require("temporal_score" in atom_meta, f"atom_meta={atom_meta}")
        require("final_score" in atom_meta, f"atom_meta={atom_meta}")
        contents = [item["content"] for item in fused["results"]]
        require(any("蓝色主题" in item for item in contents), f"mmr={contents}")

        with db.connect() as conn:
            conn.execute(
                "UPDATE memory_atoms SET expires_at=? WHERE id=?",
                (1, atom_hits[0].id),
            )
        expired = memory_storage.expire_stale_atoms("scope")
        require(expired >= 1, f"expired={expired}")
        forgotten = memory_storage.forget_expired_atoms(0, "scope")
        require(forgotten >= 1, f"forgotten={forgotten}")

        deleted = memory_storage.delete_memory(sparse_after[0].id, actor="test")
        require(deleted["ok"], f"deleted={deleted}")
        with db.connect() as conn:
            orphan_count = int(
                conn.execute(
                    """
                    SELECT COUNT(*) FROM episodic_memories_fts f
                    LEFT JOIN episodic_memories m ON m.id=f.memory_id
                    WHERE m.id IS NULL
                    """
                ).fetchone()[0]
            )
            atom_orphan_count = int(
                conn.execute(
                    """
                    SELECT COUNT(*) FROM memory_atoms_fts f
                    LEFT JOIN memory_atoms a ON a.id=f.atom_id
                    WHERE a.id IS NULL OR a.status='forgotten'
                    """
                ).fetchone()[0]
            )
        require(orphan_count == 0, f"orphan_count={orphan_count}")
        require(atom_orphan_count == 0, f"atom_orphan_count={atom_orphan_count}")
        print("memory_retrieval_check=ok")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
