from __future__ import annotations

from collections.abc import Iterable
from io import BytesIO
import inspect
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from zipfile import BadZipFile, ZipFile

import aiohttp
from quart import jsonify, request

from ..assets.store import IMAGE_SUFFIXES

ARCHIVE_SUFFIXES = {".zip"}
MAX_BATCH_ITEMS = 500
MAX_ARCHIVE_FACTOR = 20


class AssetIngestApiMixin:
    async def _api_asset_import(self):
        if not self._authorized(readonly=False):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        path_text = str(payload.get("path", "") or "")
        title = str(payload.get("title", "") or "")
        tags = _tags(payload.get("tags", []))
        caption = str(payload.get("caption", "") or "")
        source = str(payload.get("source", "manual") or "manual")
        results = self._import_path_items(
            path_text,
            title=title,
            tags=tags,
            caption=caption,
            source=source,
        )
        response = _batch_response(results)
        await self._maybe_auto_upload_batch(response["results"])
        return jsonify(response), 200 if response["imported_count"] else 400

    async def _api_asset_upload(self):
        if not self._authorized(readonly=False):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        form = await request.form
        files = await request.files
        upload_files = _upload_files(files)
        if not upload_files:
            return jsonify({"ok": False, "error": "missing_file"}), 400
        tags = _tags(form.get("tags", ""))
        title = str(form.get("title", "") or "")
        caption = str(form.get("caption", "") or "")
        results: list[dict[str, Any]] = []
        for upload_file in upload_files[:MAX_BATCH_ITEMS]:
            results.extend(
                await self._import_upload_file(
                    upload_file,
                    title=title if len(upload_files) == 1 else "",
                    tags=tags,
                    caption=caption,
                )
            )
        response = _batch_response(results)
        await self._maybe_auto_upload_batch(response["results"])
        return jsonify(response), 200 if response["imported_count"] else 400

    async def _api_asset_import_urls(self):
        if not self._authorized(readonly=False):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        urls = _urls(payload.get("urls", []))
        if not urls:
            return jsonify({"ok": False, "error": "missing_urls"}), 400
        tags = _tags(payload.get("tags", []))
        caption = str(payload.get("caption", "") or "")
        timeout = int(getattr(self, "remote_timeout_seconds", 30) or 30)
        results = await self._import_external_urls(
            urls[:MAX_BATCH_ITEMS],
            tags=tags,
            caption=caption,
            timeout_seconds=timeout,
        )
        response = _batch_response(results)
        await self._maybe_auto_upload_batch(response["results"])
        return jsonify(response), 200 if response["imported_count"] else 400

    async def _import_upload_file(
        self,
        upload_file: Any,
        *,
        title: str,
        tags: list[str],
        caption: str,
    ) -> list[dict[str, Any]]:
        filename = str(getattr(upload_file, "filename", "") or "")
        content = upload_file.read()
        if inspect.isawaitable(content):
            content = await content
        data = bytes(content)
        if _is_archive(filename, data):
            return self._import_zip_bytes(data, tags=tags, caption=caption)
        return [
            self.store.import_bytes(
                data,
                filename=filename,
                title=title[:160] or Path(filename).stem,
                caption=caption,
                tags=tags,
                source="web_upload",
            )
        ]

    def _import_path_items(
        self,
        path_text: str,
        *,
        title: str,
        tags: list[str],
        caption: str,
        source: str,
    ) -> list[dict[str, Any]]:
        path = Path(path_text).expanduser()
        if not path.exists():
            return [{"ok": False, "error": "file_not_found", "path": path_text}]
        if path.is_dir():
            results = []
            for item in _image_paths(path):
                results.append(
                    self.store.import_asset(
                        str(item),
                        caption=caption,
                        tags=tags,
                        source=source,
                        keep_original_path=self.allow_original_path,
                    )
                )
                if len(results) >= MAX_BATCH_ITEMS:
                    break
            return results or [{"ok": False, "error": "no_images_found", "path": path_text}]
        if path.suffix.lower() in ARCHIVE_SUFFIXES:
            try:
                return self._import_zip_bytes(
                    path.read_bytes(),
                    tags=tags,
                    caption=caption,
                    source=source,
                )
            except OSError:
                return [{"ok": False, "error": "file_read_failed", "path": path_text}]
        return [
            self.store.import_asset(
                str(path),
                title=title[:160],
                caption=caption,
                tags=tags,
                source=source,
                keep_original_path=self.allow_original_path,
            )
        ]

    def _import_zip_bytes(
        self,
        content: bytes,
        *,
        tags: list[str],
        caption: str,
        source: str = "archive_upload",
    ) -> list[dict[str, Any]]:
        archive_limit = self.store.max_import_bytes * MAX_ARCHIVE_FACTOR
        if len(content) > archive_limit:
            return [{"ok": False, "error": "archive_too_large", "size": len(content)}]
        results: list[dict[str, Any]] = []
        try:
            with ZipFile(BytesIO(content)) as archive:
                for item in archive.infolist():
                    if item.is_dir() or Path(item.filename).suffix.lower() not in IMAGE_SUFFIXES:
                        continue
                    if item.file_size > self.store.max_import_bytes:
                        results.append(
                            {
                                "ok": False,
                                "error": "file_too_large",
                                "filename": item.filename,
                                "size": item.file_size,
                            }
                        )
                        continue
                    results.append(
                        self.store.import_bytes(
                            archive.read(item),
                            filename=item.filename,
                            title=Path(item.filename).stem,
                            caption=caption,
                            tags=tags,
                            source=source,
                            original_path=item.filename,
                        )
                    )
                    if len(results) >= MAX_BATCH_ITEMS:
                        break
        except (BadZipFile, OSError):
            return [{"ok": False, "error": "bad_archive"}]
        return results or [{"ok": False, "error": "no_images_found"}]

    async def _import_external_urls(
        self,
        urls: list[str],
        *,
        tags: list[str],
        caption: str,
        timeout_seconds: int,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        timeout = aiohttp.ClientTimeout(total=max(3, timeout_seconds))
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for url in urls:
                content, filename, error = await _download_url(
                    session,
                    url,
                    max_bytes=self.store.max_import_bytes,
                )
                if error:
                    results.append({"ok": False, "error": error, "url": url})
                    continue
                results.append(
                    self.store.import_bytes(
                        content,
                        filename=filename,
                        title=Path(filename).stem,
                        caption=caption,
                        tags=tags,
                        source="external_url",
                        original_path=url,
                    )
                )
        return results

    async def _maybe_auto_upload_batch(self, results: list[dict[str, Any]]) -> None:
        for result in results:
            await self._maybe_auto_upload(result)


async def _download_url(
    session: aiohttp.ClientSession,
    url: str,
    *,
    max_bytes: int,
) -> tuple[bytes, str, str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return b"", "", "unsupported_url_scheme"
    try:
        async with session.get(url) as resp:
            if resp.status >= 400:
                return b"", "", f"download_http_{resp.status}"
            body = bytearray()
            async for chunk in resp.content.iter_chunked(256 * 1024):
                body.extend(chunk)
                if len(body) > max_bytes:
                    return b"", "", "file_too_large"
    except Exception as exc:  # noqa: BLE001
        return b"", "", f"{type(exc).__name__}: {str(exc)[:200]}"
    filename = Path(unquote(parsed.path)).name or "external_image"
    return bytes(body), filename, ""


def _batch_response(results: list[dict[str, Any]]) -> dict[str, Any]:
    imported = [item.get("asset") for item in results if item.get("ok") and item.get("asset")]
    failed = [item for item in results if not item.get("ok")]
    response = {
        "ok": bool(imported) and not failed,
        "results": results,
        "assets": imported,
        "asset": imported[0] if len(imported) == 1 else None,
        "imported_count": len(imported),
        "failed_count": len(failed),
        "failed": failed,
    }
    if imported and failed:
        response["ok"] = True
        response["partial"] = True
    return response


def _upload_files(files: Any) -> list[Any]:
    result = []
    getter = getattr(files, "getlist", None)
    for key in ("file", "files"):
        if callable(getter):
            result.extend(getter(key))
        else:
            item = files.get(key)
            if item is not None:
                result.append(item)
    return [item for index, item in enumerate(result) if item and item not in result[:index]]


def _image_paths(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            yield path


def _is_archive(filename: str, content: bytes) -> bool:
    return Path(filename).suffix.lower() in ARCHIVE_SUFFIXES or content.startswith(b"PK\x03\x04")


def _tags(value: object) -> list[str]:
    if isinstance(value, str):
        raw = value.replace("\n", ",").replace("，", ",").replace("、", ",").split(",")
    elif isinstance(value, list):
        raw = value
    else:
        raw = []
    result = []
    for item in raw:
        text = str(item).strip().lower()
        if text and text not in result:
            result.append(text)
    return result


def _urls(value: object) -> list[str]:
    if isinstance(value, str):
        raw = value.replace("\r", "\n").replace(",", "\n").split("\n")
    elif isinstance(value, list):
        raw = value
    else:
        raw = []
    result = []
    for item in raw:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result
