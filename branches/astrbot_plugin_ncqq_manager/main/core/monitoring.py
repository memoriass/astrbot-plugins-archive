from urllib.parse import quote

from astrbot.api import logger

from .client import NCQQClient
from .sanitization import sanitize_text


def _action_label(action: str) -> str:
    return {
        "start": "启动",
        "stop": "停止",
        "restart": "重启",
        "pause": "暂停",
        "unpause": "恢复运行",
        "kill": "强制结束",
        "die": "进程退出",
        "destroy": "容器删除",
        "create": "容器创建",
    }.get(action, action)


def _sanitize_text(text: str) -> str:
    masked = sanitize_text(text.strip())
    if len(masked) > 180:
        masked = quote(masked[:177], safe="/:=@?&._- ") + "..."
    return masked


def _format_last_event(last_event: dict | None) -> str:
    if not isinstance(last_event, dict) or not last_event:
        return "最近事件：无"
    action = _action_label(
        str(last_event.get("action") or last_event.get("status") or "unknown")
    )
    event_time = last_event.get("time")
    if event_time in (None, ""):
        return f"最近事件：{action}"
    return f"最近事件：{action} @ {event_time}"


async def do_list_instances(
    client: NCQQClient, allowed_instances: list, is_admin: bool
) -> list | str:
    """Return containers list on success, or an error str on failure."""
    try:
        res = await client.make_request("GET", "/api/containers")
        containers = res.get("containers", [])

        if not is_admin:
            containers = [c for c in containers if c.get("name") in allowed_instances]

        if not containers:
            return "当前没有你有权限查看的实例正在运行。"

        return containers
    except Exception as e:
        logger.warning("列出实例失败: %s", e)
        return "网络或配置错误，请稍后重试。"


async def do_list_assets(client: NCQQClient) -> str:
    try:
        images_res = await client.make_request("GET", "/api/images")
        nodes_res = await client.make_request("GET", "/api/nodes")
        images = (
            images_res.get("images", []) if isinstance(images_res, dict) else images_res
        )
        nodes = nodes_res.get("nodes", []) if isinstance(nodes_res, dict) else nodes_res
        image_names = [str(item.get("name") or item) for item in images[:10]]
        node_names = [str(item.get("id") or item.get("name") or item) for item in nodes[:10]]
        lines = [
            "资产概览：",
            f"├─ 镜像 ({len(images)}个)：{'、'.join(image_names) if image_names else '无'}",
            f"└─ 节点 ({len(nodes)}个)：{'、'.join(node_names) if node_names else '无'}",
        ]
        return "\n".join(lines)
    except Exception as e:
        logger.warning("资产拉取失败: %s", e)
        return "资产拉取失败，请稍后重试。"


async def do_list_files(client: NCQQClient, instance_name: str, path: str = "") -> str:
    """列出容器数据目录下的文件和子目录。"""
    try:
        url = f"/api/containers/{instance_name}/files"
        if path:
            url += f"?path={quote(path, safe='/')}"
        res = await client.make_request("GET", url)
        files = res.get("files", []) if isinstance(res, dict) else []
        folders = res.get("folders", []) if isinstance(res, dict) else []
        current = res.get("current_path", path) if isinstance(res, dict) else path
        folder_names = [str(f.get("name", "")) for f in folders[:20] if f.get("name")]
        file_names = [str(f.get("name", "")) for f in files[:20] if f.get("name")]
        return (
            f"实例 {instance_name} 当前路径：{current or '/'}\\n"
            f"├─ 目录 ({len(folders)} 个)：{'、'.join(folder_names) if folder_names else '无'}\\n"
            f"└─ 文件 ({len(files)} 个)：{'、'.join(file_names) if file_names else '无'}"
        )
    except Exception as e:
        logger.warning("文件列表获取失败 %s: %s", instance_name, e)
        return "文件列表获取失败，请稍后重试。"


async def do_get_radar_endpoints(client: NCQQClient) -> list:
    """读取服务端雷达端点库，返回 [{alias, url, token}] 列表。"""
    try:
        res = await client.make_request("GET", "/api/botshepherd/radar/endpoints")
        return res.get("endpoints", []) if isinstance(res, dict) else []
    except Exception:
        return []


async def do_get_stats(
    client: NCQQClient, instance_name: str
) -> dict:
    """获取容器 stats（含 last_event 字段）。"""
    res = await client.make_request(
        "GET", f"/api/containers/{instance_name}/stats"
    )
    return res if isinstance(res, dict) else {}


async def do_watch_events_sse(
    client: NCQQClient,
    instance_name: str,
    timeout: int = 60,
) -> list[dict]:
    """短时订阅单实例 SSE 事件流。"""
    return await client.stream_events(instance_name, timeout=timeout)


async def do_confirm_instance_action(
    client: NCQQClient,
    instance_name: str,
    expected_actions: list[str],
    timeout: int = 10,
) -> tuple[bool, str]:
    """短暂等待 SSE，确认实例动作已触发预期生命周期事件。

    返回 (confirmed: bool, message: str)。
    """
    try:
        events = await do_watch_events_sse(client, instance_name, timeout=timeout)
    except Exception as e:
        logger.warning("SSE 动作确认失败 %s: %s", instance_name, e)
        return False, "动作已提交，状态确认暂时失败，请稍后手动查看实例状态。"

    normalized = {str(a).strip().lower() for a in expected_actions if str(a).strip()}
    matched = []
    for event in events:
        action = str(event.get("action") or event.get("status") or "").strip().lower()
        if action in normalized:
            matched.append(event)

    if matched:
        latest = matched[-1]
        latest_action = _action_label(
            str(latest.get("action") or latest.get("status") or "状态变更")
        )
        return True, f"实例 {instance_name} 已收到动作反馈：{latest_action}。"

    if events:
        return False, (
            f"实例 {instance_name} 的操作已提交，但在 {timeout} 秒内还未等到预期状态变化，请稍后再查看一次。"
        )

    return False, f"动作已提交，但在 {timeout} 秒内未收到实例 {instance_name} 的状态变化消息。"


async def do_get_monitor(
    client: NCQQClient, instance_name: str, fetch_logs: bool
) -> str:
    try:
        if fetch_logs:
            res = await client.make_request(
                "GET", f"/api/containers/{instance_name}/logs?lines=30"
            )
            logs = res.get("logs", "") if isinstance(res, dict) else str(res)
            log_lines = [line.strip() for line in str(logs).splitlines() if line.strip()]
            preview = [_sanitize_text(line) for line in log_lines[-8:]]
            if not preview:
                return f"实例 {instance_name} 最近暂无可用日志。"
            return (
                f"实例 {instance_name} 最近日志摘要（最多 8 行）：\n"
                + "\n".join(preview)
            )

        res = await do_get_stats(client, instance_name)
        lines = [
            f"实例：{instance_name}",
            f"CPU：{res.get('cpu_percent', 'unknown')}%",
            f"内存：{res.get('mem_usage_mb', 'unknown')}MB / {res.get('mem_limit_mb', 'unknown')}MB",
            f"网络：RX {res.get('net_rx_mb', 'unknown')}MB / TX {res.get('net_tx_mb', 'unknown')}MB",
            _format_last_event(res.get("last_event")),
        ]
        return "\n".join(lines)
    except Exception as e:
        logger.warning("监控调用失败 %s: %s", instance_name, e)
        return "监控调用失败，请稍后重试。"
