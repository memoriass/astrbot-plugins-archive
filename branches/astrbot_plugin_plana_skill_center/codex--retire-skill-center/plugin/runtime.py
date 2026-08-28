from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.star.filter.command import GreedyStr
from quart import jsonify, request

from .config import normalize_skill_center_config
from ..skills import CONTRACT_VERSION, SkillCenterManager


class PlanaSkillCenterPlugin(Star):
    """Quarantine and governance center for generated Plana skills."""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = normalize_skill_center_config(config)
        self.enabled = bool(self.config.get("enabled", True))
        self.register_llm_tool = bool(self.config.get("register_llm_tool", False))
        self.enable_write_commands = bool(
            self.config.get("enable_write_commands", False)
        )
        self.manager = SkillCenterManager(
            Path(StarTools.get_data_dir("astrbot_plugin_plana_skill_center")),
            max_body_chars=int(self.config.get("max_skill_body_chars") or 30000),
            allow_dangerous_approval=bool(
                self.config.get("allow_dangerous_approval", False)
            ),
        )

    async def initialize(self) -> None:
        if not self.enabled:
            logger.info("Plana Skill Center disabled")
            return
        self.manager.initialize()
        self._register_web_apis()
        if self.register_llm_tool:
            self._register_llm_tool()
        logger.info("Plana Skill Center initialized")

    async def terminate(self) -> None:
        try:
            self.context.get_llm_tool_manager().remove_func("plana_skill_propose")
        except Exception:
            logger.debug("Plana Skill Center tool unregister skipped", exc_info=True)

    def _register_web_apis(self) -> None:
        self.context.register_web_api(
            "/plana_skill_center/status",
            self._api_status,
            ["GET"],
            "Plana Skill Center status",
        )
        self.context.register_web_api(
            "/plana_skill_center/skills",
            self._api_skills,
            ["GET"],
            "List governed skill drafts",
        )
        self.context.register_web_api(
            "/plana_skill_center/skills/get",
            self._api_skill_get,
            ["GET"],
            "Get a governed skill draft",
        )
        self.context.register_web_api(
            "/plana_skill_center/propose",
            self._api_propose,
            ["POST"],
            "Quarantine and scan a skill draft",
        )
        self.context.register_web_api(
            "/plana_skill_center/approve",
            self._api_approve,
            ["POST"],
            "Approve a quarantined skill draft",
        )
        self.context.register_web_api(
            "/plana_skill_center/reject",
            self._api_reject,
            ["POST"],
            "Reject a governed skill draft",
        )
        self.context.register_web_api(
            "/plana_skill_center/export",
            self._api_export,
            ["POST"],
            "Export an approved skill draft",
        )

    async def _api_status(self):
        if not self._authorized(readonly=True):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        return jsonify(
            self.manager.status(
                loopback_only=True,
                register_llm_tool=self.register_llm_tool,
            )
        )

    async def _api_skills(self):
        if not self._authorized(readonly=True):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        status = str(request.args.get("status", "") or "")
        limit = self._int_arg(request.args.get("limit"), default=50)
        return jsonify(self.manager.list_skills(status=status, limit=limit))

    async def _api_skill_get(self):
        if not self._authorized(readonly=True):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        draft_id = self._int_arg(request.args.get("id"), default=0)
        include_body = str(request.args.get("include_body", "") or "").lower() == "true"
        result = self.manager.get_skill(draft_id, include_body=include_body)
        return jsonify(result), self._status_code(result)

    async def _api_propose(self):
        if not self._authorized(readonly=False):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await self._payload()
        result = self._propose_from_payload(payload)
        return jsonify(result), self._status_code(result)

    async def _api_approve(self):
        if not self._authorized(readonly=False):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await self._payload()
        result = self.manager.approve_skill(
            self._draft_id(payload),
            review_actor=str(payload.get("review_actor") or "http_api"),
        )
        return jsonify(result), self._status_code(result)

    async def _api_reject(self):
        if not self._authorized(readonly=False):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await self._payload()
        result = self.manager.reject_skill(self._draft_id(payload))
        return jsonify(result), self._status_code(result)

    async def _api_export(self):
        if not self._authorized(readonly=False):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await self._payload()
        result = self.manager.export_skill(self._draft_id(payload))
        return jsonify(result), self._status_code(result)

    def _authorized(self, *, readonly: bool) -> bool:
        return self._is_loopback_request()

    def _is_loopback_request(self) -> bool:
        forwarded_headers = ("X-Forwarded-For", "X-Real-IP", "Forwarded")
        if any(request.headers.get(name, "").strip() for name in forwarded_headers):
            return False
        remote = str(request.remote_addr or "").strip().lower()
        return remote in {"127.0.0.1", "::1", "localhost"} or remote.startswith("::ffff:127.")

    async def _payload(self) -> dict[str, Any]:
        if not request.content_length:
            return {}
        payload = await request.get_json(force=True)
        return payload if isinstance(payload, dict) else {}

    def _register_llm_tool(self) -> None:
        self.context.add_llm_tools(PlanaSkillProposeTool(self))

    async def _llm_tool_propose(
        self,
        name: str = "",
        description: str = "",
        body: str = "",
        **kwargs,
    ) -> str:
        result = self.manager.propose_skill(
            name=name,
            description=description,
            body=body,
            source=str(kwargs.get("source") or "agent-created"),
            trust_level=str(kwargs.get("trust_level") or "agent-created"),
            source_uri=str(kwargs.get("source_uri") or ""),
            origin_model=str(kwargs.get("origin_model") or ""),
        )
        return json.dumps(result, ensure_ascii=False)

    @filter.command("plana-skill")
    async def plana_skill_center(
        self,
        event: AstrMessageEvent,
        action: str = "status",
        value: GreedyStr = "",
    ):
        action = action.strip().lower()
        text = str(value or "").strip()
        if action == "status":
            yield event.plain_result(
                "Plana Skill Center: "
                f"enabled={self.enabled} contract={CONTRACT_VERSION} "
                "quarantine=true scan=true approval_required=true "
                "executes_side_effects=false auto_install=false"
            )
            return
        if action == "list":
            result = self.manager.list_skills(status=text, limit=20)
            yield event.plain_result(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if action == "show":
            result = self.manager.get_skill(self._int_value(text), include_body=False)
            yield event.plain_result(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if action == "approve":
            confirmed_text = self._confirmed_write_command(text)
            if not confirmed_text:
                yield event.plain_result(self._write_command_rejected())
                return
            result = self.manager.approve_skill(
                self._int_value(confirmed_text),
                review_actor="command",
            )
            yield event.plain_result(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if action == "reject":
            confirmed_text = self._confirmed_write_command(text)
            if not confirmed_text:
                yield event.plain_result(self._write_command_rejected())
                return
            result = self.manager.reject_skill(self._int_value(confirmed_text))
            yield event.plain_result(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if action == "export":
            confirmed_text = self._confirmed_write_command(text)
            if not confirmed_text:
                yield event.plain_result(self._write_command_rejected())
                return
            result = self.manager.export_skill(self._int_value(confirmed_text))
            yield event.plain_result(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if action == "propose":
            confirmed_text = self._confirmed_write_command(text)
            if not confirmed_text:
                yield event.plain_result(self._write_command_rejected())
                return
            name, body = self._split_command_proposal(confirmed_text)
            result = self.manager.propose_skill(name=name, body=body)
            yield event.plain_result(json.dumps(result, ensure_ascii=False, indent=2))
            return
        yield event.plain_result(
            "Usage: /plana-skill status | list [status] | show <id> | "
            "approve <id> confirm | reject <id> confirm | export <id> confirm | "
            "propose confirm <name> | <body>"
        )

    def _propose_from_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.manager.propose_skill(
            name=str(payload.get("name") or ""),
            description=str(payload.get("description") or ""),
            body=str(payload.get("body") or payload.get("skill") or payload.get("skill_md") or ""),
            source=str(payload.get("source") or "agent-created"),
            trust_level=str(payload.get("trust_level") or "agent-created"),
            source_uri=str(payload.get("source_uri") or ""),
            origin_model=str(payload.get("origin_model") or ""),
        )

    def _draft_id(self, payload: dict[str, Any]) -> int:
        return self._int_arg(payload.get("id") or payload.get("draft_id"), default=0)

    def _status_code(self, result: dict[str, Any]) -> int:
        if result.get("ok"):
            return 200
        if result.get("error") == "skill_not_found":
            return 404
        if result.get("error") == "approval_blocked":
            return 409
        return 400

    def _int_arg(self, value: Any, *, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _int_value(self, value: str) -> int:
        return self._int_arg(str(value or "").split(maxsplit=1)[0], default=0)

    def _confirmed_write_command(self, value: str) -> str:
        if not self.enable_write_commands:
            return ""
        text = str(value or "").strip()
        lowered = text.lower()
        if lowered.startswith("confirm "):
            return text[8:].strip()
        if lowered.endswith(" confirm"):
            return text[:-8].strip()
        return ""

    def _write_command_rejected(self) -> str:
        if not self.enable_write_commands:
            return (
                "Plana Skill Center write commands are disabled; "
                "use the local loopback HTTP API or enable enable_write_commands."
            )
        return "Plana Skill Center write commands require explicit confirm."

    def _split_command_proposal(self, value: str) -> tuple[str, str]:
        if "|" not in value:
            return "Generated Skill", value
        name, body = value.split("|", 1)
        return name.strip(), body.strip()


class PlanaSkillProposeTool(FunctionTool):
    def __init__(self, plugin: PlanaSkillCenterPlugin) -> None:
        super().__init__(
            name="plana_skill_propose",
            description=(
                "Quarantine and scan a generated skill draft. It does not install "
                "or execute the skill."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Skill name.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Short skill description.",
                    },
                    "body": {
                        "type": "string",
                        "description": "SKILL.md body to quarantine and scan.",
                    },
                },
                "required": ["name", "body"],
            },
        )
        self._plugin = plugin

    async def call(self, context: Any, **kwargs: Any) -> ToolExecResult:
        return await self._plugin._llm_tool_propose(
            name=str(kwargs.get("name") or ""),
            description=str(kwargs.get("description") or ""),
            body=str(kwargs.get("body") or ""),
            source=str(kwargs.get("source") or "agent-created"),
            trust_level=str(kwargs.get("trust_level") or "agent-created"),
            source_uri=str(kwargs.get("source_uri") or ""),
            origin_model=str(kwargs.get("origin_model") or ""),
        )
