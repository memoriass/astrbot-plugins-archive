from astrbot.api import logger
from .client import NCQQClient


def _action_label(action: str) -> str:
    return {
        "start": "启动",
        "stop": "停止",
        "restart": "重启",
        "pause": "暂停",
        "unpause": "恢复运行",
        "kill": "强制结束",
        "delete": "删除",
    }.get(action, action)


async def do_create_instance(client: NCQQClient, instance_name: str) -> tuple[bool, str]:
    try:
        await client.make_request("POST", "/api/containers", json={"name": instance_name})
        return True, f"实例 {instance_name} 的创建请求已提交，请稍后再查看运行状态。"
    except Exception as e:
        logger.warning("创建实例 %s 失败: %s", instance_name, e)
        return False, f"实例 {instance_name} 创建失败，请稍后重试或联系管理员。"


async def do_instance_action(
    client: NCQQClient,
    instance_name: str,
    action: str,
    delete_data: bool = False,
) -> tuple[bool, str]:
    try:
        url = f"/api/containers/{instance_name}/action?action={action}"
        if action == "delete" and delete_data:
            url += "&delete_data=true"
        await client.make_request("POST", url)
        suffix = "（含本地数据）" if action == "delete" and delete_data else ""
        return True, f"实例 {instance_name} 的{_action_label(action)}请求已提交{suffix}。"
    except Exception as e:
        logger.warning("实例 %s 执行 %s 失败: %s", instance_name, action, e)
        return False, f"实例 {instance_name} 的{_action_label(action)}失败，请稍后重试或联系管理员。"


async def do_inject_by_alias(
    client: NCQQClient,
    alias: str,
    target: str,
    container_name: str = "",
    conn_id: str = "",
    uin: str = "default",
) -> tuple[bool, str]:
    """通过雷达端点别名执行注入。

    target='bs': 将别名对应端点追加到指定 BS connection 的 target_endpoints（热重载立即生效）。
    target='nc': 将别名对应端点注入指定容器的 websocketClients（需重载 NapCat 配置生效）。
    """
    try:
        payload: dict = {"alias": alias, "target": target, "uin": uin}
        if target == "bs":
            payload["conn_id"] = conn_id or container_name
        else:
            payload["container_name"] = container_name
        res = await client.make_request(
            "POST", "/api/botshepherd/radar/inject-by-alias", json=payload
        )
        status = res.get("status", "unknown") if isinstance(res, dict) else "unknown"
        msg = res.get("message", "") if isinstance(res, dict) else str(res)
        if status == "ok":
            detail = msg.strip()
            if detail:
                return True, f"接入成功。{detail}"
            return True, "接入成功。"
        logger.warning(
            "注入失败 alias=%s target=%s conn_id=%s status=%s message=%s",
            alias, target, conn_id or container_name, status, msg,
        )
        hint = f"原因：{msg.strip()}" if msg.strip() else "后端未返回具体原因，请检查 BotShepherd 连接是否已注册。"
        return False, f"接入失败，{hint}"
    except Exception as e:
        logger.warning("注入 alias=%s target=%s 失败: %s", alias, target, e)
        return False, "接入失败，请稍后重试或联系管理员。"
