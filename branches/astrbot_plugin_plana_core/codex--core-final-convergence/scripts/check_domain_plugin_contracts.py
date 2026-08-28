from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_plana_core.dialogue.domain_contracts import (
    DOMAIN_PLUGINS,
    OperationProposal,
    PolicyDecision,
)
from astrbot_plugin_plana_core.dialogue.domain_tool_route import (
    normalize_domain_tool_arguments,
)
from astrbot_plugin_plana_core.plugin.domain_routing import _domain_response_item
from astrbot_plugin_plana_core.utils.service_intent_patterns import (
    service_domain_profile,
)
from astrbot_plugin_plana_core.utils.intent_patterns import native_tool_profile
from astrbot_plugin_komga_manager.plugin.domain_harness import (
    komga_domain_harness_descriptor,
)


def main() -> None:
    komga_descriptor = komga_domain_harness_descriptor().to_dict()
    descriptors = (
        {
            "schema_version": 1,
            "domain": "ncqq",
            "owner": "ncqq-test-plugin",
            "profile": "ncqq_plugin",
            "tool_name": "ncqq_manager",
            "aliases": ["ncqq"],
            "service_ref": "ncqq.test",
            "natural_input_field": "target",
            "dispatch_workflow": "ai_dispatch",
            "direct_dispatch": True,
        },
        {
            "schema_version": 1,
            "domain": "ani_rss",
            "owner": "ani-test-plugin",
            "profile": "ani_plugin",
            "tool_name": "ani_rss",
            "aliases": ["ani-rss"],
            "service_ref": "ani_rss.test",
            "natural_input_field": "target",
            "dispatch_workflow": "ai_dispatch",
            "direct_dispatch": True,
        },
        komga_descriptor,
    )

    class Plugin:
        def __init__(self, descriptor):
            self.descriptor = descriptor

        def domain_harness_descriptors(self):
            return (self.descriptor,)

    stars = [
        SimpleNamespace(activated=True, name=item["owner"], star_cls=Plugin(item))
        for item in descriptors
    ]
    assert DOMAIN_PLUGINS.discover(stars) == []
    ncqq = DOMAIN_PLUGINS.for_profile("ncqq_plugin")
    assert ncqq is not None and ncqq.direct_dispatch
    ani = DOMAIN_PLUGINS.for_profile("ani_plugin")
    assert ani is not None and ani.tool_name == "ani_rss" and ani.direct_dispatch
    komga = DOMAIN_PLUGINS.for_profile("komga_plugin")
    assert komga is not None and komga.tool_name == "komga_manager"
    assert komga.owner == "astrbot_plugin_komga_manager"
    assert komga.dispatch_arguments("看看书库") == {
        "workflow": "ai_dispatch",
        "target": "看看书库",
        "params": {},
    }
    assert DOMAIN_PLUGINS.discover([]) == []
    assert not DOMAIN_PLUGINS.profiles()
    assert DOMAIN_PLUGINS.discover(stars) == []
    assert service_domain_profile("plana看看我现在追了哪些番") == "ani_plugin"
    assert service_domain_profile("plana帮我看看ani状态") == "ani_plugin"
    assert service_domain_profile("plana帮我追一下葬送的芙莉莲") == "ani_plugin"
    assert native_tool_profile("plana帮我看看ani状态") == "ani_plugin"
    assert native_tool_profile("plana帮我追一下葬送的芙莉莲") == "ani_plugin"
    assert service_domain_profile("这个字幕组最近更了啥") == "ani_plugin"
    assert service_domain_profile("漫画库最近进了啥") == "komga_plugin"
    assert native_tool_profile("plana帮我搜一下葬送的芙莉莲漫画") == "komga_plugin"
    assert native_tool_profile("plana帮我搜索一下葬送的芙莉莲漫画") == "komga_plugin"
    assert native_tool_profile("葬送的芙莉莲漫画推荐") == "search"
    args = {"workflow": "wrong", "target": "rewritten"}
    assert normalize_domain_tool_arguments(
        "ncqq_plugin",
        "ncqq_manager",
        "plana帮我看看机器人状态",
        args,
    )
    assert args == {
        "workflow": "ai_dispatch",
        "target": "plana帮我看看机器人状态",
        "params": {},
    }
    event = SimpleNamespace(plain_result=lambda text: {"plain": text})
    assert _domain_response_item(event, " ANI-RSS 正常 ") == {"plain": "ANI-RSS 正常"}
    assert _domain_response_item(event, "   ") is None
    proposal = OperationProposal(
        domain="ncqq",
        operation="inspect",
        target={"instance": "accept-ncqq-example"},
    )
    assert proposal.to_dict()["risk"] == "read_only"
    assert PolicyDecision("allow", "read-only proposal").decision == "allow"
    try:
        OperationProposal(domain="ncqq", operation="restart", risk="state_change")
    except ValueError:
        pass
    else:
        raise AssertionError("write proposal accepted without confirmation")
    print("domain_plugin_contracts=ok")


if __name__ == "__main__":
    main()
