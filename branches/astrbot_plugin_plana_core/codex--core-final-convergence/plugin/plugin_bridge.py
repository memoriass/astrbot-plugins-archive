from __future__ import annotations

from astrbot.api.event import MessageChain

from quart import jsonify, request

from ..dialogue.delivery import remote_result_identity_error
from ..presentation.result_renderer import _render_to_file


from .plugin_bridge_support import PlanaPluginBridgeSupportMixin


class PlanaPluginBridgeMixin(PlanaPluginBridgeSupportMixin):
    async def _api_bridge_state(self):
        if not self._bridge_authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        return jsonify({"ok": True, "status": self.runtime.bridge_contract.status()})

    async def _api_bridge_payload(self):
        if not self._bridge_authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True)
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        if not self.runtime.bridge_contract.enabled:
            return jsonify(self.runtime.bridge_contract.disabled_result()), 403
        normalized = self.runtime.bridge_contract.normalize_payload(payload)
        result = await self._handle_bridge_payload(normalized)
        return jsonify(self.runtime.bridge_contract.result_report(normalized, result))

    async def _api_bridge_proactive_poll(self):
        if not self._bridge_authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            payload = {}
        tasks = self.runtime.proactive_queue.poll_ready(
            limit=self._bridge_limit(payload.get("limit", 5), 20)
        )
        return jsonify({"ok": True, "tasks": tasks})

    async def _api_bridge_proactive_deliver(self):
        if not self._bridge_authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        task_id = self._bridge_int(payload.get("task_id", 0), 0)
        if task_id <= 0:
            return jsonify({"ok": False, "error": "missing_task_id"}), 400
        status = str(payload.get("status") or "delivered").strip()
        runner_run_id = str(payload.get("runner_run_id") or "").strip()
        if status in {"failed", "retry_pending"}:
            ok = self.runtime.proactive_queue.mark_failed(
                task_id,
                str(payload.get("error") or "bridge_delivery_failed"),
                runner_run_id=runner_run_id,
            )
        else:
            ok = self.runtime.proactive_queue.mark_delivered(
                task_id,
                runner_run_id=runner_run_id,
            )
            request_id = str(payload.get("request_id") or "").strip()
            self._remote_run_mark_submitted_if_nonterminal(
                request_id,
                runner_run_id,
                payload,
            )
        return jsonify({"ok": ok})

    async def _handle_bridge_payload(self, payload: dict) -> dict[str, object]:
        kind = str(payload.get("kind", "unknown"))
        scope_id = str(payload.get("scope_id", "global")) or "global"
        scope_id = self.runtime.resolve_scope(scope_id)
        user_id = str(payload.get("user_id", "bridge_gateway")) or "bridge_gateway"
        content = str(payload.get("content", "")).strip()
        payload_data = (
            payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        )
        if kind == "memory_query":
            return self._handle_bridge_memory_query(scope_id, content, payload_data, kind)
        if kind == "execution_observation":
            return self._handle_bridge_execution_observation(
                scope_id, user_id, payload_data, kind
            )
        if kind == "result_report":
            result = self._handle_bridge_result_report(scope_id, user_id, content, payload_data, kind)
            if result.get("queued") and not bool(payload_data.get("suppress_notification", False)):
                result["notification_sent"] = await self._deliver_bridge_result(result, payload_data)
            else:
                result["notification_sent"] = False
            return result
        if kind in {"context_sync", "emotional_handoff"}:
            return self._handle_bridge_context_sync(
                scope_id,
                user_id,
                content,
                payload_data,
                kind,
            )
        return {"kind": kind, "error": "unsupported_kind"}

    def _handle_bridge_execution_observation(
        self,
        scope_id: str,
        user_id: str,
        payload_data: dict,
        kind: str,
    ) -> dict[str, object]:
        request_id = str(payload_data.get("request_id") or "").strip()
        runner_run_id = str(
            payload_data.get("runner_run_id") or payload_data.get("run_id") or ""
        ).strip()
        stored_run = self._remote_run(request_id)
        identity_error = remote_result_identity_error(
            stored_run,
            scope_id=scope_id,
            actor_id=user_id,
        )
        if identity_error:
            return {"kind": kind, "ok": False, "error": identity_error}
        if stored_run is None:
            return {"kind": kind, "ok": False, "error": "remote_run_missing"}
        store = getattr(self.runtime, "remote_task_runs", None)
        apply_observation = getattr(store, "apply_observation", None)
        if not callable(apply_observation):
            return {"kind": kind, "ok": False, "error": "observation_store_unavailable"}
        transition = str(
            apply_observation(
                request_id,
                status=str(payload_data.get("status") or "running"),
                runner_run_id=runner_run_id,
                observation=payload_data,
            )
        )
        return {
            "kind": kind,
            "ok": transition in {"applied", "duplicate", "ignored_terminal"},
            "request_id": request_id,
            "observation_transition": transition,
        }

    def _handle_bridge_memory_query(
        self, scope_id: str, content: str, payload_data: dict, kind: str
    ) -> dict[str, object]:
        limit = self._bridge_limit(payload_data.get("limit", 8), 20)
        target_kinds = self._bridge_target_kinds(payload_data)
        memories = self._search_bridge_memories(scope_id, content, target_kinds, limit)
        recall = self.runtime.recall_memory(
            scope_id,
            content,
            str(payload_data.get("kind") or ""),
            limit,
        )
        return {
            "kind": kind,
            "target_kinds": target_kinds,
            "items": [self._bridge_memory_item(item) for item in memories],
            "fused_results": recall.get("results", []),
            "routes": recall.get("routes", {}),
        }

    def _handle_bridge_result_report(
        self, scope_id: str, user_id: str, content: str, payload_data: dict, kind: str
    ) -> dict[str, object]:
        result_summary = str(
            payload_data.get("result_summary")
            or payload_data.get("summary")
            or payload_data.get("result")
            or content
        ).strip()
        objective = str(payload_data.get("objective") or content or "bridge result").strip()
        tool_name = str(payload_data.get("tool_name") or "bridge_gateway").strip()
        success = self._bridge_success(payload_data.get("success", True))
        task_id = self._bridge_int(payload_data.get("task_id", 0), 0)
        request_id = str(payload_data.get("request_id") or payload_data.get("codex_request_id") or "").strip()
        runner_run_id = str(payload_data.get("runner_run_id") or payload_data.get("run_id") or "").strip()
        stored_run = self._remote_run(request_id)
        identity_error = remote_result_identity_error(
            stored_run,
            scope_id=scope_id,
            actor_id=user_id,
        )
        if identity_error:
            return {
                "kind": kind,
                "queued": False,
                "error": identity_error,
                "request_id": request_id,
            }
        stored_runner_run_id = str((stored_run or {}).get("runner_run_id") or "").strip()
        if stored_runner_run_id and runner_run_id and stored_runner_run_id != runner_run_id:
            return {
                "kind": kind,
                "queued": False,
                "error": "remote_result_runner_mismatch",
                "request_id": request_id,
            }
        reported_status = str(payload_data.get("status") or "").strip().lower()
        remote_status = (
            reported_status
            if reported_status in {"succeeded", "failed", "cancelled"}
            else ("succeeded" if success else "failed")
        )
        stored_payload = self._remote_result_for_storage(payload_data)
        transition = self._remote_run_update(
            request_id,
            remote_status,
            runner_run_id,
            stored_payload,
            "" if success else result_summary,
        )
        if transition in {"ignored_cancelled", "ignored_terminal"}:
            return {
                "kind": kind,
                "queued": False,
                "request_id": request_id,
                "result_ignored": transition,
            }
        if transition == "late_success_after_cancel":
            return {
                "kind": kind,
                "queued": False,
                "request_id": request_id,
                "cancel_conflict": True,
                "error": transition,
            }
        if remote_status == "cancelled":
            result_summary = result_summary or "任务已经停止。"
        if not result_summary:
            return {
                "kind": kind,
                "stored": False,
                "error": "empty_result",
                "remote_result_applied": transition == "applied",
            }
        task_suffix = f" for task {task_id}" if task_id else ""
        feedback_id = self.runtime.feedback_queue.submit_new_memory(
            scope_id,
            user_id,
            (
                f"Bridge tool {tool_name} "
                f"{'succeeded' if success else 'failed'}{task_suffix}: "
                f"{objective} -> {result_summary}"
            ),
            "tool_result",
        )
        if feedback_id is None:
            return {
                "kind": kind,
                "queued": False,
                "error": "feedback_rejected",
                "remote_result_applied": transition == "applied",
            }
        return {
            "kind": kind,
            "queued": True,
            "remote_result_applied": transition == "applied",
            "feedback_id": feedback_id,
            "scope_id": str((stored_run or {}).get("scope_id") or scope_id),
            "actor_id": str((stored_run or {}).get("actor_id") or user_id),
            "delivery_context": dict(
                (stored_run or {}).get("delivery_context")
                if isinstance((stored_run or {}).get("delivery_context"), dict)
                else {}
            ),
        }

    async def _deliver_bridge_result(self, stored: dict[str, object], payload: dict) -> bool:
        delivery = (
            stored.get("delivery_context")
            if isinstance(stored.get("delivery_context"), dict)
            else {}
        )
        scope_id = str(
            delivery.get("conversation_id") or stored.get("scope_id") or ""
        ).strip()
        delivery_policy = str(delivery.get("delivery_policy") or "reply_then_mention")
        if delivery_policy == "private_only":
            recipients = delivery.get("artifact_recipients")
            if not isinstance(recipients, list):
                recipients = []
            private_targets = [
                str(item).strip()
                for item in recipients
                if ":FriendMessage:" in str(item)
            ]
            if not private_targets:
                return False
            scope_id = private_targets[0]
        if not scope_id or scope_id == "global":
            return False
        session_parts = scope_id.split(":", 2)
        if len(session_parts) != 3 or not all(session_parts):
            return False
        run = {
            "status": str(payload.get("status") or ("succeeded" if payload.get("success", True) else "failed")),
            "result": payload,
        }
        broker = getattr(self.dialogue, "task_broker", None)
        service = getattr(broker, "session_service", None)
        formatter = getattr(service, "_remote_success_reply", None)
        document_builder = getattr(service, "_remote_render_document", None)
        if callable(formatter):
            message = str(formatter(run) or "任务已完成。")
        else:
            message = str(payload.get("result_summary") or payload.get("summary") or "任务已完成。")
        chain = MessageChain()
        if callable(document_builder):
            document = document_builder(run)
            if isinstance(document, dict):
                try:
                    path = await _render_to_file(document)
                    chain.file_image(path)
                except Exception:
                    chain.message(message)
            else:
                chain.message(message)
        else:
            chain.message(message)
        return bool(await self.context.send_message(scope_id, chain))
