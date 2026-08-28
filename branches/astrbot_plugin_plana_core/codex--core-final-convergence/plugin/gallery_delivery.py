from __future__ import annotations

import asyncio
import re
from time import perf_counter
import uuid

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ..presentation.gallery_context import PendingGalleryReaction


class GalleryReactionDeliveryMixin:
    def _prepare_gallery_reaction(self, event: AstrMessageEvent, response: object) -> None:
        previous = getattr(event, "_plana_pending_gallery_reaction", None)
        if isinstance(previous, PendingGalleryReaction) and not previous.consumed:
            previous.consumed = True
            self._gallery_context.release(previous.intent)
        text = str(getattr(response, "completion_text", "") or "").strip()
        if not text:
            return
        request_id = self._gallery_request_id(event)
        if self._response_blocks_gallery(event, response, text):
            self._record_gallery_telemetry(
                request_id=request_id,
                gate_reason="response_contains_media_or_artifact",
                delivery_result="blocked",
                scope_kind="private" if self._gallery_is_private(event) else "group",
                stage="gated",
            )
            return
        mood_emotion = None
        try:
            state = self.runtime.storage.get_state("global", self.runtime.mode)
            mood_emotion = getattr(state, "emotion", None)
        except Exception:  # noqa: BLE001
            logger.debug("Plana Gallery mood prior unavailable", exc_info=True)
        decision = self._gallery_context.evaluate(
            event,
            event.get_message_str(),
            text,
            mood_emotion,
        )
        self._record_gallery_telemetry(
            request_id=decision.request_id,
            gate_reason=decision.reason,
            facets=list(decision.intent.facets) if decision.intent else [],
            emotion_targets=(
                _gallery_emotion_targets(decision.intent.emotions)
                if decision.intent
                else []
            ),
            delivery_result="pending" if decision.intent else "blocked",
            scope_kind="private" if self._gallery_is_private(event) else "group",
            stage="gated",
        )
        if decision.intent is None:
            return
        message_obj = getattr(event, "message_obj", None)
        source_message_id = str(getattr(message_obj, "message_id", "") or "").strip()
        platform_getter = getattr(event, "get_platform_name", None)
        try:
            platform = str(platform_getter() if callable(platform_getter) else "")
        except Exception:  # noqa: BLE001
            platform = ""
        setattr(
            event,
            "_plana_pending_gallery_reaction",
            PendingGalleryReaction(
                intent=decision.intent,
                response_text=text,
                source_message_id=source_message_id,
                is_private=self._gallery_is_private(event),
                platform=platform,
                reply_supported=self._gallery_reply_capability(event),
            ),
        )

    async def _handle_after_message_sent(self, event: AstrMessageEvent) -> None:
        pending = getattr(event, "_plana_pending_gallery_reaction", None)
        if not isinstance(pending, PendingGalleryReaction) or pending.consumed:
            return
        pending.consumed = True
        setattr(event, "_plana_pending_gallery_reaction", None)
        started = perf_counter()
        intent = pending.intent
        candidates = []
        selection = None
        try:
            if not self._gallery_context.send_enabled:
                self._record_gallery_telemetry(
                    request_id=intent.request_id,
                    gate_reason="allowed",
                    facets=list(intent.facets),
                    delivery_result="shadow_only",
                    scope_kind="private" if pending.is_private else "group",
                    stage="gated",
                )
                return
            if not self._gallery_context.should_request_candidates(intent):
                self._record_gallery_telemetry(
                    request_id=intent.request_id,
                    gate_reason="frequency_sampled_out",
                    facets=list(intent.facets),
                    emotion_targets=_gallery_emotion_targets(intent.emotions),
                    delivery_result="sampled_out",
                    scope_kind="private" if pending.is_private else "group",
                    stage="gated",
                )
                return

            candidates = await self.runtime.gallery_client.candidates(
                request_id=intent.request_id,
                query=intent.query,
                facets=list(intent.facets),
                exclude_asset_refs=self._gallery_context.excluded_refs(intent),
                emotions=list(intent.emotions),
            )
            self._record_gallery_telemetry(
                request_id=intent.request_id,
                gate_reason="allowed",
                facets=list(intent.facets),
                emotion_targets=_gallery_emotion_targets(intent.emotions),
                candidate_refs=[item.asset_ref for item in candidates],
                elapsed_ms=int((perf_counter() - started) * 1000),
                delivery_result="candidates_ready",
                scope_kind="private" if pending.is_private else "group",
                stage="candidates",
            )
            if not candidates:
                service_error = str(self.runtime.gallery_client.last_error or "").strip()
                error_category = (
                    _gallery_error_category(service_error, "unavailable")
                    if service_error
                    else ""
                )
                self._record_gallery_telemetry(
                    request_id=intent.request_id,
                    gate_reason="allowed",
                    facets=list(intent.facets),
                    emotion_targets=_gallery_emotion_targets(intent.emotions),
                    elapsed_ms=int((perf_counter() - started) * 1000),
                    delivery_result=(
                        f"service_failed:{service_error}"[:240]
                        if service_error
                        else "no_candidates"
                    ),
                    scope_kind="private" if pending.is_private else "group",
                    stage="failed",
                    error_category=error_category,
                )
                return
            provider = self.context.get_using_provider()
            selection = await self._gallery_context.select(provider, intent, candidates)
            if selection is None:
                self._record_gallery_telemetry(
                    request_id=intent.request_id,
                    gate_reason="allowed",
                    facets=list(intent.facets),
                    emotion_targets=_gallery_emotion_targets(intent.emotions),
                    candidate_refs=[item.asset_ref for item in candidates],
                    elapsed_ms=int((perf_counter() - started) * 1000),
                    delivery_result="selector_none",
                    scope_kind="private" if pending.is_private else "group",
                    stage="failed",
                )
                return
            await self.runtime.gallery_client.feedback(
                request_id=intent.request_id,
                asset_ref=selection.asset_ref,
                event="selected",
                reason=_gallery_feedback_reason(selection.reason, intent.emotions),
                query="",
            )
            self._record_gallery_telemetry(
                request_id=intent.request_id,
                gate_reason="allowed",
                facets=list(intent.facets),
                emotion_targets=_gallery_emotion_targets(intent.emotions),
                candidate_refs=[item.asset_ref for item in candidates],
                selected_ref=selection.asset_ref,
                selection_method=selection.reason,
                elapsed_ms=int((perf_counter() - started) * 1000),
                delivery_result="selected",
                scope_kind="private" if pending.is_private else "group",
                stage="selected",
            )
            resolved = await self.runtime.gallery_client.resolve(selection.asset_ref)
            if not resolved.ok:
                await self.runtime.gallery_client.feedback(
                    request_id=intent.request_id,
                    asset_ref=selection.asset_ref,
                    event="failed",
                    reason=resolved.error,
                    query="",
                )
                self._record_gallery_telemetry(
                    request_id=intent.request_id,
                    gate_reason="allowed",
                    facets=list(intent.facets),
                    emotion_targets=_gallery_emotion_targets(intent.emotions),
                    candidate_refs=[item.asset_ref for item in candidates],
                    selected_ref=selection.asset_ref,
                    selection_method=selection.reason,
                    elapsed_ms=int((perf_counter() - started) * 1000),
                    delivery_result=f"resolve_failed:{resolved.error}",
                    scope_kind="private" if pending.is_private else "group",
                    stage="failed",
                    error_category=_gallery_error_category(resolved.error, "resolve"),
                )
                return
            self._record_gallery_telemetry(
                request_id=intent.request_id,
                gate_reason="allowed",
                facets=list(intent.facets),
                emotion_targets=_gallery_emotion_targets(intent.emotions),
                candidate_refs=[item.asset_ref for item in candidates],
                selected_ref=selection.asset_ref,
                selection_method=selection.reason,
                elapsed_ms=int((perf_counter() - started) * 1000),
                delivery_result="resolved",
                scope_kind="private" if pending.is_private else "group",
                stage="resolved",
            )
            await asyncio.sleep(self._gallery_context.delivery_delay_ms / 1000)
            chain = self._gallery_reaction_chain(pending, resolved.file_path)
            self._record_gallery_telemetry(
                request_id=intent.request_id,
                gate_reason="allowed",
                facets=list(intent.facets),
                emotion_targets=_gallery_emotion_targets(intent.emotions),
                candidate_refs=[item.asset_ref for item in candidates],
                selected_ref=selection.asset_ref,
                selection_method=selection.reason,
                elapsed_ms=int((perf_counter() - started) * 1000),
                delivery_result="delivering",
                scope_kind="private" if pending.is_private else "group",
                stage="delivering",
            )
            await event.send(chain)
            await self.runtime.gallery_client.feedback(
                request_id=intent.request_id,
                asset_ref=selection.asset_ref,
                event="delivered",
                reason=_gallery_feedback_reason(selection.reason, intent.emotions),
                query="",
            )
            self._gallery_context.mark_delivered(intent, selection.asset_ref)
            logger.info("Plana local Gallery image delivered: asset_ref=%s", selection.asset_ref)
            self._record_gallery_telemetry(
                request_id=intent.request_id,
                gate_reason="allowed",
                facets=list(intent.facets),
                emotion_targets=_gallery_emotion_targets(intent.emotions),
                candidate_refs=[item.asset_ref for item in candidates],
                selected_ref=selection.asset_ref,
                selection_method=selection.reason,
                elapsed_ms=int((perf_counter() - started) * 1000),
                delivery_result="delivered",
                scope_kind="private" if pending.is_private else "group",
                stage="delivered",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Plana local Gallery image delivery failed", exc_info=True)
            if selection is not None:
                await self.runtime.gallery_client.feedback(
                    request_id=intent.request_id,
                    asset_ref=selection.asset_ref,
                    event="failed",
                    reason=_gallery_error_category(exc, "send"),
                    query="",
                )
            self._record_gallery_telemetry(
                request_id=intent.request_id,
                gate_reason="allowed",
                facets=list(intent.facets),
                emotion_targets=_gallery_emotion_targets(intent.emotions),
                candidate_refs=[item.asset_ref for item in candidates],
                selected_ref=str(getattr(selection, "asset_ref", "") or ""),
                selection_method=str(getattr(selection, "reason", "") or ""),
                elapsed_ms=int((perf_counter() - started) * 1000),
                delivery_result="failed",
                scope_kind="private" if pending.is_private else "group",
                stage="failed",
                error_category=_gallery_error_category(exc, "send"),
            )
        finally:
            self._gallery_context.release(intent)

    def _gallery_reaction_chain(
        self, pending: PendingGalleryReaction, file_path: str
    ):
        from astrbot.core.message.components import Reply
        from astrbot.core.message.message_event_result import MessageChain

        chain = MessageChain()
        if self._gallery_reply_supported(pending):
            chain.chain.append(Reply(id=pending.source_message_id))
        chain.file_image(file_path)
        chain.type = "plana_gallery_reaction"
        return chain

    @staticmethod
    def _gallery_reply_supported(pending: PendingGalleryReaction) -> bool:
        if pending.is_private or not pending.source_message_id:
            return False
        if isinstance(pending.reply_supported, bool):
            return pending.reply_supported
        platform = pending.platform.casefold()
        return "aiocqhttp" in platform or platform in {"qq", "napcat", "onebot"}

    @staticmethod
    def _gallery_reply_capability(event: AstrMessageEvent) -> bool | None:
        for name in ("supports_reply", "reply_supported"):
            value = getattr(event, name, None)
            try:
                value = value() if callable(value) else value
            except Exception:  # noqa: BLE001
                continue
            if isinstance(value, bool):
                return value
        adapter = getattr(event, "platform_meta", None) or getattr(event, "adapter", None)
        for name in ("supports_reply", "reply_supported"):
            value = getattr(adapter, name, None)
            if isinstance(value, bool):
                return value
        return None

    def _response_blocks_gallery(
        self, event: AstrMessageEvent, response: object, text: str
    ) -> bool:
        if getattr(event, "_plana_service_artifacts", None):
            return True
        if getattr(event, "_plana_search_result", None) or getattr(
            event, "_plana_search_direct_delivery", False
        ):
            return True
        if str(getattr(event, "_plana_native_tool_profile", "") or "") in {
            "search", "service_query"
        }:
            return True
        if re.search(r"!\[[^\]]*\]\([^\)]+\)", text):
            return True
        chain = getattr(response, "result_chain", None)
        components = list(getattr(chain, "chain", []) or [])
        return any(
            component.__class__.__name__ in {"Image", "File", "Record", "Video"}
            for component in components
        )

    def _record_gallery_telemetry(self, **values: object) -> None:
        try:
            self._gallery_telemetry.record(**values)
        except Exception:  # noqa: BLE001
            logger.debug("Plana Gallery telemetry write skipped", exc_info=True)

    def _gallery_request_id(self, event: AstrMessageEvent) -> str:
        message_obj = getattr(event, "message_obj", None)
        message_id = str(getattr(message_obj, "message_id", "") or "").strip()
        sender = str(event.get_sender_id() or "user")
        return f"gallery:{message_id}:{sender}"[:160] if message_id else uuid.uuid4().hex

    def _gallery_is_private(self, event: AstrMessageEvent) -> bool:
        checker = getattr(event, "is_private_chat", None)
        try:
            return bool(checker()) if callable(checker) else False
        except Exception:  # noqa: BLE001
            return False


def _gallery_error_category(error: object, default: str) -> str:
    text = str(error or "").casefold()
    if "401" in text or "unauthorized" in text or "auth" in text:
        return "auth"
    if "timeout" in text:
        return "timeout"
    if "contract" in text or "version" in text:
        return "contract"
    if "missing" in text or "not_found" in text or "file" in text:
        return "missing-file"
    if "unavailable" in text or "connection" in text or "connect" in text:
        return "unavailable"
    return default


def _gallery_emotion_targets(values: object) -> list[dict[str, object]]:
    result = []
    for item in list(values or [])[:4]:
        result.append(
            {
                "emotion_tag": str(getattr(item, "emotion_tag", ""))[:80],
                "target_intensity": int(getattr(item, "target_intensity", 2)),
                "prominence": str(getattr(item, "prominence", "secondary"))[:16],
                "weight": float(getattr(item, "weight", 1.0)),
                "confidence": float(getattr(item, "confidence", 0.0)),
            }
        )
    return result


def _gallery_feedback_reason(reason: str, values: object) -> str:
    summary = ",".join(
        f"{item['emotion_tag']}:{item['target_intensity']}:{item['prominence']}"
        for item in _gallery_emotion_targets(values)
    )
    return f"{str(reason or '')[:200]}; emotions={summary}"[:500]
