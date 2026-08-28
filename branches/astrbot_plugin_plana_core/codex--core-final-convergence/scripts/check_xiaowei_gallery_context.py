from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = (
    ROOT / "scripts" / "fixtures" / "xiaowei_gallery_context.json",
    ROOT / "scripts" / "fixtures" / "xiaowei_gallery_context_balanced.json",
)
RAW_CANDIDATE_FIXTURES = (
    ROOT / "scripts" / "fixtures" / "xiaowei_gallery_raw_allowed_candidates.json",
    ROOT / "scripts" / "fixtures" / "xiaowei_gallery_raw_blocked_candidates.json",
)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "presentation"))


def load_policy_module():
    path = ROOT / "presentation" / "gallery_context.py"
    spec = importlib.util.spec_from_file_location("plana_xiaowei_gallery_check", path)
    if spec is None or spec.loader is None:
        raise SystemExit("gallery_context_spec_missing")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeMessage:
    def __init__(self, message_id: str) -> None:
        self.message_id = message_id


class FakeEvent:
    unified_msg_origin = "group:xiaowei-comparison"

    def __init__(self, case_id: str) -> None:
        self.message_obj = FakeMessage(case_id)

    def get_sender_id(self) -> str:
        return "xiaowei-sample-actor"

    def is_private_chat(self) -> bool:
        return False


def evaluate() -> dict[str, Any]:
    fixtures = [json.loads(path.read_text(encoding="utf-8")) for path in FIXTURES]
    cases = [case for fixture in fixtures for case in fixture["cases"]]
    module = load_policy_module()
    rows: list[dict[str, Any]] = []
    for case in cases:
        policy = module.GalleryContextPolicy({"gallery_group_cooldown_seconds": 0, "gallery_private_cooldown_seconds": 0})
        intent = policy.intent(FakeEvent(case["case_id"]), case["user_text"], case["response_text"])
        actual_gallery = intent is not None
        actual_facets = set(intent.facets if intent else ())
        expected_facets = set(case.get("expected_facets") or ())
        rows.append({
            "case_id": case["case_id"],
            "timestamp": case["timestamp"],
            "media_kind": case["media_kind"],
            "xiaowei_had_image": bool(case["xiaowei_had_image"]),
            "expected_gallery": bool(case["expected_gallery"]),
            "actual_gallery": actual_gallery,
            "missing_facets": sorted(expected_facets - actual_facets),
            "actual_facets": sorted(actual_facets),
            "source_group": str(case.get("source_group") or "906678215"),
            "relative_delay_seconds": case.get("relative_delay_seconds"),
            "reply_anchor": bool(case.get("reply_anchor", False)),
            "image_hash": str(case.get("image_hash") or ""),
        })
    contextual = [row for row in rows if row["expected_gallery"]]
    blocked = [row for row in rows if not row["expected_gallery"]]
    mismatches = [row for row in rows if row["expected_gallery"] != row["actual_gallery"] or row["missing_facets"]]
    raw_candidates = _validate_raw_candidates()
    return {
        "source": [fixture["source"] for fixture in fixtures],
        "sample_count": len(rows),
        "xiaowei_image_count": sum(row["xiaowei_had_image"] for row in rows),
        "expected_gallery_count": sum(row["expected_gallery"] for row in rows),
        "actual_gallery_count": sum(row["actual_gallery"] for row in rows),
        "context_reaction_recall": _ratio(sum(row["actual_gallery"] for row in contextual), len(contextual)),
        "blocked_false_positive_rate": _ratio(sum(row["actual_gallery"] for row in blocked), len(blocked)),
        "direct_media_agreement": _ratio(sum(row["xiaowei_had_image"] == row["actual_gallery"] for row in rows), len(rows)),
        "deliberate_conservative_divergence": sum(row["xiaowei_had_image"] and not row["actual_gallery"] for row in rows),
        "mismatches": mismatches,
        "acceptance_failures": [
            reason
            for condition, reason in (
                (len(contextual) < 40, "allowed_cases_below_40"),
                (len(blocked) < 40, "blocked_cases_below_40"),
                (_ratio(sum(row["actual_gallery"] for row in contextual), len(contextual)) < 0.95, "reaction_recall_below_95_percent"),
                (_ratio(sum(row["actual_gallery"] for row in blocked), len(blocked)) > 0.02, "blocked_false_positive_above_2_percent"),
                (len({row["source_group"] for row in rows}) < 2, "source_group_coverage_missing"),
            )
            if condition
        ],
        "raw_candidates": raw_candidates,
        "rows": rows,
    }


def _validate_raw_candidates() -> dict[str, Any]:
    fixtures = [json.loads(path.read_text(encoding="utf-8")) for path in RAW_CANDIDATE_FIXTURES]
    cases = [case for fixture in fixtures for case in fixture.get("cases", [])]
    failures = []
    allowed = [case for case in cases if case.get("expected_gallery")]
    blocked = [case for case in cases if not case.get("expected_gallery")]
    if len(allowed) < 40:
        failures.append("raw_allowed_candidates_below_40")
    if len(blocked) < 40:
        failures.append("raw_blocked_candidates_below_40")
    if len({str(case.get("source_group") or "") for case in cases}) < 2:
        failures.append("raw_source_group_coverage_missing")
    if any(not str(case.get("image_hash") or "") for case in cases):
        failures.append("raw_image_hash_missing")
    if any("http://" in json.dumps(case, ensure_ascii=False).lower() or "https://" in json.dumps(case, ensure_ascii=False).lower() for case in cases):
        failures.append("raw_url_not_redacted")
    if any(fixture.get("review_status") != "pending_human_review" for fixture in fixtures):
        failures.append("raw_review_boundary_missing")
    return {
        "sample_count": len(cases),
        "allowed_count": len(allowed),
        "blocked_count": len(blocked),
        "source_group_count": len({str(case.get("source_group") or "") for case in cases}),
        "review_status": "pending_human_review",
        "acceptance_active": False,
        "validation_failures": failures,
    }


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Xiaowei Gallery Context Comparison — 2026-07-14",
        "",
        "## Scope",
        "",
        f"- Source sample: {result['source']}.",
        f"- Curated image-bearing windows: {result['sample_count']}.",
        "- The sample contains conversational reaction images and images produced by commands, generation, analysis, task progress, account recovery, or serious contexts.",
        "",
        "## Result",
        "",
        f"- Xiaowei image-bearing windows: {result['xiaowei_image_count']}/{result['sample_count']}.",
        f"- Plana local Gallery allowed: {result['actual_gallery_count']}/{result['sample_count']}.",
        f"- Context-reaction recall: {result['context_reaction_recall']:.2%}.",
        f"- Blocked-category false-positive rate: {result['blocked_false_positive_rate']:.2%}.",
        f"- Direct media agreement with Xiaowei: {result['direct_media_agreement']:.2%}.",
        f"- Deliberate conservative divergences: {result['deliberate_conservative_divergence']}.",
        "",
        "Direct agreement is not the target: Xiaowei frequently attaches generated images, command result cards, OCR or analysis artifacts, and task-progress images. Plana Gallery only adopts the contextual reaction subset.",
        "",
        "## Policy Notes",
        "",
        "- Adopted signals: praise, laughter, speechlessness, surprise, doubt emoji, playful refusal, apology and light celebration.",
        "- Rejected signals: API/code, OCR, download/report tasks, image generation/editing, restart/help commands, tokens, scoring, summaries, file operations, account risk, threats and appeals.",
        "- This is a deterministic static gate regression; it does not invoke a model, Gallery writes, production tools or image delivery.",
        "",
        "## Mismatches",
        "",
    ]
    if result["mismatches"]:
        lines.extend(f"- {row['case_id']}: expected={row['expected_gallery']} actual={row['actual_gallery']} missing_facets={row['missing_facets']}" for row in result["mismatches"])
    else:
        lines.append("- None.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = evaluate()
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "rows"}, ensure_ascii=False, indent=2))
    if (
        result["mismatches"]
        or result["acceptance_failures"]
        or result["raw_candidates"]["validation_failures"]
    ):
        return 1
    print("xiaowei_gallery_context_check=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
