from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
_CREDENTIAL_SPEC = importlib.util.spec_from_file_location(
    "plana_bridge_credential_import",
    ROOT / "bridge" / "credential.py",
)
if _CREDENTIAL_SPEC is None or _CREDENTIAL_SPEC.loader is None:
    raise RuntimeError("credential_provider_load_failed")
_CREDENTIAL_MODULE = importlib.util.module_from_spec(_CREDENTIAL_SPEC)
_CREDENTIAL_SPEC.loader.exec_module(_CREDENTIAL_MODULE)
CredentialError = _CREDENTIAL_MODULE.CredentialError
ProtectedFileCredentialProvider = _CREDENTIAL_MODULE.ProtectedFileCredentialProvider


DEFAULT_CREDENTIAL_REF = "ani_rss.production.api_key"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import an ANI-RSS api_key into the Bridge credential store.",
    )
    parser.add_argument("source_config", type=Path, help="Path to the legacy ANI-RSS JSON config")
    parser.add_argument("credential_store", type=Path, help="Bridge credential store directory")
    parser.add_argument(
        "--credential-ref",
        default=DEFAULT_CREDENTIAL_REF,
        help=f"Credential reference (default: {DEFAULT_CREDENTIAL_REF})",
    )
    args = parser.parse_args(argv)
    source = args.source_config.resolve()
    try:
        data = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        parser.error(f"unable to read source config: {type(exc).__name__}")
    api_key = data.get("api_key") if isinstance(data, dict) else None
    if not isinstance(api_key, str) or not api_key:
        parser.error("source config does not contain a non-empty api_key")
    try:
        provider = ProtectedFileCredentialProvider(args.credential_store)
        provider.put(args.credential_ref, {"api_key": api_key})
    except CredentialError as exc:
        parser.error(str(exc))
    print(
        f"imported=true ref={args.credential_ref} "
        f"source={source} source_preserved={source.is_file()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
