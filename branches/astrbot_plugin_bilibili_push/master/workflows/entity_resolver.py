from __future__ import annotations

from dataclasses import dataclass

from astrbot.api import logger

from ..database.aliases import normalize_alias
from .resolver_stats import record_resolver_event
from .runtime import event_origin
from .utils import is_uid


MIN_CONFIDENCE = 0.84
MIN_MARGIN = 0.03
SHARED_ALIAS_BASE_CONFIDENCE = 0.88
SHARED_ALIAS_MIN_TARGETS = 2


@dataclass(frozen=True, slots=True)
class ResolvedUp:
    uid: str
    username: str
    face: str = ""
    confidence: float = 0.0
    source: str = ""
    alias: str = ""
    reason: str = ""

    def as_candidate(self) -> dict:
        return {
            "uid": self.uid,
            "username": self.username or self.uid,
            "face": self.face,
            "follower": None,
        }


@dataclass(frozen=True, slots=True)
class ResolverCandidate:
    uid: str
    username: str
    face: str
    confidence: float
    source: str
    alias: str
    reason: str
    layer_rank: int

    def to_resolved(self) -> ResolvedUp:
        return ResolvedUp(
            uid=self.uid,
            username=self.username or self.uid,
            face=self.face,
            confidence=self.confidence,
            source=self.source,
            alias=self.alias,
            reason=self.reason,
        )


async def resolve_up_reference(plugin, event, query: str) -> ResolvedUp | None:
    text = str(query or "").strip()
    if not text:
        record_resolver_event(plugin, "miss")
        return None
    if is_uid(text):
        record_resolver_event(plugin, "uid", source="uid", confidence=1.0)
        return ResolvedUp(
            text,
            text,
            confidence=1.0,
            source="uid",
            alias=text,
            reason="用户输入是明确 UID",
        )

    target_id = event_origin(event)
    candidates = resolve_up_candidates(plugin, target_id, text)
    resolved = select_resolver_candidate(candidates)
    if resolved:
        outcome = _resolver_outcome(resolved.source)
        record_resolver_event(
            plugin,
            outcome,
            source=resolved.source,
            confidence=resolved.confidence,
        )
        _touch_alias_if_needed(plugin, target_id, text, resolved)
        return resolved

    if candidates:
        record_resolver_event(plugin, "ambiguous", confidence=candidates[0].confidence)
    else:
        record_resolver_event(plugin, "miss")
    return None


def resolve_up_candidates(plugin, target_id: str, query: str) -> list[ResolverCandidate]:
    candidates: list[ResolverCandidate] = []
    for collector in (
        _current_subscription_candidates,
        _alias_candidates,
        _shared_alias_candidates,
    ):
        try:
            candidates.extend(collector(plugin, target_id, query))
        except Exception as exc:
            record_resolver_event(plugin, "error", source=collector.__name__)
            logger.warning(
                f"UP 解析层 {collector.__name__} 失败，已跳过：{exc}",
                exc_info=True,
            )
    return _dedupe_candidates(candidates)


def select_resolver_candidate(candidates: list[ResolverCandidate]) -> ResolvedUp | None:
    if not candidates:
        return None
    ranked = sorted(candidates, key=_candidate_sort_key, reverse=True)
    top = ranked[0]
    if top.confidence < MIN_CONFIDENCE:
        return None
    runner_up = next((item for item in ranked[1:] if item.uid != top.uid), None)
    if runner_up and top.confidence - runner_up.confidence < MIN_MARGIN:
        return None
    return top.to_resolved()


def learn_up_alias(
    plugin,
    event,
    alias: str,
    candidate: dict,
    *,
    source: str = "confirmed_subscription",
) -> None:
    raw_alias = str(alias or "").strip()
    uid = str(candidate.get("uid") or candidate.get("mid") or "").strip()
    username = str(candidate.get("username") or candidate.get("uname") or "").strip()
    face = str(candidate.get("face") or candidate.get("upic") or "").strip()
    if not raw_alias or not uid or is_uid(raw_alias):
        return

    target_id = event_origin(event)
    plugin.db.upsert_up_alias(
        alias=raw_alias,
        uid=uid,
        username=username,
        face=face,
        target_id=target_id,
        source=source,
        confidence=1.0,
    )
    plugin.db.upsert_up_alias_evidence(
        alias=raw_alias,
        uid=uid,
        username=username,
        face=face,
        target_id=target_id,
        source=source,
    )
    if username:
        plugin.db.upsert_up_alias(
            alias=username,
            uid=uid,
            username=username,
            face=face,
            target_id="",
            source="username",
            confidence=0.95,
        )


def _current_subscription_candidates(plugin, target_id: str, query: str) -> list[ResolverCandidate]:
    wanted = normalize_alias(query)
    if not wanted:
        return []
    candidates: list[ResolverCandidate] = []
    for sub in plugin.db.get_subscriptions(target_id):
        fields = [
            ("uid", sub.uid),
            ("用户名", sub.username),
            *[("标签", tag) for tag in (sub.tags or [])],
        ]
        for label, value in fields:
            normalized = normalize_alias(value)
            score, reason = _match_score(wanted, normalized, label)
            if score <= 0:
                continue
            candidates.append(
                ResolverCandidate(
                    uid=str(sub.uid),
                    username=str(sub.username or sub.uid),
                    face="",
                    confidence=score,
                    source="current_subscription",
                    alias=query,
                    reason=reason,
                    layer_rank=30,
                )
            )
    return candidates


def _alias_candidates(plugin, target_id: str, query: str) -> list[ResolverCandidate]:
    rows = plugin.db.find_up_aliases(query, target_id=target_id, limit=5)
    candidates: list[ResolverCandidate] = []
    for row in rows:
        scope = "当前会话" if row.get("target_id") == target_id else "全局用户名"
        confidence = float(row.get("confidence") or 0)
        if row.get("target_id") != target_id:
            confidence = min(confidence, 0.9)
        candidates.append(
            ResolverCandidate(
                uid=str(row["uid"]),
                username=str(row.get("username") or row["uid"]),
                face=str(row.get("face") or ""),
                confidence=confidence,
                source=f"alias:{row.get('source') or 'unknown'}",
                alias=query,
                reason=f"{scope}历史映射命中“{row.get('alias') or query}”",
                layer_rank=20 if row.get("target_id") == target_id else 10,
            )
        )
    return candidates


def _shared_alias_candidates(plugin, target_id: str, query: str) -> list[ResolverCandidate]:
    min_targets = int(getattr(plugin, "shared_alias_min_targets", SHARED_ALIAS_MIN_TARGETS))
    rows = plugin.db.find_shared_up_aliases(query, min_targets=min_targets, limit=5)
    candidates: list[ResolverCandidate] = []
    for row in rows:
        confidence = _shared_alias_confidence(row)
        source = "alias:shared_conflict" if row.get("conflict_count") else "alias:shared"
        reason = _shared_alias_reason(row, query)
        candidates.append(
            ResolverCandidate(
                uid=str(row["uid"]),
                username=str(row.get("username") or row["uid"]),
                face=str(row.get("face") or ""),
                confidence=confidence,
                source=source,
                alias=query,
                reason=reason,
                layer_rank=12 if not row.get("conflict_count") else 6,
            )
        )
    return candidates


def _dedupe_candidates(candidates: list[ResolverCandidate]) -> list[ResolverCandidate]:
    best_by_uid: dict[str, ResolverCandidate] = {}
    for candidate in candidates:
        current = best_by_uid.get(candidate.uid)
        if current is None or _candidate_sort_key(candidate) > _candidate_sort_key(current):
            best_by_uid[candidate.uid] = candidate
    return sorted(best_by_uid.values(), key=_candidate_sort_key, reverse=True)


def _candidate_sort_key(candidate: ResolverCandidate) -> tuple[float, int]:
    return (candidate.confidence, candidate.layer_rank)


def _match_score(query: str, candidate: str, label: str) -> tuple[float, str]:
    if not query or not candidate:
        return 0.0, ""
    if query == candidate:
        score = 0.99 if label == "uid" else 0.97
        return score, f"当前订阅{label}完全匹配"
    if len(query) >= 2 and query in candidate:
        return 0.9, f"当前订阅{label}包含该称呼"
    if len(candidate) >= 2 and candidate in query:
        return 0.88, f"用户称呼包含当前订阅{label}"
    return 0.0, ""


def _shared_alias_confidence(row: dict) -> float:
    target_count = int(row.get("target_count") or 0)
    confirm_count = int(row.get("confirm_count") or 0)
    if int(row.get("conflict_count") or 0) > 0:
        return min(0.80, 0.72 + min(target_count, 4) * 0.02)
    bonus = min(max(target_count - 2, 0), 5) * 0.01
    repeat_bonus = min(max(confirm_count - target_count, 0), 5) * 0.004
    return min(0.92, SHARED_ALIAS_BASE_CONFIDENCE + bonus + repeat_bonus)


def _shared_alias_reason(row: dict, query: str) -> str:
    target_count = int(row.get("target_count") or 0)
    confirm_count = int(row.get("confirm_count") or 0)
    conflict_count = int(row.get("conflict_count") or 0)
    if conflict_count:
        return (
            f"跨会话别名“{query}”有 {target_count} 个会话确认过该 UID，"
            f"但存在 {conflict_count} 个竞争 UID"
        )
    return f"跨会话别名“{query}”已有 {target_count} 个会话、{confirm_count} 次确认"


def _resolver_outcome(source: str) -> str:
    if source == "alias:shared":
        return "shared_alias"
    if source.startswith("alias:"):
        return "alias"
    return source


def _touch_alias_if_needed(plugin, target_id: str, query: str, resolved: ResolvedUp) -> None:
    if resolved.source == "alias:shared":
        plugin.db.touch_up_alias_evidence(query, resolved.uid)
        return
    if not resolved.source.startswith("alias:"):
        return
    plugin.db.touch_up_alias(query, resolved.uid, target_id)
    plugin.db.touch_up_alias(query, resolved.uid, "")
