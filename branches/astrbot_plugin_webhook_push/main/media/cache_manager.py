import json
import os
import sqlite3
import time

from astrbot.api import logger


class CacheManager:
    """基于 SQLite 的持久化缓存管理器"""

    def __init__(self, db_dir: str, persistence_days: int = 7):
        self.db_dir = db_dir
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)

        self.db_path = os.path.join(db_dir, "metadata_cache.db")
        self.persistence_seconds = persistence_days * 24 * 3600
        self._init_db()

    def _init_db(self):
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS media_cache (
                    cache_key TEXT PRIMARY KEY,
                    data TEXT,
                    expiry INTEGER
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_expiry ON media_cache(expiry)")
            conn.commit()

    def get(self, key: str) -> dict | None:
        """获取缓存"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT data FROM media_cache WHERE cache_key = ? AND expiry > ?",
                    (key, int(time.time())),
                )
                row = cursor.fetchone()
                if row:
                    return json.loads(row[0])
        except Exception as e:
            logger.error(f"持久化缓存读取失败: {e}")
        return None

    def set(self, key: str, data: dict):
        """设置缓存"""
        try:
            expiry = int(time.time() + self.persistence_seconds)
            data_json = json.dumps(data)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO media_cache (cache_key, data, expiry) VALUES (?, ?, ?)",
                    (key, data_json, expiry),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"持久化缓存写入失败: {e}")

    def cleanup(self):
        """清理过期缓存"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "DELETE FROM media_cache WHERE expiry < ?", (int(time.time()),)
                )
                if cursor.rowcount > 0:
                    logger.info(f"已清理 {cursor.rowcount} 条过期的持久化缓存数据")
                conn.commit()
        except Exception as e:
            logger.error(f"清理过期缓存失败: {e}")

    def clear_all(self) -> int:
        """清除所有缓存"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("DELETE FROM media_cache")
                count = cursor.rowcount
                conn.commit()
                logger.info(f"已手动清除 {count} 条所有媒体缓存数据")
                return count
        except Exception as e:
            logger.error(f"手动清除缓存失败: {e}")
            return 0
