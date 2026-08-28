import json
import os
from pathlib import Path
from astrbot.api import logger

class GameAliasManager:
    def __init__(self, data_path: Path):
        # 插件本体中的 utils/defaults 目录路径，存放默认配置和初始占位
        self.plugin_utils_dir = Path(__file__).parent.parent / "utils" / "defaults"
        self.default_alias_file = self.plugin_utils_dir / "game_aliases.json"
        self.default_cache_file = self.plugin_utils_dir / "game_aliases_cache.json"
        
        # 用户 plugin_data 中的数据目录路径（去除了 utils 嵌套层级）
        self.config_dir = data_path / "game_aliases"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.user_alias_file = self.config_dir / "aliases.json"
        self.user_cache_file = self.config_dir / "aliases_cache.json"
        
        self._cache = {}
        self._unknown_cache = {}
        self._load()

    def _load(self):
        """加载别名配置与缓存，执行初始化复制或增量更新"""
        # ================== 1. 处理主别名文件 ==================
        default_aliases = {}
        if self.default_alias_file.exists():
            try:
                with open(self.default_alias_file, 'r', encoding='utf-8') as f:
                    default_aliases = json.load(f)
            except Exception as e:
                logger.error(f"读取插件内置默认别名文件失败: {e}")
        else:
            logger.warning(f"缺失插件内置文件 {self.default_alias_file}，使用空字典兜底。")

        if not self.user_alias_file.exists():
            self._cache = default_aliases.copy()
            self._save_main()
            logger.info(f"[Alias] 已将内置默认游戏别名初始化至 {self.user_alias_file}")
        else:
            try:
                with open(self.user_alias_file, 'r', encoding='utf-8') as f:
                    self._cache = json.load(f)
                    
                changed = False
                for k, v in default_aliases.items():
                    if k not in self._cache:
                        self._cache[k] = v
                        changed = True
                
                if changed:
                    self._save_main()
                    logger.info("[Alias] 检测到内置游戏别名库有更新，已增量合并补充至您的配置文件中。")
            except Exception as e:
                logger.error(f"读取用户别名文件失败: {e}")
                self._cache = default_aliases.copy()

        # ================== 2. 处理缓存别名文件(临时记录) ==================
        default_cache = {"placeholder_DO_NOT_DELETE": "placeholder"}
        if self.default_cache_file.exists():
            try:
                with open(self.default_cache_file, 'r', encoding='utf-8') as f:
                    default_cache = json.load(f)
            except Exception as e:
                logger.error(f"读取插件内置默认别名缓存文件失败: {e}")

        if not self.user_cache_file.exists():
            self._unknown_cache = default_cache.copy()
            self._save_cache()
            logger.info(f"[Alias] 已初始化未知来源缓存文件至 {self.user_cache_file}")
        else:
            try:
                with open(self.user_cache_file, 'r', encoding='utf-8') as f:
                    self._unknown_cache = json.load(f)
            except Exception as e:
                logger.error(f"读取用户别名缓存文件失败: {e}")
                self._unknown_cache = default_cache.copy()

    def _save_main(self):
        """保存主别名配置到用户目录"""
        try:
            with open(self.user_alias_file, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存主游戏别名文件失败: {e}")

    def _save_cache(self):
        """保存未匹配的别名缓存到临时 JSON 中"""
        try:
            with open(self.user_cache_file, 'w', encoding='utf-8') as f:
                json.dump(self._unknown_cache, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存游戏别名缓存文件失败: {e}")

    def get_canonical_name(self, source: str) -> str:
        """获取规范化的来源名称。如果完全未知，则记录到临时缓存 JSON 中供用户未来迁移。"""
        if not source:
            return "default"
            
        source_lower = source.lower().strip()
        
        # 精确匹配主配置字典
        if source_lower in self._cache:
            return self._cache[source_lower]
            
        # 模糊匹配主配置字典
        for alias, canonical in self._cache.items():
            if alias in source_lower:
                return canonical
                
        # 未在主 JSON 匹配到，处理临时生成名，并记入 cache json 中去
        clean_name = source_lower.replace(" ", "_").replace("(", "").replace(")", "").replace("（", "").replace("）", "")
        if clean_name:
            if source_lower not in self._unknown_cache:
                logger.info(f"[Alias] 发现未记录的通知来源 '{source}'，已自动写入临时记录表 {self.user_cache_file} 供日后参考。")
                self._unknown_cache[source_lower] = clean_name
                self._save_cache()
            
            # 返回它在 cache 表里的映射名
            return self._unknown_cache.get(source_lower, clean_name)
            
        return "default"
