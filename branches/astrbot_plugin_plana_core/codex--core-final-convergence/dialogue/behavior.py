from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from time import time
from typing import Any, Literal

from ..utils.intent_patterns import (
    looks_like_informational_document_request,
    looks_like_long_task_request,
    native_tool_profile,
)
from .delivery import delivery_context_from_event

BehaviorAction = Literal[
    "silence", "direct_answer", "native_tool", "short_artifact", "codex",
    "clarify", "cancel_or_correct", "reject",
]

_CANCEL_RE = re.compile(r"(?:不要了|算了|停(?:一下|止)?|取消|撤销|别做了|不用了)", re.I)
_CORRECT_RE = re.compile(r"(?:不是这个|搞错了|改成|应该是|重新来|重做|纠正)", re.I)
_ARTIFACT_RESEND_RE = re.compile(r"(?:再发(?:一次|一下)?|重发|没收到|图呢|图片呢|文件呢|二维码呢)", re.I)
_DANGEROUS_RE = re.compile(r"(?:删除|清空|格式化|销毁|rm\s+-rf|修改密码).{0,20}(?:系统|根目录|账号|实例|服务器|文件|目录)?", re.I)
_HELP_RE = re.compile(r"(?:谁能|有没有人|帮我|能不能|怎么查|怎么弄|求助|救命|怎么办)", re.I)
_TIME_SENSITIVE_RE = re.compile(r"(?:掉线|离线|失败|超时|报警|告警|二维码|登录失效)", re.I)
_MEDIA_DOMAINS = re.compile(r"(?:早餐|午餐|晚餐|宵夜|菜|食物|餐厅|番剧|动漫|动画|漫画|电影|新闻|商品|二维码|榜单|推荐)", re.I)
_TECHNICAL = re.compile(r"(?:代码|接口|api|报错|日志|配置|命令|架构|数据库|端口|网络|ssh)", re.I)
_MODEL_ONLY = re.compile(r"(?:不需要|无需|不要).{0,8}(?:后台|执行|工具|搜索)|(?:直接|只).{0,6}(?:告诉|说明|回答)", re.I)


@dataclass(frozen=True, slots=True)
class BehaviorDecision:
    action: BehaviorAction
    confidence: float
    wake_reason: str = ""
    participation_reason: str = ""
    capability: str = ""
    risk_class: str = "ordinary"
    media_intent: str = "text"
    clarification: str = ""
    delivery_context: dict[str, Any] = field(default_factory=dict)
    created_at: int = field(default_factory=lambda: int(time()))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BehaviorOrchestrator:
    """One-pass local behavior decision before dialogue routing."""

    def __init__(self) -> None:
        self._proactive_last_at: dict[tuple[str, str], float] = {}
        self._proactive_daily: dict[tuple[str, str, int], int] = {}

    def decide(self, runtime: Any, event: Any, wake: Any, *, social_state: Any | None = None, session_state: Any | None = None) -> BehaviorDecision:
        text = self._text(event)
        scope_id = str(runtime.resolve_scope(event.unified_msg_origin) or "global")
        actor_id = self._actor_id(runtime, event)
        delivery = delivery_context_from_event(event, scope_id=scope_id, actor_id=actor_id).to_dict()
        media_intent = self._media_intent(text)
        if looks_like_informational_document_request(text):
            return self._decision(
                "direct_answer",
                0.98,
                wake,
                "informational_document_request",
                "ordinary",
                "text",
                delivery,
                capability="document_reference",
            )
        profile = native_tool_profile(text)
        if _MODEL_ONLY.search(text):
            return self._decision("direct_answer", 0.98, wake, "explicit_model_only", "ordinary", "text", delivery, capability="model_only")
        if _DANGEROUS_RE.search(text) and any(marker in text.lower() for marker in ("系统目录", "根目录", "/etc", "/root", "system32", "ssh私钥", "密钥")):
            return self._decision("reject", 0.99, wake, "explicitly_forbidden_target", "destructive", media_intent, delivery)
        if _ARTIFACT_RESEND_RE.search(text):
            return self._decision("short_artifact", 0.98, wake, "artifact_resend_request", "low_risk", "text", delivery, capability="artifact_resend")
        if _CANCEL_RE.search(text) or _CORRECT_RE.search(text):
            return self._decision("cancel_or_correct", 0.96, wake, "task_continuation_intent", "controlled", media_intent, delivery)
        if looks_like_long_task_request(text):
            return self._decision("codex", 0.91, wake, "long_or_multi_step_task", "delegated", media_intent, delivery)
        if profile:
            action: BehaviorAction = "short_artifact" if profile == "download" else "native_tool"
            return self._decision(action, 0.94, wake, f"native_profile:{profile}", "low_risk", media_intent, delivery, capability=profile)
        if not bool(getattr(wake, "should_dispatch", False)):
            if not self._proactive_allowed(runtime, event, text, social_state, session_state):
                return self._decision("silence", 0.95, wake, "no_high_value_opportunity", "ordinary", media_intent, delivery)
            self._record_proactive(runtime, scope_id, actor_id)
            return self._decision("direct_answer", 0.72, wake, "conservative_help_opportunity", "ordinary", media_intent, delivery)
        return self._decision("direct_answer", 0.86, wake, "direct_or_familiar_turn", "ordinary", media_intent, delivery)

    def prompt_block(self, decision: BehaviorDecision, social_state: Any | None) -> str:
        density = str(getattr(social_state, "preferred_density", "balanced") or "balanced")
        address = str(getattr(social_state, "preferred_address", "") or "")
        return (
            "[PLANA_BEHAVIOR]\n"
            f"action={decision.action}; media={decision.media_intent}; response_density={density}; preferred_address={address or 'none'}.\n"
            "像熟悉的日常助理一样说话：自然、直接、有人情味，但不要表演。"
            "先给结果，参数充分时不要反问；除非确实需要等待，不说‘我将调用’‘请稍候’‘执行部门返回’。"
            "不要每段重复称呼用户，默认用‘你’而不是连续使用‘您’‘为您’；普通完成后不要追加‘还需要我做什么吗’。"
            "遇到日常分享时回应内容本身，可以简短关心或接一句自然的话，不要转成任务申请，也不要说‘待命’‘请吩咐’。"
            "小错误直接纠正，失败说明真实原因和一个可执行建议；不要暴露内部 lane、request id、协议名称或路径。"
        )

    def _proactive_allowed(self, runtime: Any, event: Any, text: str, social_state: Any | None, session_state: Any | None) -> bool:
        if str(runtime.config.get("assistant_group_proactive_mode", "conservative")) != "conservative":
            return False
        if not self._is_group(event):
            return True
        tolerance = float(getattr(social_state, "participation_tolerance", 0.35) or 0.35)
        scope_id = str(runtime.resolve_scope(event.unified_msg_origin) or "global")
        actor_id = self._actor_id(runtime, event)
        now = time()
        try:
            cooldown = max(30, int(runtime.config.get("assistant_group_proactive_cooldown_seconds", 300)))
        except (TypeError, ValueError):
            cooldown = 300
        if now - self._proactive_last_at.get((scope_id, actor_id), 0.0) < cooldown:
            return False
        day = int(now // 86400)
        try:
            daily_limit = max(0, int(runtime.config.get("assistant_group_proactive_daily_limit", 8)))
        except (TypeError, ValueError):
            daily_limit = 8
        if self._proactive_daily.get((scope_id, actor_id, day), 0) >= daily_limit:
            return False
        current_goal = str(getattr(session_state, "current_goal", "") or "")
        continuation = bool(current_goal and (_CANCEL_RE.search(text) or _CORRECT_RE.search(text)))
        opportunity = bool(_HELP_RE.search(text) or (_TIME_SENSITIVE_RE.search(text) and current_goal))
        return tolerance >= 0.25 and (continuation or opportunity)

    def _record_proactive(self, runtime: Any, scope_id: str, actor_id: str) -> None:
        now = time()
        self._proactive_last_at[(scope_id, actor_id)] = now
        day_key = (scope_id, actor_id, int(now // 86400))
        self._proactive_daily[day_key] = self._proactive_daily.get(day_key, 0) + 1

    def _media_intent(self, text: str) -> str:
        lowered = text.lower()
        if any(marker in lowered for marker in ("二维码", "qr code", "qrcode")):
            return "qrcode"
        if _MEDIA_DOMAINS.search(text) and not _TECHNICAL.search(text):
            return "image_text"
        if any(marker in lowered for marker in ("图片", "配图", "卡片", "预览")):
            return "image_text"
        return "text"

    def _decision(self, action: BehaviorAction, confidence: float, wake: Any, reason: str, risk_class: str, media_intent: str, delivery: dict[str, Any], *, capability: str = "") -> BehaviorDecision:
        return BehaviorDecision(action=action, confidence=confidence, wake_reason=str(getattr(wake, "reason", "") or ""), participation_reason=reason, capability=capability, risk_class=risk_class, media_intent=media_intent, delivery_context=delivery)

    def _actor_id(self, runtime: Any, event: Any) -> str:
        try:
            return str(runtime.identity_from_event(event).global_user_id or "user")
        except Exception:  # noqa: BLE001
            try:
                return str(event.get_sender_id() or "user")
            except Exception:  # noqa: BLE001
                return "user"

    def _text(self, event: Any) -> str:
        try:
            return " ".join(str(event.get_message_str() or "").strip().split())
        except Exception:  # noqa: BLE001
            return ""

    def _is_group(self, event: Any) -> bool:
        try:
            message_type = event.get_message_type()
            normalized = str(getattr(message_type, "value", message_type))
        except Exception:  # noqa: BLE001
            normalized = str(getattr(event, "message_type", "") or "")
        return "group" in normalized.lower()
