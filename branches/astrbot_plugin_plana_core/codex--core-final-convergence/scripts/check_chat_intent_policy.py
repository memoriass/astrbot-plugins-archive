from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = "astrbot_plugin_plana_core"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"load_failed={path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


for name, path in (
    (PKG, ROOT),
    (f"{PKG}.memory", ROOT / "memory"),
):
    module = types.ModuleType(name)
    module.__path__ = [str(path)]  # type: ignore[attr-defined]
    sys.modules[name] = module

load(f"{PKG}.memory.models", ROOT / "memory" / "models.py")
load(f"{PKG}.memory.quality", ROOT / "memory" / "quality.py")
classifier = load(f"{PKG}.memory.classifier", ROOT / "memory" / "classifier.py")
planner_module = load(f"{PKG}.memory.query_planner", ROOT / "memory" / "query_planner.py")
should_extract_durable_memory = classifier.should_extract_durable_memory
LLMMemoryQueryPlanner = planner_module.LLMMemoryQueryPlanner

sys.path.insert(0, str(ROOT.parent))
from astrbot_plugin_plana_core.utils.intent_patterns import native_tool_profile
from astrbot_plugin_plana_core.utils.service_intent_patterns import service_domain_profile


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    require(service_domain_profile("plana帮我看看那个QQ怎么了") == "ncqq_plugin", "ncqq_route_missing")
    require(service_domain_profile("这周追的番更新了吗") == "ani_plugin", "ani_route_missing")
    require(service_domain_profile("漫画库最近进了啥") == "komga_plugin", "komga_route_missing")
    require(native_tool_profile("plana帮我看看那个QQ怎么了") == "ncqq_plugin", "ncqq_tool_profile_missing")
    require(native_tool_profile("今天有点累，陪我聊会儿") == "", "companion_chat_misrouted")

    require(should_extract_durable_memory("请记住我喜欢简洁回复"), "explicit_memory_missing")
    require(should_extract_durable_memory("我叫零，住在上海。"), "self_disclosure_missing")
    require(not should_extract_durable_memory("看看那个 QQ 实例是不是掉线了"), "tool_query_pollution")
    require(not should_extract_durable_memory("ANI RSS 当前有哪些订阅？"), "subscription_query_pollution")

    planner = LLMMemoryQueryPlanner()
    require(planner._fallback("我绑定的那个实例掉线了吗").should_retrieve, "binding_recall_missing")
    require(not planner._fallback("今天天气怎么样").should_retrieve, "unrelated_recall_enabled")
    print("chat_intent_policy_check=ok")


if __name__ == "__main__":
    main()
