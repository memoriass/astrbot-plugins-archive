from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_plana_core.dialogue.behavior import BehaviorOrchestrator
from astrbot_plugin_plana_core.dialogue.social_state import SocialInteractionStore
from astrbot_plugin_plana_core.dialogue.response_style import review_response_style
from astrbot_plugin_plana_core.plugin.db import Database
from astrbot_plugin_plana_core.utils.intent_patterns import (
    looks_like_explicit_codex_request,
    looks_like_informational_document_request,
    looks_like_service_discussion_request,
    looks_like_service_inspection_request,
    looks_like_tool_execution_request,
    native_tool_profile,
    prefers_external_search_over_service,
)


@dataclass
class _Identity:
    global_user_id: str = "qq:10001"


class _Runtime:
    def __init__(self) -> None:
        self.config = {
            "assistant_group_proactive_mode": "conservative",
            "assistant_group_proactive_cooldown_seconds": 300,
            "assistant_group_proactive_daily_limit": 8,
        }

    def resolve_scope(self, value):
        return str(value or "group:1")

    def identity_from_event(self, event):
        return _Identity()


class _MessageObject:
    message_id = "message-1"


class _Event:
    unified_msg_origin = "group:1"
    message_obj = _MessageObject()

    def __init__(self, text: str, message_type: str = "GroupMessage") -> None:
        self.text = text
        self.message_type = message_type

    def get_message_str(self):
        return self.text

    def get_sender_id(self):
        return "10001"

    def get_sender_name(self):
        return "tester"

    def get_message_type(self):
        return self.message_type


@dataclass
class _Wake:
    should_dispatch: bool
    reason: str = "test"


def main() -> int:
    runtime = _Runtime()
    orchestrator = BehaviorOrchestrator()
    unowned_downloader = orchestrator.decide(runtime, _Event("帮我查一下下载器状态"), _Wake(True))
    assert unowned_downloader.action == "direct_answer", unowned_downloader
    assert native_tool_profile("帮我查一下下载器状态") == ""
    anime_search = orchestrator.decide(runtime, _Event("帮我搜一下 Mikan 这季度番剧高分推荐"), _Wake(True))
    assert anime_search.action == "native_tool", anime_search
    assert anime_search.capability == "ani_plugin", anime_search
    assert not prefers_external_search_over_service("请搜一下 Mikan 这季度番剧高分推荐")
    assert not prefers_external_search_over_service("这季度有啥番值得追？mikan 上能下到的就行")
    assert native_tool_profile("这季度有啥番值得追？mikan 上能下到的就行") == "ani_plugin"
    assert not prefers_external_search_over_service("查一下 ANI-RSS 当前启用的订阅")
    assert not looks_like_explicit_codex_request("只读，不要交给 Codex")
    assert looks_like_explicit_codex_request("明确交给 Codex 处理")
    assert not looks_like_explicit_codex_request("明确交给已经退役的执行器处理")
    model_only = orchestrator.decide(runtime, _Event("NapCat 心跳在哪里设置？不需要后台执行"), _Wake(True))
    assert model_only.capability == "model_only", model_only
    document = orchestrator.decide(
        runtime,
        _Event("根据基础插件指南的文档，说明 AstrBot 工具注册与宿主事件接入各自的核心要求，列出实际文档名。"),
        _Wake(True),
    )
    assert document.action == "direct_answer", document
    assert document.capability == "document_reference", document
    assert native_tool_profile("接口文档里怎么配置 WebSocket") == ""
    assert looks_like_service_discussion_request("qb有些任务显示是排队，是代表什么意思？")
    assert native_tool_profile("qb有些任务显示是排队，是代表什么意思？") == ""
    assert looks_like_service_discussion_request("现在用ncqq频繁掉线有没有解决办法")
    assert native_tool_profile("现在用ncqq频繁掉线有没有解决办法") == ""
    diagnostic = orchestrator.decide(
        runtime,
        _Event("plana把刚才那个QQ的日志认真查一下，看看为什么总掉线"),
        _Wake(True),
    )
    assert diagnostic.action == "codex", diagnostic
    assert looks_like_service_discussion_request("大佬们 docker管理漫画除了komga 还有啥吗")
    assert native_tool_profile("大佬们 docker管理漫画除了komga 还有啥吗") == ""
    assert not looks_like_service_discussion_request("帮我检查一下当前 ncqq 登录状态")
    assert looks_like_service_inspection_request("帮我检查一下当前 ncqq 登录状态")
    assert native_tool_profile("帮我检查一下当前 ncqq 登录状态") == "ncqq_plugin"
    assert native_tool_profile("plana帮我新建一个测试机器人") == "ncqq_plugin"
    assert native_tool_profile("plana帮我新弄个测试机器人，别碰现在用的那些") == "ncqq_plugin"
    assert native_tool_profile("把accept-ncqq-test这个机器人彻底删掉，数据也清掉") == "ncqq_plugin"
    assert native_tool_profile("把刚才那个 ncqq 实例重启后发登录码") == "ncqq_plugin"
    assert native_tool_profile("plana看看accept-ncqq-20260719-test起来没") == "ncqq_plugin"
    assert looks_like_informational_document_request("接口文档里怎么配置 WebSocket")
    assert not looks_like_tool_execution_request("根据基础插件指南，说明工具注册方式")
    assert not looks_like_informational_document_request("按照这份文档执行安装")
    assert looks_like_tool_execution_request("按照这份文档执行安装")
    assert not looks_like_informational_document_request("根据指南创建一个实例")
    assert looks_like_tool_execution_request("根据指南创建一个实例")
    media = orchestrator.decide(runtime, _Event("推荐几个今晚吃的"), _Wake(True))
    assert media.media_intent == "image_text", media
    cancellation = orchestrator.decide(runtime, _Event("算了，停一下刚才那个"), _Wake(True))
    assert cancellation.action == "cancel_or_correct", cancellation
    resend = orchestrator.decide(runtime, _Event("刚才的二维码没收到，再发一下"), _Wake(True))
    assert resend.action == "short_artifact", resend
    assert resend.capability == "artifact_resend", resend
    qr = orchestrator.decide(runtime, _Event("那把登录码发我吧"), _Wake(True))
    assert qr.action in {"native_tool", "short_artifact"}, qr
    colloquial_status = orchestrator.decide(
        runtime, _Event("测试群那个机器人还是没起来吗"), _Wake(True)
    )
    assert colloquial_status.action == "native_tool", colloquial_status
    subscriptions = orchestrator.decide(
        runtime, _Event("这季我都订了些啥来着"), _Wake(True)
    )
    assert subscriptions.action == "native_tool", subscriptions
    komga_recent = orchestrator.decide(
        runtime, _Event("漫画库最近新进了啥"), _Wake(True)
    )
    assert komga_recent.action == "native_tool", komga_recent
    rejected = orchestrator.decide(runtime, _Event("删除系统目录 /etc"), _Wake(True))
    assert rejected.action == "reject", rejected
    silent = orchestrator.decide(runtime, _Event("今天的天气还不错"), _Wake(False))
    assert silent.action == "silence", silent
    with tempfile.TemporaryDirectory() as tmp:
        store = SocialInteractionStore(Database(Path(tmp) / "social.sqlite3"))
        state = store.get("group:1", "qq:10001")
        original = state.participation_tolerance
        store.record_feedback("group:1", "qq:10001", "以后别插话")
        assert store.get("group:1", "qq:10001").participation_tolerance < original
    stiff = review_response_style("零，我将调用内部协议，请稍候。请问还需要我做什么吗？")
    assert not stiff.natural and stiff.mechanical_markers
    natural = review_response_style("查到了：当前没有下载速度，连接状态是 firewalled。先检查监听端口。")
    assert natural.natural
    print("behavior orchestrator checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
