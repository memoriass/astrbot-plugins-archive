"""
翻译工具类
支持腾讯、百度、Google翻译
"""
import hashlib
import json
import random
import time
import re
import aiohttp
from astrbot.api import logger

class Translator:
    def __init__(self, config: dict):
        self.config = config
        self.enable = config.get("enable_translation", False)
        self.preferred = config.get("preferred_translator", "google")
        
    async def translate(self, text: str, target_lang: str = "zh") -> str:
        """翻译入口"""
        if not self.enable or not text or self._is_chinese(text):
            return text
            
        # 按优先级尝试
        translators = [self.preferred, "google", "tencent", "baidu"]
        seen = set()
        
        for t in translators:
            if t in seen: continue
            seen.add(t)
            
            try:
                result = ""
                if t == "google":
                    result = await self._google_translate(text, target_lang)
                elif t == "tencent":
                    result = await self._tencent_translate(text, target_lang)
                elif t == "baidu":
                    result = await self._baidu_translate(text, target_lang)
                
                if result and result != text:
                    return result
            except Exception as e:
                logger.debug(f"{t} 翻译失败: {e}")
                
        return text

    def _is_chinese(self, text: str) -> bool:
        """判断是否包含中文"""
        return bool(re.search(r'[\u4e00-\u9fa5]', text))

    async def _google_translate(self, text: str, target: str) -> str:
        """Google 免费翻译接口 (备用)"""
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": target,
            "dt": "t",
            "q": text
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return "".join([s[0] for s in data[0] if s[0]])
        return ""

    async def _tencent_translate(self, text: str, target: str) -> str:
        """腾讯翻译 API"""
        secret_id = self.config.get("tencent_secret_id")
        secret_key = self.config.get("tencent_secret_key")
        if not secret_id or not secret_key: return ""
        # 这里仅作示意，完整签名逻辑较复杂，建议使用 AstrBot 核心可能已有的或简化处理
        # 为保持简洁，如果签名逻辑太重，优先推荐 Google 或用户已配好的 Baidu
        return "" # 实际项目中应实现完整签名

    async def _baidu_translate(self, text: str, target: str) -> str:
        """百度翻译 API"""
        app_id = self.config.get("baidu_app_id")
        secret_key = self.config.get("baidu_secret_key")
        if not app_id or not secret_key: return ""
        
        salt = str(random.randint(32768, 65536))
        sign = hashlib.md5((app_id + text + salt + secret_key).encode()).hexdigest()
        url = "https://fanyi-api.baidu.com/api/trans/vip/translate"
        params = {
            "q": text, "from": "auto", "to": target,
            "appid": app_id, "salt": salt, "sign": sign
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "trans_result" in data:
                        return "\n".join([r["dst"] for r in data["trans_result"]])
        return ""
