from __future__ import annotations

from typing import Any

from .delivery import reply_message_id_from_event, run_matches_reply
from .remote_task import RemoteTaskDelegator
from .task_session_models import NaturalTaskAction


class TaskSessionSupportMixin:
    def _remote_success_reply(self, run: dict[str, Any]) -> str:
        result = run.get("result") if isinstance(run.get("result"), dict) else {}
        nested = result.get("result") if isinstance(result.get("result"), dict) else {}
        capability = str(result.get("capability") or nested.get("capability") or "")
        if capability == "ani_rss.list_subscriptions":
            subscriptions = nested.get("subscriptions") if isinstance(nested.get("subscriptions"), list) else []
            lines = [f"ANI-RSS 当前有 {len(subscriptions)} 条订阅："]
            for index, item in enumerate(subscriptions[:8], start=1):
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "未命名订阅")
                subgroup = str(item.get("subgroup") or "").strip()
                lines.append(f"{index}. {title}{f' · {subgroup}' if subgroup else ''}")
            return "\n".join(lines)
        top_summary = str(result.get("result_summary") or "").strip()
        if top_summary:
            return self._dedupe_adjacent_summary(top_summary)
        nested_summary = str(
            nested.get("result_summary")
            or nested.get("summary")
            or result.get("summary")
            or ""
        ).strip()
        if nested_summary:
            return self._dedupe_adjacent_summary(nested_summary)
        subscriptions = nested.get("subscriptions") if isinstance(nested.get("subscriptions"), list) else []
        titles = [
            str(item.get("title") or item.get("name") or "").strip()
            for item in subscriptions[:5]
            if isinstance(item, dict) and (item.get("title") or item.get("name"))
        ]
        count = nested.get("count", nested.get("returned_count"))
        if titles or count is not None:
            title_text = f"：{'、'.join(titles)}" if titles else ""
            return f"只读查询完成，共 {count if count is not None else len(subscriptions)} 条{title_text}"
        return "只读查询已完成。"

    def _remote_render_document(self, run: dict[str, Any]) -> dict[str, Any] | None:
        result = run.get("result") if isinstance(run.get("result"), dict) else {}
        nested = result.get("result") if isinstance(result.get("result"), dict) else {}
        resource = nested.get("resource") if isinstance(nested.get("resource"), dict) else {}
        resource_name = (
            nested.get("resource_name") or resource.get("display_name")
            or resource.get("external_id")
        )
        resource_state = nested.get("resource_state") or nested.get("login_status")
        if resource_name or resource_state:
            delivery = nested.get("delivery") if isinstance(nested.get("delivery"), dict) else {}
            return {
                "contract_version": "plana.render.v1",
                "template": "resource_status",
                "title": "资源状态",
                "status": "warning" if str(resource_state).lower() in {"offline", "logged_out", "离线", "掉线"} else "success",
                "summary": self._remote_success_reply(run),
                "artifacts": result.get("artifacts") if isinstance(result.get("artifacts"), list) else [],
                "metadata": {
                    "resource_name": resource_name or "目标资源",
                    "resource_state": resource_state or nested.get("status") or "已完成",
                    "action": nested.get("action_summary") or nested.get("action") or "",
                    "recipient": delivery.get("recipient") or nested.get("recipient") or "",
                    "delivery_status": delivery.get("status") or nested.get("delivery_status") or "",
                    "recovery": nested.get("recovery") or result.get("recovery") or "",
                },
            }
        subscriptions = nested.get("subscriptions")
        if isinstance(subscriptions, list):
            items = []
            for item in subscriptions:
                if not isinstance(item, dict):
                    continue
                items.append({
                    "title": item.get("title") or item.get("name") or "Subscription",
                    "status": "enabled" if item.get("enable") else "disabled",
                    "season": item.get("season"),
                    "episode": item.get("episode") or item.get("progress"),
                    "category": item.get("subgroup"),
                })
            return {
                "contract_version": "plana.render.v1",
                "template": "ani_rss",
                "title": "ANI-RSS 订阅",
                "status": "success",
                "summary": self._remote_success_reply(run),
                "items": items,
                "metadata": {"count": nested.get("count", len(items)), "read_only": nested.get("read_only", True)},
            }
        summary = self._remote_success_reply(run)
        artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), list) else []
        if not self._should_render_remote_task_result(result, summary, artifacts):
            return None
        return {
            "contract_version": "plana.render.v1",
            "template": "task_result",
            "title": "任务结果",
            "status": run.get("status") or "succeeded",
            "summary": summary,
            "artifacts": artifacts,
            "metadata": {},
        }

    def _should_render_remote_task_result(
        self,
        result: dict[str, Any],
        summary: str,
        artifacts: list[Any],
    ) -> bool:
        meaningful_artifacts = [
            item
            for item in artifacts
            if isinstance(item, dict)
            and str(item.get("content_type") or "").lower() not in {"", "text/plain"}
        ]
        if meaningful_artifacts or len(artifacts) > 1:
            return True
        if len(summary) > 600 or summary.count("\n") >= 3:
            return True
        return any(
            key in result
            for key in ("progress", "recovery", "recovery_notes")
        )

    def _dedupe_adjacent_summary(self, summary: str) -> str:
        clean = summary.strip()
        for marker in ("结果摘要：", "Result summary:"):
            prefix, separator, detail = clean.partition(marker)
            if separator and len(detail) % 2 == 0:
                midpoint = len(detail) // 2
                if detail[:midpoint] == detail[midpoint:]:
                    return f"{prefix}{separator}{detail[:midpoint]}"
        if len(clean) % 2 == 0:
            midpoint = len(clean) // 2
            if clean[:midpoint] == clean[midpoint:]:
                return clean[:midpoint]
        return clean

    def _remote_failure_reply(self, run: dict[str, Any]) -> str:
        result = run.get("result") if isinstance(run.get("result"), dict) else {}
        error = str(run.get("error") or result.get("error") or "远程执行失败").strip()
        recovery = str(result.get("recovery") or result.get("recovery_notes") or "请稍后重试或检查执行部门连接。").strip()
        return f"只读查询失败：{error}\n恢复建议：{recovery}"

    async def _cancel_remote(
        self,
        *,
        runtime: Any,
        event: Any,
        scope_id: str,
        actor_id: str,
        remote: RemoteTaskDelegator,
        request_id: str = "",
    ) -> NaturalTaskAction | None:
        store = getattr(runtime, "remote_task_runs", None)
        active = getattr(store, "active", None)
        if not callable(active):
            return None
        runs = active(scope_id=scope_id, actor_id=actor_id, limit=5)
        reply_message_id = reply_message_id_from_event(event)
        if reply_message_id:
            anchored = [item for item in runs if run_matches_reply(item, reply_message_id)]
            if anchored:
                runs = anchored
        if request_id:
            runs = [
                item
                for item in runs
                if request_id
                in {
                    str(item.get("request_id") or ""),
                    str(item.get("title") or ""),
                }
            ]
        if not runs and self._event_is_admin(event):
            runs = active(scope_id=scope_id, limit=5)
            if request_id:
                runs = [
                    item
                    for item in runs
                    if request_id
                    in {
                        str(item.get("request_id") or ""),
                        str(item.get("title") or ""),
                    }
                ]
        if not runs:
            return None
        if len(runs) > 1:
            choices = "；".join(
                f"{index}. {str(item.get('title') or '后台任务')[:30]}"
                for index, item in enumerate(runs[:5], start=1)
            )
            return NaturalTaskAction(
                True,
                f"你这边有几个任务还在跑：{choices}。告诉我任务名称，我来停掉。",
                True,
                "remote_cancel_ambiguous",
            )
        result = await remote.cancel(runs[0])
        return NaturalTaskAction(
            True,
            result.message or result.error or "Codex 取消请求处理失败。",
            True,
            f"remote_cancel_{result.status or 'failed'}",
        )

    def _event_is_admin(self, event: Any) -> bool:
        checker = getattr(event, "is_admin", None)
        if callable(checker):
            try:
                return bool(checker())
            except Exception:  # noqa: BLE001
                return False
        return str(getattr(event, "role", "") or "").lower() == "admin"

    def observe_model_response(
        self,
        runtime: Any,
        event: Any,
        text: str,
    ) -> None:
        scope_id = self._scope_id(runtime, event)
        actor_id = self._actor_id(runtime, event)
        state = self.sessions.session(scope_id, actor_id)
        if not state.latest_llm_tool_pending:
            return
        lowered = str(text or "").lower()
        failed = any(
            token in lowered
            for token in (
                "无法",
                "不能",
                "失败",
                "错误",
                "权限受限",
                "受限",
                "unavailable",
                "failed",
                "error",
            )
        )
        state.latest_llm_tool_pending = False
        if failed:
            state.latest_failure = "llm_tool_failed_or_refused"
            state.latest_recovery = "可以重试；复杂诊断可生成 Codex 授权提案。"

    def _recovery_steps(self, runtime: Any) -> int:
        try:
            value = int(runtime.config.get("assistant_task_max_recovery_steps", 2))
        except (TypeError, ValueError):
            value = 2
        return max(0, min(value, 2))

    def _scope_id(self, runtime: Any, event: Any) -> str:
        try:
            return str(runtime.resolve_scope(event.unified_msg_origin) or "global")
        except Exception:  # noqa: BLE001
            return "global"

    def _actor_id(self, runtime: Any, event: Any) -> str:
        identity_from_event = getattr(runtime, "identity_from_event", None)
        if callable(identity_from_event):
            try:
                identity = identity_from_event(event)
                value = str(getattr(identity, "global_user_id", "") or "")
                if value:
                    return value
            except Exception:  # noqa: BLE001
                pass
        getter = getattr(event, "get_sender_id", None)
        if callable(getter):
            try:
                return str(getter() or "user")
            except Exception:  # noqa: BLE001
                pass
        return "user"
