from __future__ import annotations

from ..plugin.models import RelationEdge, UserIdentity
from ..plugin.storage import PlanaStorage


class RelationGraph:
    def __init__(self, storage: PlanaStorage):
        self.storage = storage

    # ------------------------------------------------------------------
    # Public observers
    # ------------------------------------------------------------------

    def observe_interaction(
        self,
        identity: UserIdentity,
        text: str,
        scope_id: str,
    ) -> None:
        """Observe a user message and update relation edges.

        Two relation types are maintained:
        - ``tool_operator``: user explicitly addressed Plana (high signal).
        - ``frequent_user``: any interaction, weight accumulates over time
          (borrows a person_info / interaction-frequency idea).
        """
        normalized = text.strip().lower()
        if not normalized:
            return

        # Frequent-user relation: record every interaction with a lower weight.
        # Each upsert merges via INSERT OR REPLACE so weight reflects recency.
        self.storage.upsert_relation(
            source_id=identity.global_user_id,
            target_id="plana:core",
            relation_type="frequent_user",
            weight=0.30,
            confidence=0.5,
            evidence=f"interaction:{scope_id}",
            scope_id=scope_id,
        )

        # Explicit-signal relation: user directly invoked Plana.
        if self._is_explicit_signal(normalized):
            self.storage.upsert_relation(
                source_id="plana:core",
                target_id=identity.global_user_id,
                relation_type="tool_operator",
                weight=0.55,
                confidence=0.7,
                evidence=f"explicit_plana_signal:{scope_id}",
                scope_id=scope_id,
            )

    def observe_plana_signal(
        self,
        identity: UserIdentity,
        text: str,
        scope_id: str,
    ) -> None:
        """Backward-compatible alias for observe_interaction."""
        self.observe_interaction(identity, text, scope_id)

    def active_relations(
        self,
        identity: UserIdentity,
        limit: int,
        scope_id: str = "global",
    ) -> list[RelationEdge]:
        return self.storage.related_edges(identity.global_user_id, limit, scope_id)

    def graph_text(
        self, identity: UserIdentity, limit: int = 8, scope_id: str = "global"
    ) -> str:
        edges = self.active_relations(identity, limit, scope_id)
        if not edges:
            return "Plana relation graph: empty"
        lines = ["Plana relation graph:"]
        for edge in edges:
            lines.append(
                f"{edge.id}. {edge.source_id} -[{edge.relation_type}:{edge.weight:.2f}]-> "
                f"{edge.target_id}; confidence={edge.confidence:.2f}; evidence={edge.evidence}"
            )
        return "\n".join(lines)

    def graph_detail_text(
        self, identity: UserIdentity, limit: int = 8, scope_id: str = "global"
    ) -> str:
        edges = self.active_relations(identity, limit, scope_id)
        if not edges:
            return "Plana relation graph detail: empty"
        lines = ["Plana relation graph detail:"]
        for edge in edges:
            lines.append(
                f"id={edge.id}; type={edge.relation_type}; weight={edge.weight:.2f}; "
                f"confidence={edge.confidence:.2f}; source={edge.source_id}; "
                f"target={edge.target_id}"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_explicit_signal(self, normalized: str) -> bool:
        return (
            normalized.startswith("/plana")
            or "普拉娜" in normalized
            or "plana" in normalized
        )
