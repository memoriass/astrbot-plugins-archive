from .branches import is_bili_dispatch_candidate
from .models import WorkflowRequest


EXPLICIT_BILI_COMMANDS = (
    "添加b站订阅",
    "添加b站直播",
    "取消b站订阅",
    "取消b站直播",
    "删除b站订阅",
    "删除b站直播",
    "b站订阅列表",
    "b站登录状态",
    "b站登录",
    "b站扫码",
    "b站搜索",
    "bilibili 添加订阅",
    "bilibili 添加直播",
    "bilibili 订阅列表",
    "bilibili 登录",
    "bilibili 搜索",
    "add_bili_sub",
    "add_bili_live",
    "del_bili_sub",
    "del_bili_live",
    "list_bili_sub",
    "search_bili",
)


def workflow_from_natural_language(text: str) -> WorkflowRequest | None:
    raw = str(text or "").strip()
    if not raw or not is_bili_dispatch_candidate(raw):
        return None
    return WorkflowRequest(
        "ai_dispatch",
        target=raw,
        params={"text": raw},
        source="natural",
    )


def is_explicit_bili_command(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    candidates = {raw}
    if raw.startswith("/"):
        candidates.add(raw[1:].lstrip())
    parts = raw.split(maxsplit=1)
    if len(parts) == 2:
        candidates.add(parts[1].strip())
    return any(_starts_with_command(value) for value in candidates)


def _starts_with_command(text: str) -> bool:
    lowered = text.lower()
    for command in EXPLICIT_BILI_COMMANDS:
        normalized = command.lower()
        if not lowered.startswith(normalized):
            continue
        rest = lowered[len(normalized):]
        if not rest or rest[0].isspace() or rest[0] in ":：,，;；":
            return True
    return False
