from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass
import hashlib
import json
import re
from time import time
from typing import Any
import uuid

try:
    from ..plugin.gallery import GalleryCandidate, GalleryEmotionTarget
    from .gallery_emotions import display_emotions, emotion_facets, target_payload
except ImportError:  # pragma: no cover - standalone checks
    from plugin.gallery import GalleryCandidate, GalleryEmotionTarget
    from gallery_emotions import display_emotions, emotion_facets, target_payload

_DENY = re.compile(
    r"(?:代码|接口|api|报错|日志|配置|数据库|命令|架构|服务器|网络|ssh|"
    r"下载|安装|重启|部署|测试|总结|报告|识别|ocr|生成|重画|编辑|绘制|"
    r"删除|清空|密码|密钥|token|隐私|越权|销毁|威胁|事故|报警|告警|"
    r"死亡|去世|葬礼|自杀|伤害|严重|崩溃|失败|超时|申诉|封号|"
    r"二维码|登录|新闻|商品|价格|餐厅|菜品|推荐)",
    re.I,
)
_EXPLICIT = re.compile(r"(?:来|发|给).{0,4}(?:张|个)?(?:图|图片|表情包|反应图)|配个图", re.I)
_EMOTIONAL = re.compile(
    r"(?:哈哈|笑死|好耶|太棒|牛啊|厉害|绝了|离谱|绷不住|无语|震惊|啊这|"
    r"真的假的|懂了|确实|同意|早安|晚安|谢谢|对不起|抱歉|庆祝|"
    r"嘿嘿|好呀|甜甜|不可以|才不要|不能哦|怎么啦|[😂😱👏🤔])",
    re.I,
)


@dataclass(frozen=True, slots=True)
class GalleryContextIntent:
    request_id: str
    query: str
    facets: tuple[str, ...]
    emotions: tuple[GalleryEmotionTarget, ...]
    cooldown_key: str
    explicit_request: bool = False


@dataclass(frozen=True, slots=True)
class GalleryGateDecision:
    request_id: str
    reason: str
    intent: GalleryContextIntent | None = None


@dataclass(frozen=True, slots=True)
class GallerySelection:
    asset_ref: str
    confidence: float
    reason: str


@dataclass(slots=True)
class PendingGalleryReaction:
    intent: GalleryContextIntent
    response_text: str
    source_message_id: str
    is_private: bool
    platform: str
    reply_supported: bool | None = None
    consumed: bool = False


class GalleryContextPolicy:
    def __init__(self, config: dict[str, Any], state_store: Any | None = None) -> None:
        self.send_enabled = bool(config.get("enable_gallery_chat_images", False))
        self.shadow_enabled = bool(config.get("assistant_xiaowei_replay_shadow", True))
        self.enabled = self.send_enabled or self.shadow_enabled
        self.selector_mode = str(config.get("gallery_selector_mode", "hybrid") or "hybrid")
        self.frequency_mode = str(
            config.get("gallery_reaction_frequency_mode", "natural") or "natural"
        ).strip().lower()
        self.direct_score = float(config.get("gallery_direct_select_score", 50) or 50)
        self.direct_margin = float(config.get("gallery_direct_select_margin", 12) or 12)
        self.delivery_delay_ms = max(
            0, min(int(config.get("gallery_delivery_delay_ms", 350) or 350), 5000)
        )
        self.scope_allowlist = {
            item.strip()
            for item in str(config.get("gallery_reaction_scope_allowlist", "") or "").split(",")
            if item.strip()
        }
        self.threshold = max(
            0.0, min(float(config.get("gallery_selector_threshold", 0.75) or 0.75), 1.0)
        )
        self.group_cooldown = max(
            0, int(config.get("gallery_group_cooldown_seconds", 300) or 300)
        )
        self.private_cooldown = max(
            0, int(config.get("gallery_private_cooldown_seconds", 180) or 180)
        )
        self.timeout_seconds = max(
            0.3, min(float(config.get("gallery_timeout_seconds", 2) or 2), 5.0)
        )
        self.inflight_lease_seconds = max(
            5, min(int(config.get("gallery_inflight_lease_seconds", 30) or 30), 300)
        )
        self.frequency_window_size = max(
            5, min(int(config.get("gallery_reaction_window_size", 20) or 20), 100)
        )
        self.frequency_window_max = max(
            1,
            min(
                int(config.get("gallery_reaction_window_max", 6) or 6),
                self.frequency_window_size,
            ),
        )
        self._state_store = state_store
        self._last_sent: dict[str, float] = {}
        self._recent: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=20))
        self._loaded: set[str] = set()
        self._inflight: dict[str, float] = {}
        self._frequency_history: dict[str, deque[bool]] = defaultdict(
            lambda: deque(maxlen=self.frequency_window_size)
        )
        self._recent_emotions: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=4))

    def evaluate(
        self,
        event: Any,
        user_text: str,
        response_text: str,
        mood_emotion: Any | None = None,
    ) -> GalleryGateDecision:
        request_id = _request_id(event)
        if not self.enabled or not user_text.strip() or not response_text.strip():
            return GalleryGateDecision(request_id, "disabled_or_empty")
        behavior = getattr(event, "_plana_behavior_decision", None)
        action = str(getattr(behavior, "action", "direct_answer") or "direct_answer")
        if action not in {"direct_answer", "silence"}:
            return GalleryGateDecision(request_id, f"behavior:{action}")
        combined_text = f"{user_text} {response_text}"
        if user_text.lstrip().startswith("/") or _DENY.search(combined_text):
            return GalleryGateDecision(request_id, "blocked_context")
        explicit_request = bool(_EXPLICIT.search(user_text))
        emotions = tuple(display_emotions(combined_text, mood_emotion))
        if not (explicit_request or emotions or _EMOTIONAL.search(combined_text)):
            return GalleryGateDecision(request_id, "no_reaction_signal")
        scope_id = str(getattr(event, "unified_msg_origin", "") or "global")
        if self.scope_allowlist and scope_id not in self.scope_allowlist:
            return GalleryGateDecision(request_id, "scope_not_allowed")
        is_private = _is_private(event)
        actor_id = _actor_id(event)
        cooldown_key = f"private:{scope_id}:{actor_id}" if is_private else f"group:{scope_id}"
        cooldown = self.private_cooldown if is_private else self.group_cooldown
        self._restore(cooldown_key)
        self._expire_inflight()
        if cooldown_key in self._inflight:
            return GalleryGateDecision(request_id, "inflight")
        if time() - self._last_sent.get(cooldown_key, 0.0) < cooldown:
            return GalleryGateDecision(request_id, "cooldown")
        facets = tuple(emotion_facets(combined_text, emotions))
        self._inflight[cooldown_key] = time()
        intent = GalleryContextIntent(
            request_id=request_id,
            query=f"{user_text[:240]} {response_text[:240]}",
            facets=facets,
            emotions=emotions,
            cooldown_key=cooldown_key,
            explicit_request=explicit_request,
        )
        return GalleryGateDecision(request_id, "allowed", intent)

    def intent(self, event: Any, user_text: str, response_text: str) -> GalleryContextIntent | None:
        return self.evaluate(event, user_text, response_text).intent

    def excluded_refs(self, intent: GalleryContextIntent) -> list[str]:
        return list(self._recent[intent.cooldown_key])

    def should_request_candidates(self, intent: GalleryContextIntent) -> bool:
        if intent.explicit_request:
            return True
        confidence = max((item.confidence for item in intent.emotions), default=0.0)
        has_context_facets = any(
            facet.startswith(("tone:", "scene:")) for facet in intent.facets
        )
        probability = _base_frequency_probability(
            self.frequency_mode,
            confidence,
            has_context_facets,
        )
        if self.frequency_mode in {"always", "active"}:
            return True
        history = self._frequency_history[intent.cooldown_key]
        if sum(history) >= self.frequency_window_max:
            history.append(False)
            return False
        primary = next(
            (item.emotion_tag for item in intent.emotions if item.prominence == "primary"),
            "",
        )
        recent_emotions = self._recent_emotions[intent.cooldown_key]
        if primary and recent_emotions:
            repeated = sum(1 for item in list(recent_emotions)[-2:] if item == primary)
            probability *= 0.35 if repeated >= 2 else 0.65 if repeated == 1 else 1.0
        if len(history) >= 8:
            density = sum(history) / len(history)
            if density >= self.frequency_window_max / self.frequency_window_size:
                probability *= 0.35
            elif density >= 0.25:
                probability *= 0.70
        if probability <= 0.0:
            history.append(False)
            return False
        digest = hashlib.sha256(f"gallery-frequency:{intent.request_id}".encode()).digest()
        sample = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
        allowed = sample < probability
        history.append(allowed)
        return allowed

    async def select(
        self,
        provider: Any,
        intent: GalleryContextIntent,
        candidates: list[GalleryCandidate],
    ) -> GallerySelection | None:
        direct = self._direct_selection(intent, candidates)
        if direct is not None and self.selector_mode in {"hybrid", "rule", "rules"}:
            return direct
        if self.selector_mode in {"rule", "rules"}:
            return None
        model = _provider(provider)
        if model is None or not hasattr(model, "text_chat") or not candidates:
            return None
        allowed = {candidate.asset_ref for candidate in candidates}
        rows = [
            {
                "asset_ref": item.asset_ref,
                "caption": item.caption,
                "tags": list(item.tags),
                "emotions": [
                    {
                        "emotion_tag": emotion.emotion_tag,
                        "intensity": emotion.intensity,
                        "prominence": emotion.prominence,
                    }
                    for emotion in item.emotions
                ],
                "matched_emotions": list(item.matched_emotions),
                "score_breakdown": item.score_breakdown,
                "retrieval_score": item.score,
            }
            for item in candidates
        ]
        prompt = (
            "Choose at most one local reaction image that improves this chat reply. "
            "Return strict JSON only: "
            '{"asset_ref":"gallery:...|none","confidence":0.0,"reason":"..."}. '
            "Choose only from the supplied asset_ref values. Prefer no image when the fit "
            "is approximate, factual, serious, repetitive, or potentially insensitive.\n"
            f"Target emotions: {json.dumps([target_payload(item) for item in intent.emotions], ensure_ascii=False)}\n"
            f"Context: {intent.query}\nCandidates: {json.dumps(rows, ensure_ascii=False)}"
        )
        try:
            response = await asyncio.wait_for(
                model.text_chat(
                    prompt=prompt,
                    system_prompt=(
                        "You are a conservative local reaction-image selector. "
                        "You cannot invent assets and must return JSON only."
                    ),
                ),
                timeout=self.timeout_seconds,
            )
        except Exception:  # noqa: BLE001
            return None
        payload = _json(str(getattr(response, "completion_text", "") or ""))
        if not isinstance(payload, dict):
            return None
        asset_ref = str(payload.get("asset_ref") or "").strip()
        confidence = _confidence(payload.get("confidence"))
        if asset_ref not in allowed or confidence < self.threshold:
            return None
        return GallerySelection(
            asset_ref=asset_ref,
            confidence=confidence,
            reason=str(payload.get("reason") or "model_selected")[:200],
        )

    def _direct_selection(
        self,
        intent: GalleryContextIntent,
        candidates: list[GalleryCandidate],
    ) -> GallerySelection | None:
        if not candidates:
            return None
        top = candidates[0]
        second_score = candidates[1].score if len(candidates) > 1 else 0.0
        requested = set(intent.facets)
        matched = requested.intersection(top.matched_facets or top.tags)
        primary = next(
            (item.emotion_tag for item in intent.emotions if item.prominence == "primary"),
            "",
        )
        emotion_coverage = float(top.score_breakdown.get("emotion_coverage", 0.0)) / 35.0
        emotion_ready = (
            not intent.emotions
            or (
                primary in set(top.matched_emotions or top.matched_facets or top.tags)
                and emotion_coverage >= 0.7
            )
        )
        if (
            matched
            and emotion_ready
            and top.score >= self.direct_score
            and top.score - second_score >= self.direct_margin
        ):
            return GallerySelection(
                asset_ref=top.asset_ref,
                confidence=1.0,
                reason="rule_direct",
            )
        return None

    def mark_delivered(self, intent: GalleryContextIntent, asset_ref: str) -> None:
        delivered_at = time()
        self._last_sent[intent.cooldown_key] = delivered_at
        self._recent[intent.cooldown_key].append(asset_ref)
        primary = next(
            (item.emotion_tag for item in intent.emotions if item.prominence == "primary"),
            "",
        )
        if primary:
            self._recent_emotions[intent.cooldown_key].append(primary)
        self._inflight.pop(intent.cooldown_key, None)
        if self._state_store is not None:
            self._state_store.mark_delivered(intent.cooldown_key, asset_ref, delivered_at)

    def release(self, intent: GalleryContextIntent) -> None:
        self._inflight.pop(intent.cooldown_key, None)

    def release_all(self) -> None:
        self._inflight.clear()

    def _expire_inflight(self) -> None:
        cutoff = time() - self.inflight_lease_seconds
        expired = [key for key, reserved_at in self._inflight.items() if reserved_at < cutoff]
        for key in expired:
            self._inflight.pop(key, None)

    def _restore(self, cooldown_key: str) -> None:
        if cooldown_key in self._loaded or self._state_store is None:
            return
        last_sent, recent = self._state_store.load(cooldown_key)
        self._last_sent[cooldown_key] = last_sent
        self._recent[cooldown_key].extend(recent[-20:])
        self._loaded.add(cooldown_key)


def _provider(provider: Any) -> Any:
    if isinstance(provider, dict):
        return provider.get("preflight") or provider.get("default") or provider.get("planner")
    return provider


def _base_frequency_probability(
    mode: str,
    confidence: float,
    has_context_facets: bool,
) -> float:
    if mode in {"always", "active"}:
        return 1.0
    if mode in {"conservative", "low"}:
        return (
            0.35 if confidence >= 0.85
            else 0.15 if confidence >= 0.65
            else 0.08 if has_context_facets
            else 0.0
        )
    return (
        0.70 if confidence >= 0.85
        else 0.45 if confidence >= 0.65
        else 0.20 if has_context_facets
        else 0.0
    )


def _is_private(event: Any) -> bool:
    checker = getattr(event, "is_private_chat", None)
    if callable(checker):
        try:
            return bool(checker())
        except Exception:  # noqa: BLE001
            return False
    return False


def _actor_id(event: Any) -> str:
    getter = getattr(event, "get_sender_id", None)
    if callable(getter):
        try:
            return str(getter() or "user")
        except Exception:  # noqa: BLE001
            return "user"
    return "user"


def _request_id(event: Any) -> str:
    message_obj = getattr(event, "message_obj", None)
    source_message_id = str(getattr(message_obj, "message_id", "") or "").strip()
    actor_id = _actor_id(event)
    return (
        f"gallery:{source_message_id}:{actor_id}"[:160]
        if source_message_id
        else uuid.uuid4().hex
    )


def _json(raw: str) -> Any:
    text = raw.strip().strip("`")
    if text.lower().startswith("json"):
        text = text[4:].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None


def _confidence(value: Any) -> float:
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return 0.0
