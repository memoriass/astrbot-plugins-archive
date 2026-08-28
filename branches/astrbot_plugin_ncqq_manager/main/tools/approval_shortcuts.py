"""Approval notice and shortcut parsing helpers."""

from __future__ import annotations

import re

from astrbot.api.all import AstrMessageEvent
from astrbot.core.message.components import At, Plain, Reply

from ..core.approval import list_approvals


class ApprovalShortcutMixin:
    _APPROVAL_ID_RE = re.compile(r"[A-Z0-9]{6}")
    _APPROVAL_APPROVE_RE = re.compile(
        r"^\s*((批准|同意|通过|确认)(?:\s|$|[，。,.!！:：]|[A-Z0-9]|全部|所有)|(APPROVE|YES|OK)(?:\s|$|[，。,.!！:：]|[A-Z0-9]|ALL))",
        re.IGNORECASE,
    )
    _APPROVAL_REJECT_RE = re.compile(
        r"^\s*((拒绝|驳回|否决|不同意|不通过|不批准|取消)(?:\s|$|[，。,.!！:：]|[A-Z0-9]|全部|所有)|(REJECT|NO|CANCEL)(?:\s|$|[，。,.!！:：]|[A-Z0-9]|ALL))",
        re.IGNORECASE,
    )

    def _approval_admin_mentions(self) -> list:
        admins = self.get_astrbot_admins()
        if not admins:
            return [Plain("请管理员审批。")]
        chain = [Plain("请 ")]
        for admin in admins:
            chain.append(At(qq=admin))
            chain.append(Plain(" "))
        chain.append(Plain("审批。"))
        return chain

    def _approval_notice_single(
        self,
        event: AstrMessageEvent,
        action_label: str,
        approval_id: str,
        extra_text: str = "",
    ):
        chain = [
            Plain(
                f"⚠️ {action_label}属于高权限操作，已提交审批。\n"
                f"审批 ID：{approval_id}\n"
                "状态：已进入审批任务队列，等待管理员处理。\n"
            )
        ]
        chain.extend(self._approval_admin_mentions())
        chain.append(
            Plain(
                f"\n管理员可直接回复：批准 {approval_id} / 拒绝 {approval_id}。"
                "\n也可以引用本条审批消息，只回复：批准 / 拒绝。"
            )
        )
        if extra_text:
            chain.append(Plain("\n" + extra_text))
        return event.chain_result(chain)

    def _approval_notice_batch(
        self,
        event: AstrMessageEvent,
        action_label: str,
        name_id_pairs: list[tuple[str, str]],
    ):
        id_lines = "\n".join(f"  {n} → {aid}" for n, aid in name_id_pairs)
        chain = [
            Plain(
                f"⚠️ {action_label}属于高权限操作，已提交 {len(name_id_pairs)} 条审批。\n"
                "状态：已进入审批任务队列，等待管理员处理。\n"
                f"{id_lines}\n"
            )
        ]
        chain.extend(self._approval_admin_mentions())
        chain.append(
            Plain(
                "\n管理员可回复：批准 <审批ID> / 拒绝 <审批ID>。"
                "\n如果引用本条批量审批消息，请带具体 ID；如需全部处理，请明确写“批准全部”或“拒绝全部”。"
            )
        )
        return event.chain_result(chain)

    async def get_pending_approvals(self) -> dict:
        return await self.get_kv_data("pending_approvals", {})

    async def save_pending_approvals(self, approvals: dict) -> None:
        await self.put_kv_data("pending_approvals", approvals)

    def _approval_decision(self, text: str) -> str:
        if self._APPROVAL_REJECT_RE.match(text or ""):
            return "reject"
        if self._APPROVAL_APPROVE_RE.match(text or ""):
            return "approve"
        return ""

    def _approval_ids_from_text(self, text: str) -> list[str]:
        ids: list[str] = []
        raw = text or ""
        upper = raw.upper()
        for match in self._APPROVAL_ID_RE.finditer(upper):
            start, end = match.span()
            if start > 0 and self._is_ascii_alnum(upper[start - 1]):
                continue
            if end < len(upper) and self._is_ascii_alnum(upper[end]):
                continue
            raw_token = raw[start:end]
            if raw_token.isalpha() and raw_token.islower():
                continue
            approval_id = match.group(0)
            if approval_id not in ids:
                ids.append(approval_id)
        return ids

    @staticmethod
    def _is_ascii_alnum(value: str) -> bool:
        return bool(value and value.isascii() and value.isalnum())

    def _approval_ids_from_reply(self, reply_comp: Reply | None) -> list[str]:
        if reply_comp is None:
            return []
        parts: list[str] = []
        for attr in ("message_str", "text"):
            value = getattr(reply_comp, attr, "")
            if value:
                parts.append(str(value))
        chain = getattr(reply_comp, "chain", None) or []
        for comp in chain:
            if isinstance(comp, Plain) and comp.text:
                parts.append(str(comp.text))
        return self._approval_ids_from_text("\n".join(parts))

    def _approval_reply_may_target_bot(
        self,
        event: AstrMessageEvent,
        reply_comp: Reply,
    ) -> bool:
        quoted_sender = str(
            getattr(reply_comp, "sender_id", "")
            or getattr(reply_comp, "qq", "")
            or ""
        )
        self_id = str(event.get_self_id() or "")
        return bool(quoted_sender and self_id and quoted_sender == self_id)

    async def _has_group_approvals(self, event: AstrMessageEvent) -> bool:
        group_id = str(event.get_group_id() or "")
        if not group_id:
            return False
        for item in await list_approvals(self):
            if str(item.get("group_id") or "") == group_id:
                return True
        return False
