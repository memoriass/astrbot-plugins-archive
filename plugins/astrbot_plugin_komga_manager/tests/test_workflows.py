from __future__ import annotations

import json
import unittest

from workflows.models import READ_WORKFLOWS, WRITE_WORKFLOWS, WorkflowRequest
from workflows.routing import route_natural_text
from workflows.runner import run_komga_workflow


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    async def list_libraries(self):
        return self._result("list_libraries")

    async def list_recent(self, limit):
        return self._result("list_recent", limit)

    async def search_series(self, query, limit):
        return self._result("search_series", query, limit)

    async def series_detail(self, series_id):
        self.calls.append(("series_detail", (series_id,)))
        return {"id": series_id, "name": "Series"}

    async def list_books(self, series_id, limit):
        return self._result("list_books", series_id, limit)

    async def on_deck(self, limit):
        return self._result("on_deck", limit)

    async def collections(self, limit):
        return self._result("collections", limit)

    async def readlists(self, limit):
        return self._result("readlists", limit)

    def _result(self, name, *args):
        self.calls.append((name, args))
        return [{"id": name, "name": name}]


class FakePlugin:
    def __init__(self) -> None:
        self.client_instance = FakeClient()

    def client(self):
        return self.client_instance

    def default_limit(self):
        return 20


async def collect(plugin: FakePlugin, request: WorkflowRequest) -> list[dict]:
    raw = [item async for item in run_komga_workflow(plugin, object(), request)]
    return [json.loads(item) for item in raw]


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_read_workflows_execute_once(self) -> None:
        plugin = FakePlugin()
        requests = {
            "list_libraries": WorkflowRequest("list_libraries"),
            "list_recent": WorkflowRequest("list_recent"),
            "search_series": WorkflowRequest("search_series", "Frieren"),
            "series_detail": WorkflowRequest("series_detail", "series-1"),
            "list_books": WorkflowRequest("list_books", "series-1"),
            "on_deck": WorkflowRequest("on_deck"),
            "collections": WorkflowRequest("collections"),
            "readlists": WorkflowRequest("readlists"),
        }
        for workflow in READ_WORKFLOWS:
            payload = (await collect(plugin, requests[workflow]))[0]
            self.assertTrue(payload["ok"], workflow)
            self.assertTrue(payload["read_only"], workflow)
            self.assertTrue(payload["executed"], workflow)
        self.assertEqual([name for name, _args in plugin.client_instance.calls], list(READ_WORKFLOWS))

    async def test_write_workflows_only_create_pending_proposals(self) -> None:
        plugin = FakePlugin()
        for workflow in WRITE_WORKFLOWS:
            target = "series-1" if workflow == "refresh_series_metadata" else "library-1"
            payload = (await collect(plugin, WorkflowRequest(workflow, target)))[0]
            self.assertEqual(payload["action"], "write_pending")
            self.assertFalse(payload["executed"])
            self.assertTrue(payload["requires_confirmation"])
        self.assertEqual(plugin.client_instance.calls, [])

    def test_natural_routes_cover_reads_and_governed_writes(self) -> None:
        expected = {
            "看看 Komga 有哪些书库": "list_libraries",
            "看看最近更新": "list_recent",
            "搜索漫画葬送的芙莉莲": "search_series",
            "series detail id:series-1": "series_detail",
            "列出书籍": None,
            "看看待继续阅读": "on_deck",
            "列出合集": "collections",
            "看看阅读列表": "readlists",
            "扫描书库 id:library-1": "scan_library",
            "分析书库 id:library-1": "analyze_library",
            "刷新元数据 id:library-1": "refresh_library_metadata",
            "刷新系列元数据 id:series-1": "refresh_series_metadata",
        }
        for text, workflow in expected.items():
            request = route_natural_text(text)
            if workflow is None:
                self.assertIsNone(request)
            else:
                self.assertIsNotNone(request, text)
                self.assertEqual(request.workflow, workflow, text)


if __name__ == "__main__":
    unittest.main()

