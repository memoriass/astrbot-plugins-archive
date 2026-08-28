from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from astrbot.core.message.message_event_result import MessageChain
from astrbot_plugin_plana_core.plugin.gallery import (
    GalleryCandidate,
    GalleryCandidateEmotion,
    GalleryEmotionTarget,
    GalleryResolvedAsset,
    PlanaGalleryClient,
)
from astrbot_plugin_plana_core.plugin.db import Database
from astrbot_plugin_plana_core.plugin.plugin_events import PlanaPluginEventMixin
from astrbot_plugin_plana_core.presentation import gallery_context as policy_module
from astrbot_plugin_plana_core.presentation.gallery_emotions import display_emotions
from astrbot_plugin_plana_core.presentation.gallery_telemetry import (
    GalleryDecisionTelemetry,
    GalleryReactionState,
)


class FakeEvent:
    unified_msg_origin = "group:100"

    def __init__(self, message_id: str = "message-1") -> None:
        self.message_obj = SimpleNamespace(message_id=message_id)
        self.sent: list[MessageChain] = []

    def get_message_str(self) -> str:
        return "哈哈这也太棒了"

    def get_sender_id(self) -> str:
        return "actor:1"

    def is_private_chat(self) -> bool:
        return False

    def get_platform_name(self) -> str:
        return "aiocqhttp"

    async def send(self, chain: MessageChain) -> None:
        self.sent.append(chain)


class FakeProvider:
    def __init__(self, payload: dict[str, object]):
        self.payload = payload
        self.calls = 0

    async def text_chat(self, **_kwargs):
        self.calls += 1
        return SimpleNamespace(completion_text=json.dumps(self.payload))


class FakeGalleryClient:
    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self.candidate_calls = 0
        self.feedback_events: list[str] = []
        self.candidate_kwargs: dict[str, object] = {}
        self.feedback_payloads: list[dict[str, object]] = []
        self.items = [
            GalleryCandidate(
                asset_ref="gallery:happy",
                caption="开心庆祝",
                tags=("emotion:excited", "scene:celebrate", "safety:safe"),
                matched_facets=("emotion:excited", "scene:celebrate"),
                emotions=(GalleryCandidateEmotion("emotion:excited", 3, "primary"),),
                matched_emotions=("emotion:excited",),
                score=88,
                score_breakdown={"emotion_coverage": 35, "primary_alignment": 10},
            )
        ]

    async def candidates(self, **kwargs):
        self.candidate_calls += 1
        self.candidate_kwargs = kwargs
        return self.items

    async def resolve(self, asset_ref: str):
        return GalleryResolvedAsset(
            ok=True,
            asset_ref=asset_ref,
            file_path=self.file_path,
            mime_type="image/png",
        )

    async def feedback(self, **kwargs):
        self.feedback_events.append(str(kwargs.get("event") or ""))
        self.feedback_payloads.append(kwargs)
        return True


class FakeTelemetry:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    def record(self, **values: object) -> None:
        self.rows.append(values)


class FakePlugin(PlanaPluginEventMixin):
    pass


async def check_policy() -> None:
    assert policy_module._base_frequency_probability("natural", 0.85, False) == 0.70
    assert policy_module._base_frequency_probability("natural", 0.72, False) == 0.45
    assert policy_module._base_frequency_probability("natural", 0.0, True) == 0.20
    assert policy_module._base_frequency_probability("conservative", 0.0, True) == 0.08
    assert policy_module._base_frequency_probability("active", 0.0, False) == 1.0
    policy = policy_module.GalleryContextPolicy({"gallery_selector_mode": "model"})
    event = FakeEvent()
    intent = policy.intent(event, event.get_message_str(), "确实值得庆祝")
    assert intent is not None
    assert intent.emotions and intent.emotions[0].prominence == "primary"
    budget_policy = policy_module.GalleryContextPolicy(
        {
            "gallery_reaction_frequency_mode": "natural",
            "gallery_reaction_window_size": 5,
            "gallery_reaction_window_max": 2,
        }
    )
    budget_policy._frequency_history["group:budget"].extend([True, True])
    budget_intent = policy_module.GalleryContextIntent(
        request_id="budget-1", query="", facets=("tone:agree",), emotions=(),
        cooldown_key="group:budget",
    )
    assert not budget_policy.should_request_candidates(budget_intent)
    active_policy = policy_module.GalleryContextPolicy(
        {
            "gallery_reaction_frequency_mode": "active",
            "gallery_reaction_window_size": 5,
            "gallery_reaction_window_max": 1,
        }
    )
    active_policy._frequency_history["group:active"].extend([True] * 5)
    assert active_policy.should_request_candidates(
        policy_module.GalleryContextIntent(
            request_id="active", query="", facets=("tone:agree",), emotions=(),
            cooldown_key="group:active",
        )
    )
    policy.release(intent)
    mixed = policy.intent(
        FakeEvent("mixed"),
        "好耶终于完成了，但我人也麻了",
        "确实值得庆祝",
    )
    assert mixed is not None
    assert "role:plana" not in mixed.facets
    assert [(item.emotion_tag, item.target_intensity, item.prominence) for item in mixed.emotions] == [
        ("emotion:excited", 3, "primary"),
        ("emotion:speechless", 1, "secondary"),
    ]
    assert policy.should_request_candidates(mixed) == policy.should_request_candidates(mixed)
    policy.release(mixed)
    explicit = policy.intent(FakeEvent("explicit"), "给我发个反应图", "可以")
    assert explicit is not None and explicit.explicit_request
    assert policy.should_request_candidates(explicit)
    policy.release(explicit)
    candidates = [
        GalleryCandidate(
            asset_ref="gallery:happy",
            caption="开心庆祝",
            tags=("emotion:happy", "scene:celebrate", "safety:safe"),
            matched_facets=("emotion:happy",),
            score=88,
        )
    ]
    selected = await policy.select(
        FakeProvider({"asset_ref": "gallery:happy", "confidence": 0.91, "reason": "fit"}),
        intent,
        candidates,
    )
    assert selected is not None and selected.asset_ref == "gallery:happy"
    invented = await policy.select(
        FakeProvider({"asset_ref": "gallery:invented", "confidence": 0.99}),
        intent,
        candidates,
    )
    assert invented is None
    low = await policy.select(
        FakeProvider({"asset_ref": "gallery:happy", "confidence": 0.4}),
        intent,
        candidates,
    )
    assert low is None
    policy.release(intent)
    assert policy.intent(FakeEvent("blocked"), "帮我分析数据库报错", "我来检查日志") is None
    assert policy.intent(FakeEvent("response-blocked"), "哈哈好耶", "数据库测试失败了") is None

    lease_policy = policy_module.GalleryContextPolicy(
        {
            "gallery_group_cooldown_seconds": 0,
            "gallery_inflight_lease_seconds": 5,
        }
    )
    first = lease_policy.intent(FakeEvent("lease-1"), "哈哈好耶", "太棒了")
    assert first is not None
    lease_policy._inflight[first.cooldown_key] = 0
    second = lease_policy.intent(FakeEvent("lease-2"), "哈哈好耶", "太棒了")
    assert second is not None
    lease_policy.release(second)

    rule_policy = policy_module.GalleryContextPolicy(
        {
            "gallery_selector_mode": "rule",
            "gallery_group_cooldown_seconds": 0,
        }
    )
    rule_intent = rule_policy.intent(
        FakeEvent("rule"),
        "好耶终于完成了，但我人也麻了",
        "确实值得庆祝",
    )
    assert rule_intent is not None
    aligned = GalleryCandidate(
        asset_ref="gallery:aligned",
        tags=("emotion:excited", "emotion:speechless"),
        matched_facets=("emotion:excited", "emotion:speechless"),
        emotions=(
            GalleryCandidateEmotion("emotion:excited", 3, "primary"),
            GalleryCandidateEmotion("emotion:speechless", 1, "secondary"),
        ),
        matched_emotions=("emotion:excited", "emotion:speechless"),
        score=120,
        score_breakdown={"emotion_coverage": 35, "primary_alignment": 10},
    )
    missing_primary = GalleryCandidate(
        asset_ref="gallery:wrong",
        tags=("emotion:speechless",),
        matched_facets=("emotion:speechless",),
        matched_emotions=("emotion:speechless",),
        score=100,
        score_breakdown={"emotion_coverage": 12, "primary_alignment": 0},
    )
    direct = await rule_policy.select(None, rule_intent, [aligned, missing_primary])
    assert direct is not None and direct.asset_ref == "gallery:aligned"
    blocked_direct = await rule_policy.select(None, rule_intent, [missing_primary, aligned])
    assert blocked_direct is None
    rule_policy.release(rule_intent)


async def check_client_contract() -> None:
    class ContractClient(PlanaGalleryClient):
        def __init__(self) -> None:
            super().__init__(
                {
                    "enable_gallery_chat_images": True,
                    "plana_core_service_key": "test-key",
                }
            )
            self.payload: dict[str, object] = {}

        async def _json_request(self, method: str, path: str, **kwargs):
            self.payload = kwargs.get("json") or {}
            return {
                "contract_version": "plana.gallery.candidates.v1",
                "candidates": [
                    {
                        "asset_ref": "gallery:contract",
                        "tags": ["emotion:excited"],
                        "matched_facets": ["emotion:excited"],
                        "emotions": [
                            {
                                "emotion_tag": "emotion:excited",
                                "intensity": 3,
                                "prominence": "primary",
                            }
                        ],
                        "matched_emotions": ["emotion:excited"],
                        "score": 80,
                        "score_breakdown": {"emotion_coverage": 35},
                    }
                ],
            }

    client = ContractClient()
    candidates = await client.candidates(
        request_id="contract:1",
        query="好耶",
        facets=["emotion:excited"],
        emotions=[
            GalleryEmotionTarget(
                "emotion:excited", 3, "primary", 1.0, 0.9
            )
        ],
        exclude_asset_refs=[],
    )
    assert client.payload["emotions"] == [
        {
            "emotion_tag": "emotion:excited",
            "target_intensity": 3,
            "prominence": "primary",
            "weight": 1.0,
        }
    ]
    assert candidates[0].emotions[0].intensity == 3
    assert candidates[0].matched_emotions == ("emotion:excited",)

    class UnauthorizedClient(ContractClient):
        async def _json_request(self, method: str, path: str, **kwargs):
            self.last_error = "unauthorized"
            return {"ok": False, "error": "unauthorized"}

    unauthorized = UnauthorizedClient()
    assert await unauthorized.candidates(
        request_id="contract:unauthorized",
        query="",
        facets=[],
        exclude_asset_refs=[],
    ) == []
    assert unauthorized.last_error == "unauthorized"


async def check_delivery_order() -> None:
    with tempfile.TemporaryDirectory() as temp:
        image = Path(temp) / "reaction.png"
        image.write_bytes(b"fixture")
        client = FakeGalleryClient(str(image))
        provider = FakeProvider({"asset_ref": "none", "confidence": 0})
        plugin = FakePlugin()
        plugin._gallery_context = policy_module.GalleryContextPolicy(
            {
                "enable_gallery_chat_images": True,
                "gallery_delivery_delay_ms": 0,
                "gallery_selector_mode": "hybrid",
                "gallery_reaction_frequency_mode": "active",
            }
        )
        plugin._gallery_telemetry = FakeTelemetry()
        plugin.runtime = SimpleNamespace(gallery_client=client)
        plugin.context = SimpleNamespace(get_using_provider=lambda: provider)
        plugin.dialogue = SimpleNamespace(
            wake_state=SimpleNamespace(observe_response=lambda *args, **kwargs: None)
        )
        event = FakeEvent()
        response = SimpleNamespace(
            completion_text="确实值得庆祝",
            result_chain=MessageChain().message("确实值得庆祝"),
        )
        plugin._prepare_gallery_reaction(event, response)
        assert client.candidate_calls == 0 and event.sent == []
        await plugin._handle_after_message_sent(event)
        assert client.candidate_calls == 1 and len(event.sent) == 1
        assert client.candidate_kwargs["emotions"]
        assert event.sent[0].type == "plana_gallery_reaction"
        assert [item.__class__.__name__ for item in event.sent[0].chain] == ["Reply", "Image"]
        assert client.feedback_events == ["selected", "delivered"]
        assert all(payload.get("query") == "" for payload in client.feedback_payloads)
        assert all("emotions=" in str(payload.get("reason")) for payload in client.feedback_payloads)
        await plugin._handle_after_message_sent(event)
        assert len(event.sent) == 1
        blocked_event = FakeEvent("media")
        blocked_response = SimpleNamespace(
            completion_text="好耶",
            result_chain=MessageChain().message("好耶").file_image(str(image)),
        )
        plugin._prepare_gallery_reaction(blocked_event, blocked_response)
        assert getattr(blocked_event, "_plana_pending_gallery_reaction", None) is None


def check_telemetry() -> None:
    with tempfile.TemporaryDirectory() as temp:
        database = Database(Path(temp) / "plana.sqlite3")
        telemetry = GalleryDecisionTelemetry(database)
        telemetry.record(
            request_id="request:1",
            gate_reason="allowed",
            facets=["emotion:happy"],
            emotion_targets=[
                {
                    "emotion_tag": "emotion:happy",
                    "target_intensity": 3,
                    "prominence": "primary",
                    "weight": 1.0,
                    "confidence": 0.9,
                }
            ],
            candidate_refs=["gallery:happy"],
            selected_ref="gallery:happy",
            selection_method="rule_direct",
            elapsed_ms=12,
            delivery_result="delivered",
            scope_kind="group",
        )
        with database.connect() as conn:
            row = conn.execute("SELECT * FROM gallery_reaction_decisions").fetchone()
            event = conn.execute("SELECT * FROM gallery_reaction_events").fetchone()
        assert row is not None and row["delivery_result"] == "delivered"
        assert json.loads(row["emotion_targets"])[0]["emotion_tag"] == "emotion:happy"
        assert event is not None and event["stage"] == "gated"
        assert "user_text" not in row.keys() and "response_text" not in row.keys()

        state = GalleryReactionState(database)
        state.mark_delivered("group:private-source", "gallery:happy", 1234.0)
        restored_at, restored_refs = state.load("group:private-source")
        assert restored_at == 1234.0 and restored_refs == ["gallery:happy"]
        with database.connect() as conn:
            stored = conn.execute("SELECT * FROM gallery_reaction_state").fetchone()
        assert stored is not None and "private-source" not in stored["scope_hash"]


def check_emotion_taxonomy() -> None:
    wronged = display_emotions("我有点委屈，明明是被误会了", None)
    assert wronged and wronged[0].emotion_tag == "emotion:wronged"
    helpless = display_emotions("只能这样了，唉，真的没办法", None)
    assert helpless and helpless[0].emotion_tag == "emotion:helpless"
    panicked = display_emotions("手忙脚乱，真的来不及了！", None)
    assert panicked and panicked[0].emotion_tag == "emotion:panicked"
    assert panicked[0].target_intensity == 3


def main() -> None:
    local = PlanaGalleryClient({})
    assert not local.configured
    enabled_local = PlanaGalleryClient({"enable_gallery_chat_images": True})
    assert not enabled_local.configured
    service = SimpleNamespace(
        candidates=lambda payload: {
            "ok": True,
            "contract_version": "plana.gallery.candidates.v1",
            "candidates": [],
        },
        resolve=lambda asset_ref: {"ok": False, "error": "not_found"},
        feedback=lambda payload: {"ok": True},
        status=lambda: {"ok": True},
    )
    runtime = SimpleNamespace(
        sibling_services={"astrbot_plugin_plana_gallery": service}
    )
    in_process = PlanaGalleryClient(
        {"enable_gallery_chat_images": True},
        runtime=runtime,
    )
    assert in_process.configured
    assert in_process.status()["preferred_transport"] == "in_process"
    remote = PlanaGalleryClient({"gallery_service_url": "https://example.com/gallery"})
    assert not remote.configured
    asyncio.run(check_policy())
    asyncio.run(check_client_contract())
    asyncio.run(check_delivery_order())
    check_telemetry()
    check_emotion_taxonomy()
    source = "\n".join(
        (ROOT / "plugin" / name).read_text(encoding="utf-8")
        for name in ("plugin_events.py", "gallery_delivery.py")
    )
    assert "_schedule_gallery_image" not in source
    assert "record_artifact(" not in source
    assert "plana_gallery_reaction" in source
    assert "after_message_sent" in (ROOT / "main.py").read_text(encoding="utf-8")
    print("gallery_context_check=ok")


if __name__ == "__main__":
    main()
