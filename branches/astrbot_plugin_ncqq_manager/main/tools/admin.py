"""Admin approval tools for ncqq manager."""

from __future__ import annotations

import time

from astrbot.api.all import AstrMessageEvent

from ..core.actions import do_create_instance, do_inject_by_alias, do_instance_action
from ..core.approval import (
    claim_approval,
    list_approvals,
)


class AdminToolsMixin:
    async def ncqq_approval(
        self,
        event: AstrMessageEvent,
        action: str,
        approval_id: str = "",
        reason: str = "",
    ):
        """查看、批准或拒绝 ncqq 高权限操作的待审批请求。

        当管理员要处理积压审批、批准或驳回某条申请时调用。
        仅 AstrBot 管理员可使用；普通用户提交的高权限操作（删除实例、创建实例、覆写配置等）会生成审批记录，等待管理员在此处理。

        Args:
            action (string): 操作类型，必须是以下之一：
                "list"    — 列出所有未过期的待审批请求（含申请描述、ID、等待时长）。
                "approve" — 批准并立即执行指定审批请求，执行后记录自动删除。
                "reject"  — 拒绝并删除指定审批请求，可附带拒绝原因。
            approval_id (string): approve/reject 时必填，六位审批 ID（大小写不敏感），例如 'AB12CD'。
            reason (string): 仅 action=reject 时有效，可选拒绝原因。
        """
        if not self.is_plugin_admin(event):
            yield event.plain_result("此功能仅限 AstrBot 管理员使用。")
            return

        # ── list ──────────────────────────────────────────────────────────────
        if action == "list":
            records = await list_approvals(self)
            if not records:
                yield event.plain_result("当前没有待处理的审批请求。")
                return
            lines = ["⏳ 待审批请求列表："]
            for r in records:
                age_min = int((time.time() - r.get("created_at", 0)) / 60)
                lines.append(
                    f"• [{r['approval_id']}] {r['description']}\n"
                    f"   申请者: {r['requester_qq']} | 已等待 {age_min} 分钟"
                )
            yield event.plain_result("\n\n".join(lines))
            return

        # ── approve ───────────────────────────────────────────────────────────
        if action == "approve":
            aid = approval_id.strip().upper()
            if not aid:
                yield event.plain_result("请提供审批 ID（approval_id）。")
                return
            record = await claim_approval(self, aid)
            if not record:
                yield event.plain_result(f"未找到编号 [{aid}] 的审批请求，可能已处理或已过期。")
                return
            yield event.plain_result(f"开始处理审批 [{aid}]：{record['description']}")
            result_msg = await self._dispatch_approved_action(record["action"], record["params"])
            yield event.plain_result(f"审批 [{aid}] 已处理完成。\n{result_msg}")
            return

        # ── reject ────────────────────────────────────────────────────────────
        if action == "reject":
            aid = approval_id.strip().upper()
            if not aid:
                yield event.plain_result("请提供审批 ID（approval_id）。")
                return
            record = await claim_approval(self, aid)
            if not record:
                yield event.plain_result(f"未找到编号 [{aid}] 的审批请求，可能已处理或已过期。")
                return
            msg = f"审批 [{aid}] 已拒绝：{record['description']}"
            if reason:
                msg += f"\n拒绝原因：{reason}"
            yield event.plain_result(msg)
            return

        yield event.plain_result(f"不支持的操作 '{action}'，支持：list / approve / reject。")


    # ------------------------------------------------------------------
    # Internal dispatcher for approved actions
    # ------------------------------------------------------------------

    async def _dispatch_approved_action(self, action: str, params: dict) -> str:
        """将已批准的审批记录分发到对应 handler 执行并返回结果文本。

        支持的 action 键：create_instance / delete / inject_backend。
        """
        handlers = {
            "create_instance":       self._handle_create_instance_flow,
            "delete":                self._handle_delete,
            "inject_backend":        self._handle_inject_backend,
        }
        handler = handlers.get(action)
        if handler is None:
            return f"暂不支持处理该审批类型：{action}。请联系管理员检查配置。"
        try:
            return await handler(params)
        except KeyError as exc:
            missing = str(exc.args[0]) if exc.args else "unknown"
            return f"审批目标 ncqq-manager 面板不存在或参数缺失：{missing}。请检查配置。"
        except Exception:
            return "审批执行过程中出现异常，请稍后重试或检查后台日志。"

    # --- 各 action 的具体处理方法 ---

    async def _handle_create_instance_flow(self, params: dict) -> str:
        inst_name = params["instance_name"]
        manager_id = self.normalize_manager_id(params.get("manager_id", ""))
        client = self.client_for_manager(manager_id)
        backend_alias = str(params.get("backend_alias") or "").strip()
        bind_qq = str(params.get("bind_qq") or "").strip()
        nickname = str(params.get("nickname") or "").strip()

        results: list[str] = []
        exists = False
        try:
            payload = await client.make_request("GET", "/api/containers")
            containers = payload.get("containers", []) if isinstance(payload, dict) else []
            exists = any(
                str(item.get("name") or "").strip().lstrip("/") == inst_name
                for item in containers
                if isinstance(item, dict)
            )
        except Exception:
            results.append("容器列表读取失败，将直接尝试创建。")

        create_ok = exists
        if exists:
            results.append(f"实例 {inst_name} 已存在，跳过创建。")
        else:
            create_ok, msg = await do_create_instance(client, inst_name)
            results.append(msg)

        if create_ok and bind_qq:
            mapping = await self.get_user_mapping()
            if bind_qq not in mapping:
                mapping[bind_qq] = {"nickname": "", "instances": []}
            instances = mapping[bind_qq].setdefault("instances", [])
            instance_ref = self.format_instance_ref(manager_id, inst_name)
            if instance_ref not in instances:
                instances.append(instance_ref)
                results.append(f"已绑定实例 {instance_ref} -> QQ {bind_qq}。")
            else:
                results.append(f"实例 {instance_ref} 与 QQ {bind_qq} 的绑定已存在。")
            if nickname:
                mapping[bind_qq]["nickname"] = nickname
            await self.save_user_mapping(mapping)

        if create_ok and backend_alias:
            _, msg = await do_inject_by_alias(
                client,
                alias=backend_alias,
                target="bs",
                conn_id=inst_name,
            )
            results.append(f"后端接入 {backend_alias}: {msg}")

        if create_ok:
            results.append("后续登录请让用户执行登录恢复流程获取二维码。")
        return "\n".join(results)

    async def _handle_delete(self, params: dict) -> str:
        inst_name = params["instance_name"]
        manager_id = self.normalize_manager_id(params.get("manager_id", ""))
        client = self.client_for_manager(manager_id)
        ok, msg = await do_instance_action(
            client, inst_name, "delete", delete_data=params.get("delete_data", False)
        )
        if ok:
            mapping = await self.get_user_mapping()
            changed = False
            for data in mapping.values():
                insts = data.get("instances", [])
                refs = {self.format_instance_ref(manager_id, inst_name)}
                if manager_id == self.default_manager_id():
                    refs.add(inst_name)
                for ref in refs:
                    if ref in insts:
                        insts.remove(ref)
                        changed = True
            if changed:
                await self.save_user_mapping(mapping)
                msg += f"\n已自动解除所有用户与实例 {manager_id}/{inst_name} 的绑定。"
        return msg

    async def _handle_inject_backend(self, params: dict) -> str:
        manager_id = self.normalize_manager_id(params.get("manager_id", ""))
        client = self.client_for_manager(manager_id)
        _, msg = await do_inject_by_alias(
            client, alias=params["alias"], target="bs", conn_id=params["instance_name"]
        )
        return msg

