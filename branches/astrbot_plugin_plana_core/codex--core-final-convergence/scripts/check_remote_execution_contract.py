from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_plana_core.dialogue.remote_task import CodexDelegationRequest
from astrbot_plugin_plana_core.execution.remote_contract import (
    DELEGATE_CONTRACT_VERSION,
    DELEGATE_TYPE,
    normalize_remote_execution_metadata,
    serialize_remote_execution_metadata,
)


def expect_value_error(action, expected: str) -> None:
    try:
        action()
    except ValueError as exc:
        assert expected in str(exc), (expected, str(exc))
    else:
        raise AssertionError(f"expected_value_error:{expected}")


def main() -> None:
    payload = CodexDelegationRequest(
        text="inspect repository", scope_id="scope-1", actor_id="actor-1",
        capability="code.inspect", reason="benchmark", expected_outputs=("report",),
    ).payload()
    assert payload["contract_version"] == DELEGATE_CONTRACT_VERSION
    assert payload["type"] == DELEGATE_TYPE
    assert payload["request_id"].startswith("codex-")
    assert payload["engine"] == "codex"
    assert payload["execution_profile"] == "codex_default"
    assert payload["execution_metadata_version"] == "plana.remote.execution.v1"
    codex = normalize_remote_execution_metadata(
        {"engine": "codex", "execution_profile": "coding_quality", "profile_revision": 7},
        allowed_engines=("codex",),
    )
    assert serialize_remote_execution_metadata(codex)["profile_revision"] == 7
    expect_value_error(
        lambda: normalize_remote_execution_metadata({"engine": "hermes"}),
        "remote_execution_engine_not_allowed:hermes",
    )
    for field in ("endpoint", "token", "provider", "base_url", "api_key"):
        expect_value_error(
            lambda field=field: normalize_remote_execution_metadata({field: "forbidden"}),
            f"remote_execution_control_field_forbidden:{field}",
        )
    expect_value_error(
        lambda: normalize_remote_execution_metadata({"execution_profile": "arbitrary-model"}),
        "remote_execution_profile_not_allowed",
    )
    expect_value_error(
        lambda: normalize_remote_execution_metadata({"model": "arbitrary-model"}),
        "remote_execution_metadata_field_unknown:model",
    )
    expect_value_error(
        lambda: normalize_remote_execution_metadata({"profile_revision": 0}),
        "remote_execution_profile_revision_invalid",
    )
    source = (ROOT / "execution" / "remote_contract.py").read_text(encoding="utf-8")
    assert "LEGACY_DELEGATE" not in source
    assert "normalize_remote_delegate_payload" not in source
    print("remote_execution_contract_check=ok")


if __name__ == "__main__":
    main()
