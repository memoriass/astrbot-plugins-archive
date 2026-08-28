from astrbot.api.all import AstrMessageEvent

from ..core.actions import do_inject_by_alias
from ..core.approval import create_approval
from ..core.monitoring import do_get_radar_endpoints


class BackendToolsMixin:
    async def ncqq_backend(
        self,
        event: AstrMessageEvent,
        action: str,
        alias: str = "",
        instance_names: str = "",
        manager_id: str = "",
    ):
        """Inject an existing backend endpoint into one or more ncqq instances.

        This is an internal helper for the connect_backend workflow. Endpoint
        creation/removal and manual binding management are intentionally not
        exposed in chat workflows.
        """
        sender_id = str(event.get_sender_id())
        is_admin = self.is_plugin_admin(event)
        selected_manager, targets, target_error = self._resolve_tool_targets(
            instance_names, manager_id
        )
        if target_error:
            yield event.plain_result(target_error)
            return
        client = self.client_for_manager(selected_manager)

        if action != "inject":
            yield event.plain_result("不支持的后端操作。connect_backend workflow 仅允许 inject。")
            return

        endpoints = await do_get_radar_endpoints(client)
        matched = next(
            (item for item in endpoints if alias.lower() in item.get("alias", "").lower()),
            None,
        )
        if not matched:
            yield event.plain_result(f"未找到别名含 '{alias}' 的后端端点，请先在管理台确认端点。")
            return
        resolved_alias = matched["alias"]

        if not targets:
            yield event.plain_result("后端接入流程需要明确目标实例。")
            return

        if not is_admin:
            allowed = await self.get_allowed_instances(sender_id, selected_manager)
            bad = [name for name in targets if name not in allowed]
            if bad:
                yield event.plain_result(
                    f"以下实例不在你的可操作范围内：{'、'.join(bad)}。"
                )
                return
            ids = []
            for name in targets:
                aid = await create_approval(
                    self,
                    action="inject_backend",
                    params={
                        "alias": resolved_alias,
                        "manager_id": selected_manager,
                        "instance_name": name,
                    },
                    requester_qq=sender_id,
                    group_id=str(event.get_group_id() or ""),
                    description=f"接入后端 {resolved_alias} -> 实例 {name}（申请者: {sender_id}）",
                )
                ids.append(aid)
            yield self._approval_notice_batch(event, "接入后端", list(zip(targets, ids)))
            return

        results: list[str] = []
        for name in targets:
            _, msg = await do_inject_by_alias(
                client,
                alias=resolved_alias,
                target="bs",
                conn_id=name,
            )
            results.append(f"[{name}] {msg}")
        yield event.plain_result(f"批量接入后端 {resolved_alias}：\n" + "\n".join(results))
