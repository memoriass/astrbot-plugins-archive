from __future__ import annotations

from typing import Any


class MemoryKernelProfileMixin:
    def get_person_profile(
        self,
        scope_id: str = "global",
        user_id: str = "",
        limit: int | float | str | None = 20,
    ) -> dict[str, Any]:
        safe_limit = self._limit(limit, 20, 80)
        scope = self._scope(scope_id)
        person = self._person(user_id, scope)
        query = user_id or "user:"
        semantics = self._profile_semantics(scope, query, safe_limit)
        relation_node = user_id or "plana:core"
        relations = self.runtime.storage.related_edges(relation_node, safe_limit, scope)
        preference_count = sum(1 for item in semantics if item.predicate == "preference")
        promise_count = sum(1 for item in semantics if item.predicate == "promise")
        return {
            "scope": scope,
            "user_id": user_id,
            "person": person.to_dict() if person else None,
            "person_summary": person.summary_text() if person else "",
            "summary": {
                "semantic_items": len(semantics),
                "relationship_edges": len(relations),
                "preferences": preference_count,
                "promises": promise_count,
            },
            "semantics": semantics,
            "relations": relations,
            "evidence": self._profile_evidence(scope, user_id, safe_limit),
            "snapshots": self._profile_snapshots(scope, user_id, 5),
        }

    def capture_person_profile_snapshot(
        self,
        scope_id: str,
        user_id: str,
        *,
        source: str = "memory_kernel",
    ) -> dict[str, Any]:
        store = getattr(self.runtime, "profile_evidence_storage", None)
        if store is None or not user_id:
            return {"snapshot_id": 0, "skipped": "profile_evidence_unavailable"}
        profile = self.get_person_profile(scope_id, user_id, 20)
        snapshot_id = store.snapshot(
            scope_id=profile["scope"],
            user_id=user_id,
            summary=str(profile.get("person_summary") or ""),
            profile=profile.get("person"),
            semantic_count=int(profile["summary"].get("semantic_items", 0)),
            relation_count=int(profile["summary"].get("relationship_edges", 0)),
            source=source,
        )
        return {"snapshot_id": snapshot_id, "scope": profile["scope"]}

    def _person(self, user_id: str, scope_id: str) -> Any | None:
        if not user_id:
            return None
        person = self.runtime.person_info_storage.get(user_id, scope_id)
        if person is None and scope_id != "global":
            person = self.runtime.person_info_storage.get(user_id, "global")
        return person

    def _profile_semantics(
        self,
        scope: str,
        query: str,
        limit: int,
    ) -> list[Any]:
        items = list(self.runtime.storage.search_semantics(scope, query, limit))
        if scope != "global" and len(items) < limit:
            items.extend(
                self.runtime.storage.search_semantics(
                    "global",
                    query,
                    limit - len(items),
                )
            )
        seen: set[tuple[str, str]] = set()
        result = []
        for item in items:
            key = (
                str(getattr(item, "subject", "")),
                str(getattr(item, "predicate", "")),
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
            if len(result) >= limit:
                break
        return result

    def _profile_evidence(
        self,
        scope: str,
        user_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        store = getattr(self.runtime, "profile_evidence_storage", None)
        if store is None:
            return []
        safe_limit = min(limit, 20)
        evidence = store.recent_evidence(scope, user_id, safe_limit)
        if scope != "global" and len(evidence) < safe_limit:
            evidence.extend(
                store.recent_evidence(
                    "global",
                    user_id,
                    safe_limit - len(evidence),
                )
            )
        return self._dedupe_profile_rows(evidence, safe_limit)

    def _profile_snapshots(
        self,
        scope: str,
        user_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        store = getattr(self.runtime, "profile_evidence_storage", None)
        if store is None:
            return []
        snapshots = store.recent_snapshots(scope, user_id, limit)
        if scope != "global" and len(snapshots) < limit:
            snapshots.extend(
                store.recent_snapshots(
                    "global",
                    user_id,
                    limit - len(snapshots),
                )
            )
        return self._dedupe_profile_rows(snapshots, limit)

    @staticmethod
    def _dedupe_profile_rows(
        rows: list[dict[str, Any]], limit: int
    ) -> list[dict[str, Any]]:
        seen: set[tuple[Any, ...]] = set()
        result: list[dict[str, Any]] = []
        for row in rows:
            key = (
                row.get("scope_id"),
                row.get("user_id"),
                row.get("kind") or row.get("source"),
                row.get("subject") or row.get("summary"),
                row.get("predicate"),
                row.get("object_value"),
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(row)
            if len(result) >= limit:
                break
        return result
