import base64
import json
import random
from pathlib import Path
from typing import Any

from astrbot.api import logger


class CommonHandler:
    """处理通用和扩展 Webhook (GitHub, DockerHub 等)"""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        # Use dedicated common background resources
        self.bg_resource_path = (
            Path(__file__).parent.parent / "utils" / "resources" / "common_bg"
        )

    async def process_common_webhook(
        self, body: str, headers: dict[str, str]
    ) -> dict | None:
        """处理通用 Webhook 数据"""
        try:
            # 1. 检测是否为 GitHub
            if "X-GitHub-Event" in headers:
                res = self._handle_github(body, headers)
                res["poster_url"] = self._get_random_bg_for_source(
                    res.get("source", "github")
                )
                return res

            # 2. 尝试解析为 JSON
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                # 纯文本处理
                return {
                    "message_text": f"通用Webhook:\n{body}",
                    "message_type": "common",
                }

            # 3. 检测是否为 DockerHub (简单检测机制)
            if "push_data" in data and "repository" in data:
                res = self._handle_dockerhub(data)
                res["poster_url"] = self._get_random_bg_for_source(
                    res.get("source", "dockerhub")
                )
                return res

            # 4. 兜底处理：检查是否有常见的 content/message 字段
            content = data.get("content") or data.get("message") or data.get("text")
            if content:
                source = data.get("source", "common")
                return {
                    "message_text": str(content),
                    "message_type": "common",
                    "source": source,
                    "poster_url": self._get_random_bg_for_source(source),
                }

            # 5. 极端兜底：将整个 JSON 格式化输出
            source = data.get("source", "common")
            return {
                "message_text": f"通用Webhook:\n{json.dumps(data, indent=2, ensure_ascii=False)}",
                "message_type": "common",
                "source": source,
                "poster_url": self._get_random_bg_for_source(source),
            }

        except Exception as e:
            logger.error(f"通用 Webhook 处理失败: {e}")
            return None

    def _handle_github(self, body: str, headers: dict[str, str]) -> dict:
        event = headers.get("X-GitHub-Event", "unknown")
        try:
            data = json.loads(body)
            repo_name = data.get("repository", {}).get("full_name", "Unknown Repo")
            sender = data.get("sender", {}).get("login", "Unknown User")

            if event == "push":
                ref = data.get("ref", "").split("/")[-1]
                commits = data.get("commits", [])
                msg = f"GitHub推送 - {repo_name}\n"
                msg += f"分支: {ref}\n"
                msg += f"推送者: {sender}\n"
                if commits:
                    msg += f"摘要: {commits[0].get('message', '').splitlines()[0]}"
                return {
                    "message_text": msg,
                    "message_type": "common",
                    "source": "github",
                }

            elif event == "release":
                action = data.get("action", "")
                tag = data.get("release", {}).get("tag_name", "")
                msg = f"GitHub发布 {action} - {repo_name}\n"
                msg += f"版本: {tag}\n"
                msg += f"发布者: {sender}"
                return {
                    "message_text": msg,
                    "message_type": "common",
                    "source": "github",
                }

            # 其他事件显示类型
            return {
                "message_text": f"⚓ GitHub Event: {event}\n仓库: {repo_name}\n用户: {sender}",
                "message_type": "common",
                "source": "github",
            }
        except Exception:
            return {
                "message_text": f"GitHub: {event}",
                "message_type": "common",
                "source": "github",
            }

    def _handle_dockerhub(self, data: dict) -> dict:
        repo = data.get("repository", {}).get("repo_name", "Unknown")
        tag = data.get("push_data", {}).get("tag", "latest")
        pusher = data.get("push_data", {}).get("pusher", "Unknown")

        msg = "DockerHub更新\n"
        msg += f"仓库: {repo}\n"
        msg += f"标签: {tag}\n"
        msg += f"推送者: {pusher}"
        return {"message_text": msg, "message_type": "common", "source": "dockerhub"}

    def _get_random_bg_for_source(self, source: str) -> str:
        """根据来源获取本地随机背景图，返回 base64 data url"""
        if not self.bg_resource_path.exists():
            return ""

        # 搜寻逻辑：
        # 直接使用来源名称作为前缀，例如 source='alas' 匹配 alas001.jpg, alas002.png 等
        # 如果未识别到任何匹配项，则搜索以 'default' 开头的图片
        search_prefix = source.lower() if source else "default"

        # 获取目录下所有匹配的文件
        matches = []
        try:
            for file in self.bg_resource_path.iterdir():
                if file.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
                    # 匹配逻辑：文件名以来源名开头
                    if file.name.lower().startswith(search_prefix):
                        matches.append(file)

            # 如果来源没有匹配到，或者来源原本就是 default，则尝试寻找 default 开头的图
            if not matches and search_prefix != "default":
                for file in self.bg_resource_path.iterdir():
                    if file.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
                        if file.name.lower().startswith("default"):
                            matches.append(file)

            if not matches:
                return ""

            # 随机选择一张
            selected_file = random.choice(matches)

            # 读取并转为 base64
            with open(selected_file, "rb") as f:
                img_data = f.read()
                b64 = base64.b64encode(img_data).decode()
                ext = selected_file.suffix.lower().replace(".", "")
                if ext == "jpg":
                    ext = "jpeg"
                return f"data:image/{ext};base64,{b64}"

        except Exception as e:
            logger.error(f"加载本地通用背景图失败: {e}")
            return ""
