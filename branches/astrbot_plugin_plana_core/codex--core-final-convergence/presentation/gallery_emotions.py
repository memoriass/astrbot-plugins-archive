from __future__ import annotations

import re
from typing import Any

try:
    from ..plugin.gallery import GalleryEmotionTarget
except ImportError:  # pragma: no cover - standalone checks
    from plugin.gallery import GalleryEmotionTarget


_EMOTION_RULES = (
    (r"好耶|激动|兴奋|终于|太棒|赢了|成功了|👏", "emotion:excited", 2),
    (r"哈哈|笑死|绷不住|乐了|好笑|😂", "emotion:amused", 2),
    (r"开心|高兴|快乐|嘿嘿|好呀", "emotion:happy", 2),
    (r"喜欢|可爱|贴贴|甜甜|宠|❤|❤️", "emotion:affection", 2),
    (r"谢谢|感谢|感激|暖心", "emotion:grateful", 2),
    (r"厉害|牛啊|真棒|得意|自豪", "emotion:proud", 2),
    (r"松口气|放心了|还好|总算", "emotion:relieved", 2),
    (r"期待|盼望|希望能|等不及", "emotion:hopeful", 1),
    (r"俏皮|卖萌|坏笑|逗你|嘿嘿嘿", "emotion:playful", 1),
    (r"平静|淡定|安稳|慢慢来", "emotion:calm", 1),
    (r"震惊|真的假的|居然|意外|😱", "emotion:surprised", 2),
    (r"不懂|困惑|迷茫|为什么|怎么回事|🤔", "emotion:confused", 2),
    (r"好奇|想知道|看看后续|然后呢", "emotion:curious", 1),
    (r"离谱|无语|啊这|人麻了|麻了|不知道说什么", "emotion:speechless", 2),
    (r"无奈|没办法|只能这样|叹气|唉", "emotion:helpless", 2),
    (r"害羞|不好意思|脸红", "emotion:shy", 2),
    (r"尴尬|社死|出糗", "emotion:embarrassed", 2),
    (r"委屈|被误会|欺负我|不公平", "emotion:wronged", 2),
    (r"难过|伤心|想哭", "emotion:sad", 2),
    (r"失望|遗憾|落空", "emotion:disappointed", 2),
    (r"挫败|受挫|又失败|做不下去|卡住了", "emotion:frustrated", 2),
    (r"内疚|愧疚|是我的错|做错了", "emotion:guilty", 2),
    (r"生气|愤怒|气死|火大", "emotion:angry", 2),
    (r"烦|烦躁|不耐烦|被打扰", "emotion:annoyed", 2),
    (r"害怕|恐惧|吓死|可怕", "emotion:afraid", 2),
    (r"紧张|焦虑|担心|忐忑", "emotion:nervous", 2),
    (r"慌张|惊慌|手忙脚乱|来不及了", "emotion:panicked", 2),
    (r"嫌弃|恶心|反感|咦惹", "emotion:disgusted", 2),
    (r"累|疲惫|困了|没精神", "emotion:tired", 2),
    (r"无聊|没意思|好闲", "emotion:bored", 1),
    (r"抱抱|安慰|陪你|没关系", "emotion:comfort", 1),
)

_STRONG_EMOTION_PATTERNS = {
    "emotion:excited": r"终于|太棒|超级(?:兴奋|激动)|好耶[!！]",
    "emotion:amused": r"笑死|绷不住|哈哈哈|😂😂",
    "emotion:happy": r"太开心|开心[!！]|高兴坏了",
    "emotion:affection": r"太可爱|超级喜欢|狠狠爱了",
    "emotion:hopeful": r"非常期待|迫不及待|等不及了",
    "emotion:playful": r"疯狂卖萌|坏笑[!！]|嘿嘿嘿嘿",
    "emotion:surprised": r"震惊|吓一跳|真的假的[?？]",
    "emotion:speechless": r"太离谱|无语[!！]|麻了[!！]",
    "emotion:helpless": r"完全没办法|只能认了|心累[!！]",
    "emotion:sad": r"太难过|哭死|伤心透了",
    "emotion:wronged": r"太委屈|委屈死了|真的不公平",
    "emotion:frustrated": r"彻底失败|完全做不下去|崩溃了",
    "emotion:angry": r"气死|火大|非常生气",
    "emotion:afraid": r"吓死|太可怕|非常害怕",
    "emotion:panicked": r"来不及了[!！]|彻底慌了|救命[!！]",
}


def display_emotions(text: str, mood_emotion: Any | None) -> list[GalleryEmotionTarget]:
    repeated_punctuation = bool(re.search(r"[!！?？]{2,}", text, re.I))
    weak = bool(re.search(r"(?:有点|一点|稍微|轻微|还算|还好)", text, re.I))
    detected: list[GalleryEmotionTarget] = []
    for pattern, tag, base_intensity in _EMOTION_RULES:
        if not re.search(pattern, text, re.I):
            continue
        strong = repeated_punctuation or bool(
            re.search(_STRONG_EMOTION_PATTERNS.get(tag, r"(?!)"), text, re.I)
        )
        intensity = max(1, min(base_intensity + int(strong) - int(weak), 3))
        confidence = min(0.95, 0.72 + (0.13 if strong else 0.0) - (0.08 if weak else 0.0))
        detected.append(
            GalleryEmotionTarget(
                emotion_tag=tag,
                target_intensity=intensity,
                prominence="secondary",
                weight=0.55,
                confidence=confidence,
            )
        )
    if not detected:
        return []
    detected.sort(key=lambda item: (item.confidence, item.target_intensity), reverse=True)
    primary = detected[0]
    result = [
        GalleryEmotionTarget(
            emotion_tag=primary.emotion_tag,
            target_intensity=primary.target_intensity,
            prominence="primary",
            weight=1.0,
            confidence=primary.confidence,
        )
    ]
    if len(detected) > 1:
        secondary = next(
            (item for item in detected[1:] if item.emotion_tag != primary.emotion_tag),
            None,
        )
        if secondary is not None:
            result.append(
                GalleryEmotionTarget(
                    emotion_tag=secondary.emotion_tag,
                    target_intensity=max(1, secondary.target_intensity - 1),
                    prominence="secondary",
                    weight=0.55,
                    confidence=max(0.55, secondary.confidence - 0.08),
                )
            )
    if len(result) == 1:
        mood_tag = _mood_emotion_tag(mood_emotion)
        if mood_tag and mood_tag != result[0].emotion_tag:
            result.append(
                GalleryEmotionTarget(
                    emotion_tag=mood_tag,
                    target_intensity=1,
                    prominence="secondary",
                    weight=0.15,
                    confidence=0.15,
                )
            )
    return result[:2]


def emotion_facets(
    text: str,
    emotions: tuple[GalleryEmotionTarget, ...] | list[GalleryEmotionTarget],
) -> list[str]:
    rules = (
        (r"确实|同意|懂了", "tone:agree"),
        (r"吐槽|离谱|绷不住", "tone:complain"),
        (r"🤔|疑惑|怎么啦|为什么", "tone:question"),
        (r"加油|辛苦|鼓励", "tone:encourage"),
        (r"早安|晚安", "scene:greeting"),
        (r"对不起|抱歉", "scene:apology"),
        (r"不可以|才不要|不能哦|拒绝", "scene:refuse"),
        (r"稍等|等一下|等等", "scene:wait"),
        (r"好耶|太棒|厉害|谢谢|庆祝|👏", "scene:celebrate"),
    )
    result = [item.emotion_tag for item in emotions]
    if any(
        item.emotion_tag
        in {
            "emotion:excited",
            "emotion:amused",
            "emotion:affection",
            "emotion:grateful",
            "emotion:proud",
            "emotion:relieved",
            "emotion:hopeful",
            "emotion:playful",
        }
        for item in emotions
    ):
        result.append("emotion:happy")
    result.extend(tag for pattern, tag in rules if re.search(pattern, text, re.I))
    if "tone:question" in result:
        result.append("tone:doubt")
    if "scene:refuse" in result:
        result.append("scene:refusal")
    if "scene:wait" in result:
        result.append("scene:waiting")
    return list(dict.fromkeys(result))


def target_payload(item: GalleryEmotionTarget) -> dict[str, object]:
    return {
        "emotion_tag": item.emotion_tag,
        "target_intensity": item.target_intensity,
        "prominence": item.prominence,
        "weight": item.weight,
        "confidence": item.confidence,
    }


def _mood_emotion_tag(value: Any | None) -> str:
    label = ""
    if value is not None:
        labeler = getattr(value, "label", None)
        try:
            label = str(labeler() if callable(labeler) else "").strip().lower()
        except Exception:  # noqa: BLE001
            label = ""
    return {
        "excited": "emotion:excited",
        "happy": "emotion:happy",
        "relaxed": "emotion:calm",
        "content": "emotion:calm",
        "angry": "emotion:angry",
        "anxious": "emotion:nervous",
        "sad": "emotion:sad",
        "bored": "emotion:bored",
    }.get(label, "")
