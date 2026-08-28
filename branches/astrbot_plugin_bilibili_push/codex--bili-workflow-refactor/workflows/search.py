from __future__ import annotations

from astrbot.api import logger

from ..core.http import HttpClient
from .cards import candidate_list_card
from .formatting import format_candidates
from .models import WorkflowRequest
from .pending import store_pending_task
from .results import WorkflowResult
from .utils import clean_html_text, first_text


async def search_up_candidates(keyword: str, limit: int = 8) -> tuple[list[dict], str]:
    if not keyword.strip():
        return [], "搜索关键词不能为空。"

    client = await HttpClient.get_client()
    try:
        response = await client.get(
            "https://api.bilibili.com/x/web-interface/search/type",
            params={"search_type": "bili_user", "keyword": keyword, "page": 1},
            timeout=10,
        )
        if response.status_code != 200:
            return [], f"搜索失败，HTTP {response.status_code}。"
        data = response.json()
        if data.get("code") != 0:
            return [], f"搜索失败，code={data.get('code')}。"
    except Exception as exc:
        logger.error(f"Bilibili workflow search failed: {exc}", exc_info=True)
        return [], f"搜索失败：{exc}"

    results = []
    for item in data.get("data", {}).get("result", [])[:limit]:
        face = str(item.get("upic") or "")
        if face.startswith("//"):
            face = f"https:{face}"
        results.append(
            {
                "uid": str(item.get("mid") or ""),
                "username": clean_html_text(item.get("uname") or ""),
                "face": face,
                "follower": item.get("fans"),
            }
        )
    return [item for item in results if item["uid"]], ""


async def run_search_up(plugin, event, request: WorkflowRequest) -> str:
    payload = {"target": request.target, **request.params}
    keyword = first_text(payload, "keyword", "query", "target", "name")
    limit = int(payload.get("limit") or 8)
    candidates, error = await search_up_candidates(keyword, limit=limit)
    if error:
        return error
    if not candidates:
        return f"未找到关键词“{keyword}”对应的 UP 主。"

    task_id = await store_pending_task(
        plugin,
        event,
        request,
        kind="up_candidates",
        payload={
            "keyword": keyword,
            "candidates": candidates,
            "mode": "search_only",
        },
    )
    text = (
        format_candidates(candidates, title=f"搜索结果（{keyword}）")
        + f"\n\n任务ID: {task_id}\n"
        + f"如需选择候选，请发送 `bili{task_id[-4:]} <序号>`。"
    )
    return WorkflowResult(
        text=text,
        display_text=(
            format_candidates(candidates, title=f"搜索结果（{keyword}）")
            + "\n\n引用这条消息回复序号即可选择候选。"
        ),
        task_id=task_id,
        cards=[candidate_list_card(
            candidates,
            f"搜索结果: {keyword}",
            "引用这条消息回复序号即可选择候选，不会写入订阅。",
        )],
    )
