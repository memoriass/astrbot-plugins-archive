from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import inspect
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import aiohttp

from .sibling_services import find_sibling_service

CHAT_CONTRACT_VERSION = "plana.gallery.candidates.v1"
FEEDBACK_CONTRACT_VERSION = "plana.gallery.feedback.v1"
DEFAULT_GALLERY_URL = "http://127.0.0.1:6193/plana_gallery"
GALLERY_PLUGIN_NAME = "astrbot_plugin_plana_gallery"


@dataclass(frozen=True, slots=True)
class GalleryEmotionTarget:
    emotion_tag: str
    target_intensity: int = 2
    prominence: str = "secondary"
    weight: float = 1.0
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class GalleryCandidateEmotion:
    emotion_tag: str
    intensity: int = 2
    prominence: str = "secondary"


@dataclass(frozen=True, slots=True)
class GalleryCandidate:
    asset_ref: str
    title: str = ""
    caption: str = ""
    tags: tuple[str, ...] = ()
    matched_facets: tuple[str, ...] = ()
    emotions: tuple[GalleryCandidateEmotion, ...] = ()
    matched_emotions: tuple[str, ...] = ()
    score: float = 0.0
    score_breakdown: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GalleryResolvedAsset:
    ok: bool
    asset_ref: str = ""
    file_path: str = ""
    mime_type: str = ""
    error: str = ""


class PlanaGalleryClient:
    def __init__(
        self,
        config: dict[str, Any],
        *,
        runtime: Any | None = None,
        allowed_roots: list[Path] | None = None,
    ) -> None:
        self.runtime = runtime
        self.enabled = bool(config.get("enable_gallery_chat_images", False))
        self.base_url = str(
            config.get("gallery_service_url", DEFAULT_GALLERY_URL)
            or DEFAULT_GALLERY_URL
        ).strip().rstrip("/")
        self.timeout_seconds = max(
            1, min(int(config.get("gallery_timeout_seconds", 2) or 2), 10)
        )
        self.candidate_limit = max(
            1, min(int(config.get("gallery_candidate_limit", 6) or 6), 12)
        )
        self.service_key = str(config.get("plana_core_service_key", "") or "").strip()
        self.allowed_roots = [
            root.resolve() for root in (allowed_roots or []) if str(root).strip()
        ]
        self.last_error = ""
        self.last_transport = ""

    @property
    def configured(self) -> bool:
        return bool(self.enabled and (self._local_service() is not None or self._http_supported()))

    async def candidates(
        self,
        *,
        request_id: str,
        query: str,
        facets: list[str],
        exclude_asset_refs: list[str],
        emotions: list[GalleryEmotionTarget] | tuple[GalleryEmotionTarget, ...] = (),
    ) -> list[GalleryCandidate]:
        self.last_error = ""
        if not self.configured:
            self.last_error = "gallery_not_configured"
            return []
        payload = {
            "contract_version": CHAT_CONTRACT_VERSION,
            "request_id": request_id[:160],
            "query": query[:500],
            "facets": facets[:12],
            "emotions": [
                {
                    "emotion_tag": item.emotion_tag[:80],
                    "target_intensity": max(1, min(int(item.target_intensity), 3)),
                    "prominence": (
                        "primary" if item.prominence == "primary" else "secondary"
                    ),
                    "weight": max(0.1, min(float(item.weight), 2.0)),
                }
                for item in list(emotions)[:4]
                if item.emotion_tag.startswith("emotion:")
            ],
            "exclude_asset_refs": exclude_asset_refs[:100],
            "limit": self.candidate_limit,
        }
        data = await self._service_or_http(
            "candidates",
            payload,
            http_method="POST",
            http_path="/api/chat/candidates",
            json=payload,
        )
        if data.get("ok") is False:
            if not self.last_error:
                self.last_error = str(data.get("error") or "gallery_request_failed")[:200]
            return []
        if data.get("contract_version") != CHAT_CONTRACT_VERSION:
            self.last_error = "contract_version_mismatch"
            return []
        result = []
        for raw in data.get("candidates", []):
            if not isinstance(raw, dict):
                continue
            asset_ref = str(raw.get("asset_ref") or "").strip()
            if not asset_ref.startswith("gallery:"):
                continue
            score_breakdown = raw.get("score_breakdown")
            raw_emotions = raw.get("emotions")
            parsed_emotions = []
            if isinstance(raw_emotions, list):
                for item in raw_emotions[:12]:
                    if not isinstance(item, dict):
                        continue
                    emotion_tag = str(item.get("emotion_tag") or "").strip()[:80]
                    if not emotion_tag.startswith("emotion:"):
                        continue
                    parsed_emotions.append(
                        GalleryCandidateEmotion(
                            emotion_tag=emotion_tag,
                            intensity=max(1, min(int(_float(item.get("intensity")) or 2), 3)),
                            prominence=(
                                "primary"
                                if str(item.get("prominence")) == "primary"
                                else "secondary"
                            ),
                        )
                    )
            result.append(
                GalleryCandidate(
                    asset_ref=asset_ref,
                    title=str(raw.get("title") or "")[:160],
                    caption=str(raw.get("caption") or "")[:500],
                    tags=tuple(str(tag)[:80] for tag in raw.get("tags", [])[:40]),
                    matched_facets=tuple(
                        str(tag)[:80] for tag in raw.get("matched_facets", [])[:12]
                    ),
                    emotions=tuple(parsed_emotions),
                    matched_emotions=tuple(
                        str(tag)[:80]
                        for tag in raw.get("matched_emotions", [])[:4]
                        if str(tag).startswith("emotion:")
                    ),
                    score=_float(raw.get("score")),
                    score_breakdown=(
                        {str(key): _float(value) for key, value in score_breakdown.items()}
                        if isinstance(score_breakdown, dict)
                        else {}
                    ),
                )
            )
        return result

    async def resolve(self, asset_ref: str) -> GalleryResolvedAsset:
        self.last_error = ""
        if not self.configured:
            return self._resolve_fail("gallery_not_configured")
        data = await self._service_or_http(
            "resolve",
            asset_ref[:120],
            http_method="GET",
            http_path="/api/chat/resolve",
            params={"asset_ref": asset_ref[:120]},
        )
        if data.get("ok") is False:
            return self._resolve_fail(str(data.get("error") or "resolve_failed"))
        if data.get("contract_version") != CHAT_CONTRACT_VERSION:
            return self._resolve_fail("contract_version_mismatch")
        if not data.get("ok"):
            return self._resolve_fail(str(data.get("error") or "resolve_failed"))
        path = Path(str(data.get("file_path") or "")).resolve()
        if not path.is_file():
            return self._resolve_fail("asset_path_not_found")
        if self.allowed_roots and not any(path == root or root in path.parents for root in self.allowed_roots):
            return self._resolve_fail("asset_path_outside_gallery")
        return GalleryResolvedAsset(
            ok=True,
            asset_ref=str(data.get("asset_ref") or ""),
            file_path=str(path),
            mime_type=str(data.get("mime_type") or "application/octet-stream"),
        )

    async def feedback(
        self,
        *,
        request_id: str,
        asset_ref: str,
        event: str,
        reason: str = "",
        query: str = "",
    ) -> bool:
        if not self.configured:
            return False
        payload = {
            "contract_version": FEEDBACK_CONTRACT_VERSION,
            "event_id": f"{request_id}:{event}:{asset_ref}"[:200],
            "request_id": request_id[:160],
            "asset_ref": asset_ref[:120],
            "event": event[:40],
            "reason": reason[:500],
            "query": query[:500],
        }
        data = await self._service_or_http(
            "feedback",
            payload,
            http_method="POST",
            http_path="/api/chat/feedback",
            json=payload,
        )
        return bool(data.get("ok"))

    def status(self) -> dict[str, object]:
        local_available = self._local_service() is not None
        return {
            "enabled": self.enabled,
            "configured": self.configured,
            "contract_version": CHAT_CONTRACT_VERSION,
            "local_loopback_only": True,
            "in_process_available": local_available,
            "preferred_transport": "in_process" if local_available else "loopback_http",
            "last_transport": self.last_transport,
            "last_error": self.last_error,
        }

    async def _service_or_http(
        self,
        service_method: str,
        service_arg: Any,
        *,
        http_method: str,
        http_path: str,
        **http_kwargs: Any,
    ) -> dict[str, Any]:
        service = self._local_service()
        method = getattr(service, service_method, None) if service is not None else None
        if callable(method):
            try:
                result = await asyncio.to_thread(method, service_arg)
                if inspect.isawaitable(result):
                    result = await result
            except Exception as exc:  # noqa: BLE001
                self.last_transport = "in_process"
                self.last_error = f"inprocess:{exc}"[:200]
                return {}
            self.last_transport = "in_process"
            if not isinstance(result, dict):
                self.last_error = "invalid_inprocess_response"
                return {}
            if not result.get("ok", False):
                self.last_error = str(result.get("error") or "inprocess_not_ok")[:200]
            return result
        if not self._http_supported():
            self.last_error = "gallery_service_unavailable"
            return {}
        self.last_transport = "loopback_http"
        return await self._json_request(http_method, http_path, **http_kwargs)

    async def _json_request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = dict(kwargs.pop("headers", {}) or {})
        if self.service_key:
            headers["X-Plana-Core-Key"] = self.service_key
        if headers:
            kwargs["headers"] = headers
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(method, f"{self.base_url}{path}", **kwargs) as response:
                    data = await response.json(content_type=None)
                    if not isinstance(data, dict):
                        self.last_error = "invalid_response"
                        return {}
                    if response.status >= 400:
                        self.last_error = str(data.get("error") or f"http_{response.status}")
                        return data
                    return data
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)[:200]
            return {}

    def _resolve_fail(self, error: str) -> GalleryResolvedAsset:
        self.last_error = error
        return GalleryResolvedAsset(ok=False, error=error)

    def _remote_unsupported(self) -> bool:
        host = (urlsplit(self.base_url).hostname or "").strip().lower()
        return bool(host and host not in {"127.0.0.1", "localhost", "::1"})

    def _http_supported(self) -> bool:
        if not self.base_url or not self.service_key or self._remote_unsupported():
            return False
        return "/api/plug/" not in urlsplit(self.base_url).path

    def _local_service(self) -> Any | None:
        if self.runtime is None:
            return None
        return find_sibling_service(
            self.runtime,
            plugin_name=GALLERY_PLUGIN_NAME,
            service_attr="chat_service",
            required_methods=("candidates", "resolve", "feedback", "status"),
        )


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
