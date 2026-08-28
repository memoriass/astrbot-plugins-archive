from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from time import monotonic, time
from typing import Iterator


class AudioStorage:
    def __init__(self, root: Path, *, max_file_bytes: int, max_total_bytes: int,
                 ttl_seconds: int, cleanup_interval_seconds: int) -> None:
        self.root = root
        self.max_file_bytes = max(1, int(max_file_bytes))
        self.max_total_bytes = max(self.max_file_bytes, int(max_total_bytes))
        self.ttl_seconds = max(60, int(ttl_seconds))
        self.cleanup_interval_seconds = max(10, int(cleanup_interval_seconds))
        self._leases: set[Path] = set()
        self._last_cleanup = 0.0

    def ensure_capacity(self, incoming_bytes: int) -> bool:
        if incoming_bytes <= 0 or incoming_bytes > self.max_file_bytes:
            return False
        self.cleanup(force=True)
        return self.total_bytes() <= self.max_total_bytes

    def total_bytes(self) -> int:
        total = 0
        if not self.root.exists():
            return total
        for path in self.root.iterdir():
            try:
                if path.is_file():
                    total += path.stat().st_size
            except OSError:
                continue
        return total

    def cleanup(self, *, force: bool = False) -> int:
        now = monotonic()
        if not force and now - self._last_cleanup < self.cleanup_interval_seconds:
            return 0
        self._last_cleanup = now
        cutoff = time() - self.ttl_seconds
        removed = 0
        if not self.root.exists():
            return removed
        for path in self.root.iterdir():
            resolved = path.resolve()
            try:
                if path.is_file() and resolved not in self._leases and path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except OSError:
                continue
        return removed

    @contextmanager
    def lease(self, path: Path | str) -> Iterator[Path]:
        resolved = Path(path).resolve()
        try:
            resolved.relative_to(self.root.resolve())
        except ValueError as exc:
            raise ValueError("audio_lease_outside_root") from exc
        self._leases.add(resolved)
        try:
            yield resolved
        finally:
            self._leases.discard(resolved)
