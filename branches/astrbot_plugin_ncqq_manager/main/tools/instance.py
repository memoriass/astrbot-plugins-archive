import base64
import re

from astrbot.api import logger
from astrbot.api.all import AstrMessageEvent, Image
from astrbot.api.star import StarTools
from astrbot.core.message.message_event_result import MessageChain

from ..core.actions import do_create_instance, do_instance_action
from ..core.approval import create_approval
from ..core.config_reader import do_read_config
from ..core.interaction import do_check_login_status, do_get_qrcode
from ..core.monitoring import (
    do_confirm_instance_action,
    do_get_monitor,
    do_list_assets,
    do_list_files,
    do_list_instances,
)
from ..rendering.html_renderer import render_bindings, render_instances


class InstanceToolsMixin:
    # 动作 → 期望 SSE 事件映射（用于操作后确认）
    _ACTION_EVENT_MAP: dict[str, list[str]] = {
        "start":   ["start"],
        "stop":    ["stop", "die"],
        "restart": ["restart", "start"],
        "pause":   ["pause"],
        "unpause": ["unpause", "start"],
        "kill":    ["kill", "die"],
        "delete":  ["destroy", "die"],
    }

    def _resolve_tool_targets(
        self,
        instance_names: str,
        manager_id: str = "",
    ) -> tuple[str, list[str], str]:
        try:
            selected_manager = self.normalize_manager_id(manager_id)
        except KeyError:
            return "", [], f"未知 ncqq-manager 面板：{manager_id}。可用：{', '.join(self.manager_ids())}"

        targets: list[str] = []
        explicit_manager = bool(str(manager_id or "").strip())
        for raw in re.split(r"[,，、\s]+", instance_names) if str(instance_names).strip() else []:
            if not raw.strip():
                continue
            try:
                item_manager, item_name = self.split_instance_ref(raw, selected_manager)
            except KeyError:
                return "", [], f"未知 ncqq-manager 面板。可用：{', '.join(self.manager_ids())}"
            if item_manager != selected_manager:
                if explicit_manager or targets:
                    return "", [], "一次工具调用暂不支持跨 ncqq-manager 面板批量操作，请按面板拆分。"
                selected_manager = item_manager
            if item_name:
                targets.append(item_name)
        return selected_manager, targets, ""

    async def ncqq_query(
        self,
        event: AstrMessageEvent,
        query: str,
        instance_names: str = "",
        manager_id: str = "",
        file_name: str = "onebot11_uin.json",
        path: str = "",
    ):
        """查询 ncqq 实例信息，涵盖列表、登录状态、监控、日志、资产、配置、文件目录。

        当用户想了解"有哪些实例""谁在线谁掉线""资源占用""看日志""读配置文件""查目录"时使用。
        本工具只读，不执行任何写入或控制操作。

        Args:
            query (string): 查询类型，必须是以下之一：
                "instances" — 列出所有实例及运行状态（含头像、心跳、QQ号）。
                "login"     — 检查指定实例的实时登录状态（是否在线、账号信息）。
                "monitor"   — 读取指定实例的资源占用摘要（CPU/内存/网络）。
                "logs"      — 读取指定实例的容器尾部日志（最近 8 行，已脱敏）。
                "assets"    — 列出管理节点上的镜像与节点资产（仅管理员）。
                "config"    — 读取实例容器内的配置文件内容（仅管理员）。
                "files"     — 列出实例数据目录下的文件与子目录（仅管理员）。
            instance_names (string): 实例名，login/monitor/logs/config/files 时必填；支持逗号分隔多个（login 支持批量）。
            manager_id (string): 目标 ncqq-manager 面板 ID；也可在实例名中使用 manager/instance。
            file_name (string): 仅 query=config 时有效，容器内目标文件名，默认 onebot11_uin.json。
            path (string): 仅 query=files 时有效，相对于实例数据根目录的路径，留空表示根目录。
        """
        sender_id = str(event.get_sender_id())
        is_admin = self.is_plugin_admin(event)
        selected_manager, names, target_error = self._resolve_tool_targets(
            instance_names, manager_id
        )
        if target_error:
            yield event.plain_result(target_error)
            return
        client = self.client_for_manager(selected_manager)

        # --- instances ---
        if query == "instances":
            allowed = await self.get_allowed_instances(sender_id, selected_manager)
            result = await do_list_instances(client, allowed, is_admin)
            if isinstance(result, str):
                yield event.plain_result(result)
                return
            base_url = client.config.get("manager_url", "").rstrip("/")
            for inst in result:
                if inst.get("bot_avatar") and inst["bot_avatar"].startswith("/"):
                    inst["bot_avatar"] = f"{base_url}{inst['bot_avatar']}"
            rendered = await render_instances(result)
            if isinstance(rendered, bytes):
                yield event.chain_result([Image.fromBase64(base64.b64encode(rendered).decode())])
            else:
                yield event.plain_result(rendered)
            mapping = await self.get_user_mapping()
            if any(d.get("nickname") for d in mapping.values()):
                rb = await render_bindings(mapping)
                if isinstance(rb, bytes):
                    yield event.chain_result([Image.fromBase64(base64.b64encode(rb).decode())])
                else:
                    yield event.plain_result(rb)
            return

        # --- login ---
        if query == "login":
            if not names:
                yield event.plain_result("请补充实例名（instance_names）。")
                return
            if not is_admin:
                allowed = await self.get_allowed_instances(sender_id, selected_manager)
                bad = [n for n in names if n not in allowed]
                if bad:
                    yield event.plain_result(f"无权查看以下实例：{'、'.join(bad)}。")
                    return
            lines: list[str] = []
            for name in names:
                p = await do_check_login_status(client, name)
                if p.get("status") == "error":
                    lines.append(f"• {name}：⚠️ 获取失败，请稍后重试")
                elif p.get("logged_in"):
                    uin = p.get("uin", "")
                    nick = p.get("nickname", "")
                    label = f"{nick}({uin})" if uin else nick or "已登录"
                    lines.append(f"• {name}：🟢 在线（{label}）")
                else:
                    lines.append(f"• {name}：🔴 未登录（可能需重新扫码）")
            yield event.plain_result("\n".join(lines))
            return

        # --- monitor / logs ---
        if query in ("monitor", "logs"):
            if not is_admin:
                yield event.plain_result("监控与日志查询仅限管理员。")
                return
            name = instance_names.strip()
            if names:
                name = names[0]
            if not name:
                yield event.plain_result("请补充实例名（instance_names）。")
                return
            yield event.plain_result(await do_get_monitor(client, name, fetch_logs=(query == "logs")))
            return

        # --- assets ---
        if query == "assets":
            if not is_admin:
                yield event.plain_result("资产查询仅限管理员。")
                return
            yield event.plain_result(await do_list_assets(client))
            return

        # --- config ---
        if query == "config":
            if not is_admin:
                yield event.plain_result("配置读取仅限管理员。")
                return
            name = instance_names.strip()
            if names:
                name = names[0]
            if not name:
                yield event.plain_result("请补充实例名（instance_names）。")
                return
            yield event.plain_result(await do_read_config(client, name, file_name))
            return

        # --- files ---
        if query == "files":
            if not is_admin:
                yield event.plain_result("文件目录查询仅限管理员。")
                return
            name = instance_names.strip()
            if names:
                name = names[0]
            if not name:
                yield event.plain_result("请补充实例名（instance_names）。")
                return
            yield event.plain_result(await do_list_files(client, name, path))
            return

        yield event.plain_result(
            f"未知查询类型 '{query}'，支持：instances / login / monitor / logs / assets / config / files。"
        )

    async def ncqq_action(
        self,
        event: AstrMessageEvent,
        action: str,
        instance_names: str = "",
        delete_data: bool = False,
        manager_id: str = "",
    ):
        """对 ncqq 实例执行创建、销毁和生命周期控制。

        仅供新 workflow 内部调用。账号重置和配置写入不在聊天 workflow 中开放。
        纯查询场景（查状态、看日志、读配置）请使用 ncqq_query；扫码请使用 ncqq_qrcode。

        Args:
            action (string): 操作类型，必须是以下之一：
                "start"        — 启动容器。
                "stop"         — 停止容器。
                "restart"      — 重启容器。
                "pause"        — 暂停容器进程。
                "unpause"      — 恢复容器进程。
                "kill"         — 强制终止容器。
                "delete"       — 销毁容器（delete_data 控制是否同时删除数据目录）。
                "create"       — 创建新实例，仅管理员直接执行。
            instance_names (string): 目标实例名，支持逗号分隔多个（create/start/stop 等均支持批量）。
            delete_data (boolean): 仅 action=delete 时有效。true 时同时删除本地数据目录（QQ数据/配置/插件/缓存，不可恢复）；false 时仅移除容器保留数据。用户说"彻底删除""删干净"时为 true，仅说"删除"时为 false。
            manager_id (string): 目标 ncqq-manager 面板 ID；也可在实例名中使用 manager/instance。
        """
        sender_id = str(event.get_sender_id())
        is_admin = self.is_plugin_admin(event)

        selected_manager, names, target_error = self._resolve_tool_targets(
            instance_names, manager_id
        )
        if target_error:
            yield event.plain_result(target_error)
            return
        client = self.client_for_manager(selected_manager)

        # ── create ──────────────────────────────────────────────────────────
        if action == "create":
            if not names:
                yield event.plain_result("请补充实例名（instance_names）。")
                return
            if not is_admin:
                yield event.plain_result("创建实例请使用 create_instance workflow 提交整合审批。")
                return
            results: list[str] = []
            for n in names:
                ok, msg = await do_create_instance(client, n)
                results.append(msg)
            yield event.plain_result("\n".join(results))
            return

        # ── lifecycle: start/stop/restart/pause/unpause/kill/delete ──────────
        _lifecycle = {"start", "stop", "restart", "pause", "unpause", "kill", "delete"}
        if action not in _lifecycle:
            yield event.plain_result(
                f"不支持的操作 '{action}'。支持：start / stop / restart / pause / unpause / kill / delete / create。"
            )
            return

        if not names:
            yield event.plain_result("请补充实例名（instance_names）。")
            return

        if action == "delete":
            if not is_admin:
                allowed = await self.get_allowed_instances(sender_id, selected_manager)
                bad = [n for n in names if n not in allowed]
                if bad:
                    yield event.plain_result(f"以下实例不在你的可操作范围内：{'、'.join(bad)}。如需删除请联系管理员。")
                    return
                ids = []
                for n in names:
                    aid = await create_approval(
                        self,
                        action="delete",
                        params={
                            "instance_name": n,
                            "manager_id": selected_manager,
                            "delete_data": delete_data,
                        },
                        requester_qq=sender_id,
                        group_id=str(event.get_group_id() or ""),
                        description=f"销毁实例 {n}{'（含本地数据）' if delete_data else ''}（申请者: {sender_id}）",
                    )
                    ids.append(aid)
                yield self._approval_notice_batch(event, "销毁实例", list(zip(names, ids)))
                return
            # Admin delete
            results = []
            cleaned: list[str] = []
            for n in names:
                ok, msg = await do_instance_action(client, n, "delete", delete_data=delete_data)
                if ok:
                    _, confirm = await do_confirm_instance_action(
                        client, n, self._ACTION_EVENT_MAP["delete"]
                    )
                    msg = f"{msg}\n{confirm}"
                    cleaned.append(n)
                results.append(msg)
            if cleaned:
                mapping = await self.get_user_mapping()
                changed = False
                for data in mapping.values():
                    for inst in cleaned:
                        lst = data.get("instances", [])
                        refs = {self.format_instance_ref(selected_manager, inst)}
                        if selected_manager == self.default_manager_id():
                            refs.add(inst)
                        for ref in refs:
                            if ref in lst:
                                lst.remove(ref)
                                changed = True
                if changed:
                    await self.save_user_mapping(mapping)
                    results.append(f"已自动解除所有用户与实例 {'、'.join(cleaned)} 的绑定。")
            yield event.plain_result("\n".join(results))
            return

        # Non-destructive lifecycle
        if not is_admin:
            allowed = await self.get_allowed_instances(sender_id, selected_manager)
            bad = [n for n in names if n not in allowed]
            if bad:
                yield event.plain_result(f"以下实例不在你的可操作范围内：{'、'.join(bad)}。请联系管理员完成绑定。")
                return

        results = []
        for n in names:
            ok, msg = await do_instance_action(client, n, action)
            if ok:
                _, confirm = await do_confirm_instance_action(
                    client, n, self._ACTION_EVENT_MAP.get(action, [action])
                )
                msg = f"{msg}\n{confirm}"
            results.append(msg)
        yield event.plain_result("\n".join(results))

    async def ncqq_qrcode(
        self,
        event: AstrMessageEvent,
        instance_name: str,
        manager_id: str = "",
    ):
        """获取指定 ncqq 实例的登录二维码图片。

        当用户说"获取二维码""拉码""扫码登录""帮我拉个码"等含"二维码/扫码/登录码"关键词时调用。
        本工具直接拉取并返回二维码，不再内部自动检查登录状态——如需确认是否需要扫码，
        请先调用 ncqq_query(query="login") 确认实例处于未登录状态后再调用本工具。
        若二维码即将过期，本工具会直接告知，不会自动等待重取；请用户稍候后再次发起请求。

        Args:
            instance_name (string): 目标 ncqq 实例名，必须明确提供。
            manager_id (string): 目标 ncqq-manager 面板 ID；也可在实例名中使用 manager/instance。
        """
        sender_id = str(event.get_sender_id())
        is_admin = self.is_plugin_admin(event)
        selected_manager, names, target_error = self._resolve_tool_targets(
            instance_name, manager_id
        )
        if target_error:
            yield event.plain_result(target_error)
            return
        name = names[0] if names else ""
        client = self.client_for_manager(selected_manager)

        if not name:
            yield event.plain_result("请提供实例名（instance_name）。")
            return

        if not is_admin:
            allowed = await self.get_allowed_instances(sender_id, selected_manager)
            if name not in allowed:
                yield event.plain_result(
                    f"实例 {selected_manager}/{name} 不在你的可操作范围内，请确认实例名或联系管理员。"
                )
                return

        results = await do_get_qrcode(client, name)

        # 判断是否需要私聊发送（群聊触发 + 配置开启）
        is_group = bool(event.get_group_id())
        qrcode_private = self.config.get("qrcode_private", True)
        use_private = is_group and qrcode_private

        has_image = False
        for item in results:
            if isinstance(item, str) and item.startswith("__qr_soon__:"):
                secs = int(item.split(":", 1)[1])
                yield event.plain_result(
                    f"⚠️ 当前二维码仅剩约 {secs} 秒有效期，即将过期，请稍候几秒后重新发送请求。"
                )
            elif isinstance(item, str):
                yield event.plain_result(item)
            elif use_private:
                # 群聊中不直接发图，改为私聊
                if not has_image:
                    has_image = True
                    yield event.plain_result("🔐 为防止他人误扫，二维码已通过私聊发送，请查收。")
                try:
                    chain = MessageChain()
                    chain.chain.append(item)
                    await StarTools.send_message_by_id(
                        type="FriendMessage",
                        id=sender_id,
                        message_chain=chain,
                    )
                except Exception as e:
                    logger.warning("私聊发送二维码失败 (QQ %s): %s", sender_id, e)
                    yield event.plain_result("⚠️ 私聊发送失败，可能未添加好友。以下直接展示：")
                    yield event.chain_result([item])
            else:
                yield event.chain_result([item])

