from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    catalog = _load_catalog()
    assert catalog.ADAPTER_CATALOG
    assert catalog.CAPABILITY_CATALOG
    for capability, metadata in catalog.CAPABILITY_CATALOG.items():
        assert str(metadata.get("copy_key") or "").startswith("gateway.capability.")
        assert metadata.get("result_type"), capability
    production = "\n".join(
        path.read_text(encoding="utf-8-sig")
        for folder in ("plugin", "dialogue", "execution")
        for path in sorted((ROOT / folder).rglob("*.py"))
    )
    assert "CAPABILITY_CATALOG" not in production
    assert "CapabilityRegistry" not in production
    print("integration_catalog_check=ok:metadata_only")


def _load_catalog():
    path = ROOT / "web" / "integration_catalog.py"
    spec = importlib.util.spec_from_file_location("plana_integration_catalog_check", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    main()
