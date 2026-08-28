"""
Emby媒体处理器
专门处理Emby媒体服务器的webhook数据
"""

from astrbot.api import logger

from .base_processor import BaseMediaProcessor


class EmbyProcessor(BaseMediaProcessor):
    """Emby媒体处理器"""

    def can_handle(self, data: dict, headers: dict | None = None) -> bool:
        """检查是否为Emby数据"""
        # Emby特征：包含Item和Server字段
        if "Item" in data and "Server" in data:
            logger.debug("检测到Emby数据结构特征")
            return True

        # 检查User-Agent
        if headers:
            user_agent = headers.get("User-Agent", "").lower()
            if "emby" in user_agent:
                logger.debug("通过User-Agent检测到Emby")
                return True

        return False

    def convert_to_standard(self, data: dict, headers: dict | None = None) -> dict:
        """将Emby数据转换为标准格式"""
        try:
            item = data.get("Item", {})
            event = data.get("Event", "")
            logger.debug(f"Emby 原始数据结构: {data}")
            logger.debug(f"Emby 事件类型: {event}")

            # 提取基本信息
            item_type = item.get("Type", "Unknown")
            item_name = item.get("Name", "")

            # 提取剧集/音乐信息
            series_name = ""
            season_number = ""
            episode_number = ""

            if item_type == "Episode":
                series_name = item.get("SeriesName", "")
                season_number = item.get("ParentIndexNumber", "")
                episode_number = item.get("IndexNumber", "")
            elif item_type == "Season":
                series_name = item.get("SeriesName", "")
                season_number = item.get("IndexNumber", "")
            elif item_type == "Series":
                series_name = item_name
            elif item_type == "Audio":
                # 音乐处理
                series_name = item.get("AlbumArtist", "")  # 艺术家
                album_name = item.get("Album", "")
                if album_name:
                    item_name = f"{album_name} - {item_name}"
            else:
                # 对于电影等其他类型，使用item_name
                pass

            # 提取外部 ID (非常关键，用于后续数据富化)
            provider_ids = item.get("ProviderIds", {})

            # 提取其他信息
            year = item.get("ProductionYear", "")
            overview = self.clean_text(item.get("Overview", ""))
            runtime_ticks = item.get("RunTimeTicks", 0)
            runtime = self.safe_get_runtime(runtime_ticks)

            # 提取图片信息
            image_url = ""
            server_info = data.get("Server", {})
            server_url = server_info.get("Url", "")
            item_id = item.get("Id", "")

            # 优先使用直接提供的 URL
            direct_image_url = (
                item.get("PrimaryImageUrl")
                or item.get("ImageUrl")
                or data.get("PrimaryImageUrl")
            )

            if direct_image_url:
                image_url = direct_image_url
            elif server_url and item_id:
                # 如果没有直接 URL，构建拼接 URL
                # 注意：某些 Emby 需要 api_key 才能访问图片，这里仅构建基础，富化流程会尝试补充
                server_url = server_url.rstrip("/")
                image_url = f"{server_url}/Items/{item_id}/Images/Primary"

            result = self.create_standard_data(
                item_type=item_type,
                series_name=series_name,
                item_name=item_name,
                season_number=season_number,
                episode_number=episode_number,
                year=year,
                overview=overview,
                runtime=runtime,
                image_url=image_url,
                source_data="emby",
            )

            # 附加元数据与外部 ID
            result["metadata"] = self.extract_emby_metadata(item)
            result["provider_ids"] = provider_ids
            result["emby_event"] = event

            # 如果是播放事件，可以附带用户信息
            user = data.get("User", {})
            if user and "Name" in user:
                result["trigger_user"] = user["Name"]

            logger.debug(f"Emby 转换结果: {result}")
            return result

        except Exception as e:
            logger.error(f"Emby 数据转换失败: {e}")
            logger.debug(f"Emby 转换失败详情: {e}", exc_info=True)
            return {}

    def extract_emby_metadata(self, item: dict) -> dict:
        """提取Emby特有的元数据"""
        metadata = {}

        # 提取演员信息
        people = item.get("People", [])
        actors = [
            person.get("Name", "") for person in people if person.get("Type") == "Actor"
        ]
        if actors:
            metadata["actors"] = actors[:5]  # 限制前5个演员

        # 提取导演信息
        directors = [
            person.get("Name", "")
            for person in people
            if person.get("Type") == "Director"
        ]
        if directors:
            metadata["directors"] = directors

        # 提取制片公司
        studios = item.get("Studios", [])
        if studios:
            metadata["studios"] = [studio.get("Name", "") for studio in studios]

        # 提取评分
        community_rating = item.get("CommunityRating")
        if community_rating:
            metadata["rating"] = community_rating

        # 提取标签
        tags = item.get("Tags", [])
        if tags:
            metadata["tags"] = tags

        return metadata
