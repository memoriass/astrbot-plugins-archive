from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_plana_core.dialogue.remote_task import CodexDelegationResult
from astrbot_plugin_plana_core.dialogue.remote_task_store import RemoteTaskRunStore
from astrbot_plugin_plana_core.dialogue.task_response_composer import TaskResponseComposer
from astrbot_plugin_plana_core.dialogue.task_session import TaskSessionStore
from astrbot_plugin_plana_core.dialogue.task_session_service import TaskSessionService
from astrbot_plugin_plana_core.plugin.db import Database


class Reply:
    def __init__(self, message_id: str) -> None:
        self.id = message_id


class FakeEvent:
    def __init__(self, reply_message_id: str = "") -> None:
        self.reply_message_id = reply_message_id
        self.unified_msg_origin = "scope:test"
        self.message_obj = type(
            "MessageObject",
            (),
            {"message_id": reply_message_id or "message-current"},
        )()

    def get_messages(self) -> list[object]:
        return [Reply(self.reply_message_id)] if self.reply_message_id else []

    def is_admin(self) -> bool:
        return False

    def get_sender_name(self) -> str:
        return "tester"


class FakeRuntime:
    def __init__(self, store: RemoteTaskRunStore) -> None:
        self.config = {"assistant_task_natural_confirm": True}
        self.remote_task_runs = store


class FakeRelay:
    def __init__(self, response: dict) -> None:
        self.response = response

    async def cancel_runner_task(self, runner_run_id: str) -> dict:
        return dict(self.response)


class FakeBridge:
    def __init__(self, response: dict) -> None:
        self.codex_relay = FakeRelay(response)


class FakeRemote:
    def __init__(self) -> None:
        self.cancelled: list[str] = []
        self.delegated: list[object] = []

    def delegate(self, request) -> CodexDelegationResult:
        self.delegated.append(request)
        return CodexDelegationResult(
            ok=True,
            delegated=True,
            request_id="delegated-request",
            status="queued",
            message="queued",
        )

    async def cancel(self, run: dict) -> CodexDelegationResult:
        request_id = str(run.get("request_id") or "")
        self.cancelled.append(request_id)
        return CodexDelegationResult(
            ok=True,
            delegated=True,
            request_id=request_id,
            status="cancelling",
            message="已向 Codex 提交取消请求。",
        )


def create_run(
    store: RemoteTaskRunStore,
    *,
    request_id: str,
    actor_id: str,
    title: str,
    source_message_id: str,
) -> None:
    store.create(
        request_id=request_id,
        proactive_task_id=len(store.recent(limit=20)) + 1,
        scope_id="scope:test",
        actor_id=actor_id,
        lane="interactive",
        title=title,
        payload={
            "request_id": request_id,
            "delivery_context": {
                "version": "plana.delivery.v1",
                "scope_id": "scope:test",
                "actor_id": actor_id,
                "source_message_id": source_message_id,
                "reply_to_message_id": source_message_id,
            },
        },
    )


async def check_contextual_cancel(store: RemoteTaskRunStore) -> None:
    service = TaskSessionService(TaskSessionStore())
    runtime = FakeRuntime(store)
    remote = FakeRemote()
    composer = TaskResponseComposer()

    create_run(
        store,
        request_id="run-a",
        actor_id="actor-a",
        title="整理下载结果",
        source_message_id="message-a",
    )
    action = await service.handle_natural_action(
        text="停一下",
        event=FakeEvent(),
        scope_id="scope:test",
        actor_id="actor-a",
        runtime=runtime,
        composer=composer,
        remote=remote,
    )
    assert action.handled and remote.cancelled == ["run-a"]

    store.update("run-a", status="cancelled")
    create_run(
        store,
        request_id="run-b",
        actor_id="actor-a",
        title="查找番剧资料",
        source_message_id="message-b",
    )
    create_run(
        store,
        request_id="run-c",
        actor_id="actor-a",
        title="检查下载器状态",
        source_message_id="message-c",
    )
    action = await service.handle_natural_action(
        text="不要了",
        event=FakeEvent("message-b"),
        scope_id="scope:test",
        actor_id="actor-a",
        runtime=runtime,
        composer=composer,
        remote=remote,
    )
    assert action.handled and remote.cancelled[-1] == "run-b"

    action = await service.handle_natural_action(
        text="算了",
        event=FakeEvent(),
        scope_id="scope:test",
        actor_id="actor-a",
        runtime=runtime,
        composer=composer,
        remote=remote,
    )
    assert action.reason == "remote_cancel_ambiguous"
    assert "run-b" not in action.reply and "run-c" not in action.reply

    action = await service.handle_natural_action(
        text="取消 检查下载器状态",
        event=FakeEvent(),
        scope_id="scope:test",
        actor_id="actor-a",
        runtime=runtime,
        composer=composer,
        remote=remote,
    )
    assert action.handled and remote.cancelled[-1] == "run-c"


async def check_authorization_delivery_context(store: RemoteTaskRunStore) -> None:
    sessions = TaskSessionStore()
    service = TaskSessionService(sessions)
    runtime = FakeRuntime(store)
    remote = FakeRemote()
    state = sessions.session("scope:test", "actor-a")
    state.latest_remote_authorization_pending = True
    state.latest_prompt = "short delegated task"
    state.latest_expected_capability = "codex.interactive"
    state.latest_remote_lane = "interactive"
    state.latest_remote_reason = "test"
    sessions.persist(state)

    action = await service.handle_natural_action(
        text="可以",
        event=FakeEvent("message-authorize"),
        scope_id="scope:test",
        actor_id="actor-a",
        runtime=runtime,
        composer=TaskResponseComposer(),
        remote=remote,
    )
    assert action.handled and remote.delegated
    payload = remote.delegated[0].payload()
    delivery = payload["delivery_context"]
    assert delivery["conversation_id"] == "scope:test"
    assert delivery["source_message_id"] == "message-authorize"
    assert delivery["artifact_recipients"] == ["actor-a"]


async def check_terminal_cancel_reconciliation(store: RemoteTaskRunStore) -> None:
    from astrbot_plugin_plana_core.dialogue.remote_task import RemoteTaskDelegator

    create_run(
        store,
        request_id="already-failed",
        actor_id="actor-a",
        title="已在 Runner 失败的任务",
        source_message_id="message-failed",
    )
    store.mark_submitted(
        "already-failed",
        runner_run_id="runner-failed",
        status="submitted",
    )
    runtime = FakeRuntime(store)
    runtime.config["assistant_remote_runner_enabled"] = True
    delegator = RemoteTaskDelegator(runtime)
    delegator._active_bridge = lambda: FakeBridge(
        {
            "ok": True,
            "status": "failed",
            "result": {"status": "failed", "error": "runner_timeout"},
        }
    )
    result = await delegator.cancel(store.get("already-failed"))
    assert result.ok and result.status == "failed"
    assert result.payload["reconciled_terminal"] is True
    stored = store.get("already-failed")
    assert stored["status"] == "failed"
    assert stored["error"] == "runner_timeout"


def check_terminal_transitions(store: RemoteTaskRunStore) -> None:
    create_run(
        store,
        request_id="late-success",
        actor_id="actor-a",
        title="长任务",
        source_message_id="message-late",
    )
    store.update("late-success", status="cancelling")
    transition = store.apply_terminal_result(
        "late-success",
        status="succeeded",
        result={"status": "succeeded", "result_summary": "late"},
    )
    assert transition == "late_success_after_cancel"
    assert store.get("late-success")["status"] == "cancel_failed"
    assert store.apply_terminal_result("late-success", status="failed") == "ignored_terminal"

    create_run(
        store,
        request_id="cancelled",
        actor_id="actor-b",
        title="已取消任务",
        source_message_id="message-cancelled",
    )
    store.update("cancelled", status="cancelled")
    assert (
        store.apply_terminal_result("cancelled", status="succeeded")
        == "ignored_cancelled"
    )
    assert store.get("cancelled")["status"] == "cancelled"

    create_run(
        store,
        request_id="normal-success",
        actor_id="actor-b",
        title="正常任务",
        source_message_id="message-success",
    )
    assert store.apply_terminal_result("normal-success", status="succeeded") == "applied"
    assert store.get("normal-success")["status"] == "succeeded"


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix="plana-cancel-") as tmp:
        store = RemoteTaskRunStore(Database(Path(tmp) / "plana.sqlite3"))
        store.initialize()
        await check_contextual_cancel(store)
        await check_authorization_delivery_context(store)
        await check_terminal_cancel_reconciliation(store)
        check_terminal_transitions(store)
    print("remote task cancellation check passed")


if __name__ == "__main__":
    asyncio.run(main())
