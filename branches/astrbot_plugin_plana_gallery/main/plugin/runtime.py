from __future__ import annotations

import asyncio
import secrets
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.star import Context, Star, StarTools
from quart import jsonify, make_response, request

from ..assets import GalleryStore
from ..commands import GalleryCommandMixin, SilentChatCollectionMixin
from ..web import gallery_html
from .chat_api import ChatAssetApiMixin
from .chat_service import GalleryChatService
from .chat_server import GalleryLoopbackServer
from .config import emotions as _emotions
from .config import normalize_config as _normalize_config
from .config import safe_int as _safe_int
from .config import tags as _tags
from .ingest import AssetIngestApiMixin
from .management_api import ManagementApiMixin
from .settings import load_overrides, public_settings, save_overrides
from .tagging import TaggingApiMixin


class PlanaGalleryPlugin(
    AssetIngestApiMixin,
    ChatAssetApiMixin,
    TaggingApiMixin,
    ManagementApiMixin,
    SilentChatCollectionMixin,
    GalleryCommandMixin,
    Star,
):
    """Independent image asset and tagging center for Plana."""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.base_config = _normalize_config(config)
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_plana_gallery")
        self.config = {**self.base_config, **load_overrides(self.data_dir)}
        self.store = GalleryStore(
            self.data_dir,
            max_import_bytes=int(
                self.config.get("max_import_bytes", 52_428_800) or 52_428_800
            ),
        )
        self.chat_service = GalleryChatService(self.store)
        self.chat_server = GalleryLoopbackServer(
            self.chat_service,
            enabled=bool(self.config.get("core_service_http_enabled", False)),
            port=int(self.config.get("core_service_port", 6193) or 6193),
            core_service_key=str(self.config.get("core_service_key", "") or ""),
        )
        self.pending_uploads: dict[str, dict[str, Any]] = {}
        self._silent_collection_lock = asyncio.Lock()
        self._job_task: asyncio.Task | None = None
        self._apply_config()

    async def initialize(self) -> None:
        if not self.enabled:
            logger.info("Plana Gallery disabled")
            return
        self.store.initialize()
        self._register_web_apis()
        self._job_task = asyncio.create_task(self._job_worker())
        if await self.chat_server.start():
            logger.info(
                "Plana Gallery loopback service started: http://127.0.0.1:%s",
                self.chat_server.port,
            )
        logger.info("Plana Gallery initialized")

    async def terminate(self) -> None:
        if self._job_task is not None:
            self._job_task.cancel()
            await asyncio.gather(self._job_task, return_exceptions=True)
            self._job_task = None
        await self.chat_server.stop()
        logger.info("Plana Gallery terminated")

    def _register_web_apis(self) -> None:
        self.context.register_web_api(
            "/plana_gallery/dashboard",
            self._serve_dashboard,
            ["GET"],
            "Plana Gallery dashboard",
        )
        self.context.register_web_api(
            "/plana_gallery/api/status",
            self._api_status,
            ["GET"],
            "Plana Gallery status",
        )
        self.context.register_web_api(
            "/plana_gallery/api/assets",
            self._api_assets,
            ["GET"],
            "List gallery assets",
        )
        self.context.register_web_api(
            "/plana_gallery/api/assets/get",
            self._api_asset_get,
            ["GET"],
            "Get gallery asset",
        )
        self.context.register_web_api(
            "/plana_gallery/api/assets/random",
            self._api_asset_random,
            ["GET"],
            "Pick one gallery asset for Core by query or tag",
        )
        self.context.register_web_api(
            "/plana_gallery/api/assets/semantic-candidates",
            self._api_asset_semantic_candidates,
            ["GET"],
            "Read-only semantic asset candidates for review",
        )
        self.context.register_web_api(
            "/plana_gallery/api/assets/candidate-feedback",
            self._api_asset_candidate_feedback,
            ["POST"],
            "Record explicit semantic candidate feedback",
        )
        self.context.register_web_api(
            "/plana_gallery/api/chat/candidates",
            self._api_chat_candidates,
            ["POST"],
            "Versioned local chat image candidates",
        )
        self.context.register_web_api(
            "/plana_gallery/api/chat/feedback",
            self._api_chat_feedback,
            ["POST"],
            "Record chat image selection and delivery events",
        )
        self.context.register_web_api(
            "/plana_gallery/api/chat/resolve",
            self._api_chat_resolve,
            ["GET"],
            "Resolve a reviewed local asset for delivery",
        )
        self.context.register_web_api(
            "/plana_gallery/api/assets/import",
            self._api_asset_import,
            ["POST"],
            "Import tagged image asset",
        )
        self.context.register_web_api(
            "/plana_gallery/api/assets/upload",
            self._api_asset_upload,
            ["POST"],
            "Upload tagged image asset",
        )
        self.context.register_web_api(
            "/plana_gallery/api/assets/import-urls",
            self._api_asset_import_urls,
            ["POST"],
            "Import images from external public URLs",
        )
        self.context.register_web_api(
            "/plana_gallery/api/assets/update",
            self._api_asset_update,
            ["POST"],
            "Update image tags and caption",
        )
        self.context.register_web_api(
            "/plana_gallery/api/assets/delete",
            self._api_asset_delete,
            ["POST"],
            "Delete image asset",
        )
        self.context.register_web_api(
            "/plana_gallery/api/assets/batch-delete",
            self._api_assets_batch_delete,
            ["POST"],
            "Batch delete image assets",
        )
        self.context.register_web_api(
            "/plana_gallery/api/tagging/candidates",
            self._api_tagging_candidates,
            ["GET"],
            "List assets for batch tagging",
        )
        self.context.register_web_api(
            "/plana_gallery/api/tagging/batch",
            self._api_tagging_batch,
            ["POST"],
            "Batch update tags",
        )
        self.context.register_web_api(
            "/plana_gallery/api/tagging/analyze",
            self._api_tagging_analyze,
            ["POST"],
            "Analyze tag candidates",
        )
        self.context.register_web_api(
            "/plana_gallery/api/assets/file/<asset_id>",
            self._api_asset_file,
            ["GET"],
            "Serve gallery image file",
        )
        self.context.register_web_api(
            "/plana_gallery/api/assets/thumbnail/<asset_id>",
            self._api_asset_thumbnail,
            ["GET"],
            "Serve generated gallery thumbnail",
        )
        self.context.register_web_api(
            "/plana_gallery/api/assets/thumbnail/<asset_id>/rebuild",
            self._api_asset_thumbnail_rebuild,
            ["POST"],
            "Rebuild a gallery thumbnail",
        )
        self.context.register_web_api(
            "/plana_gallery/api/diagnostics/query",
            self._api_diagnostics_query,
            ["POST"],
            "Inspect local gallery candidate scoring",
        )
        self.context.register_web_api(
            "/plana_gallery/api/diagnostics/feedback",
            self._api_diagnostics_feedback,
            ["POST"],
            "Record gallery diagnostics feedback",
        )
        self.context.register_web_api(
            "/plana_gallery/api/tags/definition",
            self._api_tag_definition,
            ["POST"],
            "Create or update a canonical gallery tag",
        )
        self.context.register_web_api(
            "/plana_gallery/api/review/commit",
            self._api_review_commit,
            ["POST"],
            "Atomically commit review tags and approval",
        )
        self.context.register_web_api(
            "/plana_gallery/api/jobs",
            self._api_jobs,
            ["GET"],
            "Inspect gallery background jobs",
        )
        self.context.register_web_api(
            "/plana_gallery/api/tags",
            self._api_tag_taxonomy,
            ["GET", "POST"],
            "Read or update controlled Gallery tags",
        )
        self.context.register_web_api(
            "/plana_gallery/api/settings",
            self._api_settings,
            ["GET", "POST"],
            "Read or update Gallery runtime settings",
        )

    async def _serve_dashboard(self):
        resp = await make_response(gallery_html("/api/plug/plana_gallery"))
        resp.headers["Content-Type"] = "text/html; charset=utf-8"
        return resp

    async def _api_status(self):
        if not self._authorized(readonly=True):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = self.store.status()
        payload.update(self.store.tag_taxonomy())
        payload["storage_mode"] = "local_only"
        payload["silent_collection"] = {
            "enabled": self.enable_silent_chat_image_collection,
            "scope_mode": "allowlist" if self.silent_collection_scope_allowlist else "all_groups",
            "scope_count": len(self.silent_collection_scope_allowlist),
            "last_24h": self.store.chat_collection_status(),
        }
        return jsonify(payload)

    async def _api_assets(self):
        if not self._authorized(readonly=True):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        query = str(request.args.get("q", "") or "")
        tag = str(request.args.get("tag", "") or "")
        raw_tags = str(request.args.get("tags", "") or "")
        raw_excludes = str(request.args.get("exclude_tags", "") or "")
        page_arg = request.args.get("page")
        if page_arg is not None:
            page = self.store.browse_assets(
                query=query,
                tags=_tags(raw_tags) or ([tag] if tag else []),
                exclude_tags=_tags(raw_excludes),
                tag_mode=str(request.args.get("tag_mode", "all") or "all"),
                review=str(request.args.get("review", "all") or "all"),
                source=str(request.args.get("source", "") or ""),
                page=_safe_int(page_arg, 1, 1, 1_000_000),
                page_size=_safe_int(request.args.get("page_size"), 48, 12, 120),
                sort=str(request.args.get("sort", "updated_desc") or "updated_desc"),
            )
            return jsonify({"ok": True, **page})
        cursor = str(request.args.get("cursor", "") or "")
        limit = _safe_int(request.args.get("limit"), 50, 1, 200)
        page = self.store.list_assets_page(
            query=query, tag=tag, cursor=cursor, limit=limit
        )
        return jsonify({"ok": True, **page})

    async def _api_asset_get(self):
        if not self._authorized(readonly=True):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        asset_id = _safe_int(request.args.get("id"), 0, 0, 2_147_483_647)
        asset = self.store.get_asset(asset_id)
        if not asset:
            return jsonify({"ok": False, "error": "not_found"}), 404
        return jsonify({"ok": True, "asset": asset})

    async def _api_asset_random(self):
        if not self._authorized(readonly=True):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        query = str(request.args.get("q", "") or "")
        tag = str(request.args.get("tag", "") or "")
        include_review = str(request.args.get("include_review", "") or "").lower() in {
            "1",
            "true",
            "yes",
        }
        asset = self.store.random_asset(
            query=query,
            tag=tag,
            include_review=include_review,
        )
        if not asset:
            return jsonify({"ok": False, "error": "not_found"}), 404
        return jsonify({"ok": True, "asset": asset})

    async def _api_asset_update(self):
        if not self._authorized(readonly=False):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        asset_id = _safe_int(payload.get("id"), 0, 0, 2_147_483_647)
        result = self.store.update_asset(
            asset_id,
            title=str(payload.get("title", "")),
            caption=str(payload.get("caption", "")),
            tags=_tags(payload.get("tags", [])),
            emotions=_emotions(payload.get("emotions")) if "emotions" in payload else None,
            expected_updated_at=_safe_int(
                payload.get("expected_updated_at"), 0, 0, 9_223_372_036_854_775_807
            ),
        )
        status = 200 if result.get("ok") else (409 if result.get("error") == "version_conflict" else 404)
        return jsonify(result), status

    async def _api_asset_delete(self):
        if not self._authorized(readonly=False):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        asset_id = _safe_int(payload.get("id"), 0, 0, 2_147_483_647)
        result = self.store.delete_asset(asset_id)
        return jsonify(result), 200 if result.get("ok") else 404

    async def _api_assets_batch_delete(self):
        if not self._authorized(readonly=False):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        raw_ids = payload.get("ids", [])
        if not isinstance(raw_ids, list) or not raw_ids:
            return jsonify({"ok": False, "error": "missing_ids"}), 400
        ids = [_safe_int(item, 0, 1, 2_147_483_647) for item in raw_ids]
        result = self.store.delete_assets([item for item in ids if item])
        return jsonify(result)

    async def _api_asset_file(self, asset_id: str):
        asset_file = self.store.file_for_asset(_safe_int(asset_id, 0, 0, 2_147_483_647))
        if asset_file is None:
            return jsonify({"ok": False, "error": "not_found"}), 404
        path, mime_type = asset_file
        resp = await make_response(path.read_bytes())
        resp.headers["Content-Type"] = mime_type
        resp.headers["Cache-Control"] = "private, max-age=3600"
        return resp

    async def _api_settings(self):
        if request.method == "GET":
            if not self._authorized(readonly=True):
                return jsonify({"ok": False, "error": "unauthorized"}), 401
            return jsonify(public_settings(self.config))
        if not self._authorized(readonly=False):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        overrides = save_overrides(self.data_dir, self.config, payload)
        self.config = {**self.base_config, **overrides}
        self._apply_config()
        return jsonify(public_settings(self.config))

    async def _maybe_auto_upload(self, import_result: dict[str, Any]) -> None:
        _ = import_result

    async def _job_worker(self) -> None:
        try:
            while True:
                result = await asyncio.to_thread(self.store.process_next_job)
                await asyncio.sleep(0.05 if result else 1.0)
        except asyncio.CancelledError:
            return

    def _authorized(self, *, readonly: bool) -> bool:
        if readonly and not self.api_token:
            return True
        if not self.api_token:
            return not readonly
        token = request.headers.get("X-Plana-Gallery-Token", "").strip()
        if not token:
            token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        return secrets.compare_digest(token, self.api_token)

    def _chat_authorized(self, *, readonly: bool) -> bool:
        remote = str(request.remote_addr or "").strip().lower()
        if remote in {"127.0.0.1", "::1", "localhost"}:
            return True
        return self._authorized(readonly=readonly)

    def _apply_config(self) -> None:
        self.enabled = bool(self.config.get("enabled", True))
        self.enable_commands = bool(self.config.get("enable_commands", True))
        self.allow_chat_image_import = bool(
            self.config.get("allow_chat_image_import", True)
        )
        self.api_token = str(self.config.get("api_token", "") or "")
        self.allow_original_path = bool(self.config.get("allow_original_path", True))
        self.upload_wait_seconds = int(self.config.get("upload_wait_seconds", 60) or 60)
        self.chat_download_timeout_seconds = int(
            self.config.get("chat_download_timeout_seconds", 20) or 20
        )
        self.enable_silent_chat_image_collection = bool(
            self.config.get("enable_silent_chat_image_collection", False)
        )
        self.silent_collection_scope_allowlist = {
            item.strip()
            for item in str(self.config.get("silent_collection_scope_allowlist", "") or "").split(",")
            if item.strip()
        }
        self.silent_collection_daily_limit_per_scope = _safe_int(
            self.config.get("silent_collection_daily_limit_per_scope"), 20, 1, 10000
        )
        self.silent_collection_global_daily_limit = _safe_int(
            self.config.get("silent_collection_global_daily_limit"), 100, 1, 100000
        )
        self.silent_collection_max_images_per_message = _safe_int(
            self.config.get("silent_collection_max_images_per_message"), 3, 1, 20
        )
        self.silent_collection_max_bytes = _safe_int(
            self.config.get("silent_collection_max_bytes"), 8_388_608, 1024, 52_428_800
        )
        self.silent_collection_max_pixels = _safe_int(
            self.config.get("silent_collection_max_pixels"), 16_000_000, 1, 100_000_000
        )
        self.silent_collection_max_gif_frames = _safe_int(
            self.config.get("silent_collection_max_gif_frames"), 200, 1, 5000
        )
        self.store.max_import_bytes = int(
            self.config.get("max_import_bytes", 52_428_800) or 52_428_800
        )
