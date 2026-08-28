from __future__ import annotations

from typing import Any

GOVERNANCE_VERSION = 3

LEGACY_TAG_GOVERNANCE: tuple[dict[str, Any], ...] = (
    {"tag": "happy", "mode": "direct", "targets": ("emotion:happy",), "rationale": "语义稳定，直接归一为开心。", "auto_apply": True, "default_intensity": 2, "requires_review": False},
    {"tag": "surprised", "mode": "direct", "targets": ("emotion:surprised",), "rationale": "语义稳定，可归入惊讶。", "auto_apply": True, "default_intensity": 2, "requires_review": False},
    {"tag": "confused", "mode": "direct", "targets": ("emotion:confused",), "rationale": "语义稳定，可归入困惑。", "auto_apply": True, "default_intensity": 2, "requires_review": False},
    {"tag": "shy", "mode": "split", "targets": ("emotion:shy", "emotion:embarrassed"), "rationale": "可能是害羞或尴尬；已有实际分类时移除旧标签，否则进入待审核。", "auto_apply": False, "default_intensity": None, "requires_review": True},
    {"tag": "sad", "mode": "split", "targets": ("emotion:sad", "emotion:wronged", "emotion:disappointed"), "rationale": "旧 sad 同时包含悲伤、委屈和期待落空，必须依据表情与文字逐图拆分。", "auto_apply": False, "default_intensity": None, "requires_review": True},
    {"tag": "angry", "mode": "split", "targets": ("emotion:angry", "emotion:annoyed", "emotion:frustrated"), "rationale": "旧 angry 混合强烈愤怒、轻度烦躁和受阻挫败，不应整批映射。", "auto_apply": False, "default_intensity": None, "requires_review": True},
    {"tag": "like", "mode": "split", "targets": ("tone:agree", "emotion:affection"), "rationale": "可能表达赞同或喜欢；已有实际分类时移除旧标签，否则进入待审核。", "auto_apply": False, "default_intensity": None, "requires_review": True},
    {"tag": "morning", "mode": "context", "targets": ("scene:greeting",), "rationale": "这是稳定的问候场景，不作为情绪。", "auto_apply": True, "default_intensity": None, "requires_review": False},
    {"tag": "see", "mode": "context", "targets": ("emotion:curious", "scene:wait"), "rationale": "围观可能是好奇，也可能只是等待后续；场景和情绪应分别确认。", "auto_apply": False, "default_intensity": None, "requires_review": True},
    {"tag": "reply", "mode": "context", "targets": ("scene:wait", "emotion:curious"), "rationale": "可能表达等待回复、催促或好奇后续，必须逐图确认。", "auto_apply": False, "default_intensity": None, "requires_review": True},
    {"tag": "sigh", "mode": "split", "targets": ("emotion:helpless", "emotion:speechless", "emotion:tired", "tone:complain"), "rationale": "叹气常见为无奈，也可能是无语、疲惫或吐槽，必须逐图拆分。", "auto_apply": False, "default_intensity": None, "requires_review": True},
    {"tag": "sleep", "mode": "split", "targets": ("emotion:tired", "scene:end"), "rationale": "可能表达疲惫、晚安或结束话题，不能整批合并。", "auto_apply": False, "default_intensity": None, "requires_review": True},
    {"tag": "baka", "mode": "split", "targets": ("tone:teasing", "emotion:annoyed", "emotion:playful"), "rationale": "可能是调侃、俏皮捉弄，也可能是真实烦躁，需人工判断。", "auto_apply": False, "default_intensity": None, "requires_review": True},
    {"tag": "fool", "mode": "split", "targets": ("emotion:amused", "emotion:playful", "tone:teasing"), "rationale": "搞怪、自嘲和俏皮并不等价，建议逐图确认主情绪。", "auto_apply": False, "default_intensity": None, "requires_review": True},
    {"tag": "meow", "mode": "keep", "targets": ("emotion:playful", "tone:teasing"), "rationale": "这是内容与风格标签；可按画面补充俏皮或调侃，但原标签继续保留。", "auto_apply": False, "default_intensity": None, "requires_review": False},
    {"tag": "givemoney", "mode": "keep", "targets": (), "rationale": "特定内容主题，不强行映射为情绪。", "auto_apply": False, "default_intensity": None, "requires_review": False},
    {"tag": "cpu", "mode": "keep", "targets": (), "rationale": "内容主题标签，不参与情绪检索。", "auto_apply": False, "default_intensity": None, "requires_review": False},
    {"tag": "color", "mode": "keep", "targets": (), "rationale": "视觉属性，继续作为自由标签保留。", "auto_apply": False, "default_intensity": None, "requires_review": False},
    {"tag": "work", "mode": "keep", "targets": (), "rationale": "偏任务语境，默认不进入自动反应图主线。", "auto_apply": False, "default_intensity": None, "requires_review": False},
)


def governance_rules() -> list[dict[str, Any]]:
    return [
        {**rule, "targets": list(rule["targets"]), "governance_version": GOVERNANCE_VERSION}
        for rule in LEGACY_TAG_GOVERNANCE
    ]


def governance_rule_map() -> dict[str, dict[str, Any]]:
    return {str(rule["tag"]): rule for rule in LEGACY_TAG_GOVERNANCE}
