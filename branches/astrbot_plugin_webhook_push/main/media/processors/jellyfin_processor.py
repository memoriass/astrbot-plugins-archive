"""
Jellyfin媒体处理器
专门处理Jellyfin媒体服务器的webhook数据
"""

from astrbot.api import logger

from .base_processor import BaseMediaProcessor


class JellyfinProcessor(BaseMediaProcessor):
    """Jellyfin媒体处理器"""

    def can_handle(self, data: dict, headers: dict | None = None) -> bool:
        """检查是否为Jellyfin数据"""
        # Jellyfin特征：包含ItemType或SeriesName字段，或者包含NotificationType
        if any(
            k in data for k in ["ItemType", "SeriesName", "NotificationType", "ItemId"]
        ):
            logger.debug("检测到Jellyfin数据结构特征")
            return True

        # 检查嵌套结构
        if "Item" in data and isinstance(data["Item"], dict):
            item = data["Item"]
            if any(k in item for k in ["ItemType", "SeriesName", "ItemId"]):
                return True

        # 检查User-Agent
        if headers:
            user_agent = headers.get("User-Agent", "").lower()
            if "jellyfin" in user_agent:
                logger.debug("通过User-Agent检测到Jellyfin")
                return True

        return False

    def convert_to_standard(self, data: dict, headers: dict | None = None) -> dict:
        """将Jellyfin数据转换为标准格式"""
        try:
            logger.debug(f"Jellyfin 原始数据结构: {data}")

            # 处理可能的包装结构 (Notification plugin)
            payload = data
            if "Item" in data and isinstance(data["Item"], dict):
                # 如果有 Item 字段，认为它是包装后的数据
                payload = data["Item"]
                # 将顶层的服务器信息合并进来
                for key in ["ServerId", "ServerName", "ServerUrl"]:
                    if key in data and key not in payload:
                        payload[key] = data[key]

            # 提取基本信息
            item_type = payload.get("ItemType", payload.get("Type", "Episode"))
            item_name = payload.get("Name", "")

            # 提取剧集信息
            series_name = payload.get("SeriesName", "")
            season_number = payload.get(
                "SeasonNumber", payload.get("ParentIndexNumber", "")
            )
            episode_number = payload.get(
                "EpisodeNumber", payload.get("IndexNumber", "")
            )

            # 如果是剧集类型但没有剧集名，使用Name作为剧集名
            if item_type in ["Series", "Season"] and not series_name:
                series_name = item_name

            # 提取其他信息
            year = payload.get("Year", payload.get("ProductionYear", ""))
            overview = self.clean_text(payload.get("Overview", ""))

            # 处理时长
            runtime_ticks = payload.get("RunTimeTicks", 0)
            runtime = self.safe_get_runtime(runtime_ticks)

            # 提取图片信息
            image_url = ""
            if payload.get("ImageUrl"):
                image_url = payload.get("ImageUrl")
            elif payload.get("PrimaryImageUrl"):
                image_url = payload.get("PrimaryImageUrl")
            elif payload.get("ItemId"):
                item_id = payload.get("ItemId")
                server_url = payload.get("ServerUrl", data.get("ServerUrl", ""))
                if server_url:
                    server_url = server_url.rstrip("/")
                    image_url = f"{server_url}/Items/{item_id}/Images/Primary"

            logger.debug(f"Jellyfin 图片URL: {image_url}")

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
                source_data="jellyfin",
            )

            # 附加元数据
            result["metadata"] = self.extract_jellyfin_metadata(payload)

            logger.debug(f"Jellyfin 转换结果: {result}")
            return result

        except Exception as e:
            logger.error(f"Jellyfin 数据转换失败: {e}")
            logger.debug(f"Jellyfin 转换失败详情: {e}", exc_info=True)
            return {}

    def extract_jellyfin_metadata(self, data: dict) -> dict:
        """提取Jellyfin特有的元数据"""
        metadata = {}

        # 提取演员信息
        if data.get("Actors"):
            metadata["actors"] = data.get("Actors", [])[:5]  # 限制前5个演员

        # 提取导演信息
        if data.get("Directors"):
            metadata["directors"] = data.get("Directors", [])

        # 提取制片公司
        if data.get("Studios"):
            metadata["studios"] = data.get("Studios", [])

        # 提取评分
        if data.get("CommunityRating"):
            metadata["rating"] = data.get("CommunityRating")

        # 提取标签
        if data.get("Tags"):
            metadata["tags"] = data.get("Tags", [])

        # 提取流媒体信息
        if data.get("MediaStreams"):
            streams = data.get("MediaStreams", [])
            video_streams = [s for s in streams if s.get("Type") == "Video"]
            audio_streams = [s for s in streams if s.get("Type") == "Audio"]

            if video_streams:
                video = video_streams[0]
                metadata["video_codec"] = video.get("Codec", "")
                metadata["resolution"] = (
                    f"{video.get('Width', '')}x{video.get('Height', '')}"
                )

            if audio_streams:
                audio = audio_streams[0]
                metadata["audio_codec"] = audio.get("Codec", "")
                metadata["audio_channels"] = audio.get("Channels", "")

        return metadata

    def get_jellyfin_library_info(self, data: dict) -> dict:
        """获取Jellyfin媒体库信息"""
        library_info = {}

        if data.get("LibraryName"):
            library_info["library_name"] = data.get("LibraryName")

        if data.get("LibraryId"):
            library_info["library_id"] = data.get("LibraryId")

        if data.get("CollectionType"):
            library_info["collection_type"] = data.get("CollectionType")

        return library_info
