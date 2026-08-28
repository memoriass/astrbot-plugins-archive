from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


_RISK_LEVELS = {"read_only", "state_change", "destructive", "external_execution"}
_DECISIONS = {"allow", "confirm", "deny"}


@dataclass(frozen=True, slots=True)
class DomainPluginDescriptor:
    schema_version: int
    domain_id: str
    owner: str
    profile: str
    tool_name: str
    aliases: tuple[str, ...] = ()
    service_ref: str = ""
    natural_input_field: str = "target"
    dispatch_workflow: str = "ai_dispatch"
    read_operations: tuple[str, ...] = ()
    write_operations: tuple[str, ...] = ()
    direct_dispatch: bool = False
    supports_continuation: bool = True
    discussion_guard: bool = True

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(f"unsupported domain harness schema: {self.schema_version}")
        for field_name in (
            "domain_id",
            "owner",
            "profile",
            "tool_name",
            "natural_input_field",
            "dispatch_workflow",
        ):
            if not str(getattr(self, field_name) or "").strip():
                raise ValueError(f"{field_name} is required")

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> DomainPluginDescriptor:
        return cls(
            schema_version=int(value.get("schema_version") or 0),
            domain_id=str(value.get("domain_id") or value.get("domain") or "").strip(),
            owner=str(value.get("owner") or "").strip(),
            profile=str(value.get("profile") or "").strip(),
            tool_name=str(value.get("tool_name") or "").strip(),
            aliases=tuple(str(item).strip() for item in value.get("aliases") or () if str(item).strip()),
            service_ref=str(value.get("service_ref") or "").strip(),
            natural_input_field=str(value.get("natural_input_field") or "target").strip(),
            dispatch_workflow=str(value.get("dispatch_workflow") or "ai_dispatch").strip(),
            read_operations=tuple(str(item).strip() for item in value.get("read_operations") or () if str(item).strip()),
            write_operations=tuple(str(item).strip() for item in value.get("write_operations") or () if str(item).strip()),
            direct_dispatch=bool(value.get("direct_dispatch", False)),
            supports_continuation=bool(value.get("supports_continuation", True)),
            discussion_guard=bool(value.get("discussion_guard", True)),
        )

    def dispatch_arguments(self, text: str) -> dict[str, Any]:
        if self.natural_input_field == "target":
            return {
                "workflow": self.dispatch_workflow,
                "target": str(text or "").strip(),
                "params": {},
            }
        return {self.natural_input_field: str(text or "").strip()}


@dataclass(frozen=True, slots=True)
class OperationProposal:
    domain: str
    operation: str
    target: dict[str, Any] = field(default_factory=dict)
    evidence: tuple[dict[str, Any], ...] = ()
    steps: tuple[dict[str, Any], ...] = ()
    risk: str = "read_only"
    confirmation_required: bool = False
    postconditions: tuple[dict[str, Any], ...] = ()
    proposal_id: str = ""

    def __post_init__(self) -> None:
        if not self.domain.strip() or not self.operation.strip():
            raise ValueError("domain and operation are required")
        if self.risk not in _RISK_LEVELS:
            raise ValueError(f"unsupported proposal risk: {self.risk}")
        if self.risk != "read_only" and not self.confirmation_required:
            raise ValueError("write proposals require confirmation")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    decision: str
    reason: str
    proposal_id: str = ""

    def __post_init__(self) -> None:
        if self.decision not in _DECISIONS:
            raise ValueError(f"unsupported policy decision: {self.decision}")
        if not self.reason.strip():
            raise ValueError("policy decision reason is required")


@dataclass(frozen=True, slots=True)
class ExecutionLease:
    proposal_id: str
    domain: str
    operation: str
    target_scope: dict[str, Any]
    expires_at: int

    def __post_init__(self) -> None:
        if not self.proposal_id.strip() or not self.domain.strip() or not self.operation.strip():
            raise ValueError("lease identity is incomplete")
        if self.expires_at <= 0:
            raise ValueError("lease expiry is required")


@dataclass(frozen=True, slots=True)
class StepEvent:
    proposal_id: str
    step: str
    status: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PostconditionResult:
    proposal_id: str
    name: str
    passed: bool
    evidence: dict[str, Any] = field(default_factory=dict)


class DomainPluginRegistry:
    def __init__(self, descriptors: Iterable[DomainPluginDescriptor] = ()) -> None:
        self._by_profile: dict[str, DomainPluginDescriptor] = {}
        self._by_tool: dict[str, DomainPluginDescriptor] = {}
        for descriptor in descriptors:
            self.register(descriptor)

    def register(self, descriptor: DomainPluginDescriptor) -> None:
        profile = descriptor.profile.casefold()
        tool_name = descriptor.tool_name.casefold()
        if profile in self._by_profile:
            raise ValueError(f"domain profile already registered: {descriptor.profile}")
        if tool_name in self._by_tool:
            raise ValueError(f"domain tool already registered: {descriptor.tool_name}")
        self._by_profile[profile] = descriptor
        self._by_tool[tool_name] = descriptor

    def for_profile(self, profile: str) -> DomainPluginDescriptor | None:
        return self._by_profile.get(str(profile or "").casefold())

    def for_tool(self, tool_name: str) -> DomainPluginDescriptor | None:
        return self._by_tool.get(str(tool_name or "").casefold())

    def profiles(self) -> frozenset[str]:
        return frozenset(self._by_profile)

    def replace(self, descriptors: Iterable[DomainPluginDescriptor]) -> None:
        replacement = DomainPluginRegistry(descriptors)
        self._by_profile = replacement._by_profile
        self._by_tool = replacement._by_tool

    def discover(self, stars: Iterable[Any]) -> list[str]:
        descriptors: list[DomainPluginDescriptor] = []
        errors: list[str] = []
        for metadata in stars:
            if not bool(getattr(metadata, "activated", False)):
                continue
            plugin = getattr(metadata, "star_cls", None)
            provider = getattr(plugin, "domain_harness_descriptors", None)
            if not callable(provider):
                continue
            owner = str(getattr(metadata, "name", "") or type(plugin).__name__)
            try:
                values = provider()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{owner}:provider:{exc}")
                continue
            for value in values or ():
                try:
                    if not isinstance(value, dict):
                        raise ValueError("descriptor must be an object")
                    descriptors.append(DomainPluginDescriptor.from_mapping(value))
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{owner}:descriptor:{exc}")
        if errors:
            self.replace(())
            return errors
        try:
            self.replace(descriptors)
        except Exception as exc:  # noqa: BLE001
            self.replace(())
            errors.append(f"registry:{exc}")
        return errors


DOMAIN_PLUGINS = DomainPluginRegistry()
