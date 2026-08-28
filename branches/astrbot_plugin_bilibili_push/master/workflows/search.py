from __future__ import annotations

from astrbot.api import logger

from ..core.http import HttpClient
from ..core.network_retry import get_with_retry
from .candidate_analysis import analyze_search_candidates
from .cards import candidate_list_card
from .entity_resolver import resolve_up_reference
from .formatting import format_candidates
from .models import WorkflowRequest
from .pending import store_pending_task
from .resolver_stats import record_resolver_event
from .results import WorkflowResult
from .utils import clean_html_text, first_text


async def search_up_candidates(keyword: str, limit: int = 8) -> tuple[list[dict], str]:
    if not keyword.strip():
        return [], "搜索关键词不能为空。"

    client = await HttpClient.get_client()
    try:
        response = await get_with_retry(
            client,
            "https://api.bilibili.com/x/web-interface/search/type",
            label=f"Bilibili UP 搜索 {keyword}",
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


async def run_search_up(plugin, event, request: WorkflowRequest) -> WorkflowResult | str:
    payload = {"target": request.target, **request.params}
    keyword = first_text(payload, "keyword", "query", "target", "name")
    limit = int(payload.get("limit") or 8)
    resolved = await resolve_up_reference(plugin, event, keyword)
    if resolved and resolved.source != "uid":
        candidates = [resolved.as_candidate()]
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
        return WorkflowResult(
            text=format_candidates(candidates, title=f"搜索结果（{keyword}）"),
            display_text=(
                format_candidates(candidates, title=f"搜索结果（{keyword}）")
                + "\n\n引用这条消息回复序号即可选择候选。"
            ),
            task_id=task_id,
            card_intent=_search_card_intent(request),
            cards=[candidate_list_card(
                candidates,
                f"搜索结果: {keyword}",
                "引用这条消息回复序号即可选择候选。",
            )],
        )

    candidates, error = await search_up_candidates(keyword, limit=limit)
    if error:
        record_resolver_event(plugin, "error", source="bili_search")
        return error
    if not candidates:
        return f"未找到关键词“{keyword}”对应的 UP 主。"
    record_resolver_event(plugin, "bili_search", source="bili_user_search")

    selection = None
    if _should_analyze_search_candidates(plugin, request):
        selection = await analyze_search_candidates(
            plugin,
            event,
            keyword,
            candidates,
            intent="search_up",
        )
    recommended_uid = ""
    recommendation = ""
    if selection:
        recommended_uid = str(selection.candidate.get("uid") or "")
        recommendation = (
            f"\n\nAI 推荐：{selection.candidate.get('username')} | "
            f"UID={recommended_uid} | 置信度 {selection.confidence:.0%}\n"
            f"依据：{selection.reason}"
        )

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
        + recommendation
        + "\n\n如需选择候选，请引用这条消息回复序号。"
    )
    return WorkflowResult(
        text=text,
        display_text=(
            format_candidates(candidates, title=f"搜索结果（{keyword}）")
            + recommendation
            + "\n\n引用这条消息回复序号即可选择候选。"
        ),
        task_id=task_id,
        card_intent=_search_card_intent(request),
        cards=[candidate_list_card(
            candidates,
            f"搜索结果: {keyword}",
            "引用这条消息回复序号即可选择候选，不会写入订阅。",
            recommended_uid=recommended_uid,
        )],
    )


def _search_card_intent(request: WorkflowRequest) -> str:
    if (
        request.params.get("silent") is True
        or request.params.get("model_context") is True
    ):
        return "model_context"
    return "user_action"


def _should_analyze_search_candidates(plugin, request: WorkflowRequest) -> bool:
    if not getattr(plugin, "enable_ai_candidate_analysis", True):
        return False
    return not (
        request.params.get("silent") is True
        or request.params.get("model_context") is True
    )
