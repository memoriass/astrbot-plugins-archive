from __future__ import annotations

from typing import Any

from .constants import RESTRICTED_TAG, REVIEW_TAG, SAFE_TAG


def tag_candidate(asset: dict[str, Any], known_tags: set[str]) -> dict[str, Any]:
    tags = [str(tag) for tag in asset.get("tags", [])]
    suggested: list[str] = []
    reason = "existing_tags"
    pending = not tags or tags == [REVIEW_TAG]
    confidence = 35 if pending else 95
    text = " ".join(
        str(asset.get(field, ""))
        for field in ("title", "caption", "original_path", "source")
    ).lower()
    normalized_path = text.replace("\\", "/")
    for tag in sorted(known_tags):
        if tag in tags:
            continue
        if f"/{tag}/" in normalized_path:
            suggested.append(tag)
            confidence = max(confidence, 86)
            reason = "path_category"
        elif tag and tag in text:
            suggested.append(tag)
            confidence = max(confidence, 68)
            reason = "text_match"
    if not suggested and pending:
        suggested = [REVIEW_TAG]
        reason = "untagged"
    if pending:
        reason = "pending_review"
    candidate = dict(asset)
    candidate["suggested_tags"] = suggested[:8]
    candidate["confidence"] = confidence
    candidate["reason"] = reason
    candidate["semantic_candidate"] = semantic_candidate(candidate)
    return candidate


def semantic_candidate(asset: dict[str, Any]) -> dict[str, Any]:
    tags = [str(tag) for tag in asset.get("tags", [])]
    review_status = "needs-review" if REVIEW_TAG in set(tags) else "reviewed"
    matched_tags = [
        str(tag)
        for tag in asset.get("suggested_tags", [])
        if str(tag).strip() and str(tag) != REVIEW_TAG
    ]
    production_eligible = (
        review_status != "needs-review"
        and SAFE_TAG in set(tags)
        and RESTRICTED_TAG not in set(tags)
    )
    return {
        "asset_ref": str(asset.get("asset_ref") or ""),
        "score": int(asset.get("confidence") or 0),
        "matched_tags": matched_tags,
        "review_status": review_status,
        "candidate_only": True,
        "production_eligible": production_eligible,
        "explanation": str(asset.get("reason") or "tag_only"),
    }
