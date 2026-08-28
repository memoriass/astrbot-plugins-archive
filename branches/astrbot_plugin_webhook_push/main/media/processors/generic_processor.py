"""
通用媒体处理器
处理未知来源或通用格式的媒体数据
"""

from astrbot.api import logger

from .base_processor import BaseMediaProcessor


class GenericProcessor(BaseMediaProcessor):
    """通用媒体处理器"""

    def can_handle(self, data: dict, headers: dict | None = None) -> bool:
        """通用处理器可以处理任何数据"""
        return True

    def convert_to_standard(self, data: dict, headers: dict | None = None) -> dict:
        """将通用数据转换为标准格式"""
        try:
            logger.debug(f"通用转换器处理数据: {data}")

            # 提取基本信息，尝试多种可能的字段名
            item_type = (
                data.get("ItemType")
                or data.get("Type")
                or data.get("item_type")
                or data.get("type", "Episode")
            )

            # 标准化类型名称
            item_type = self._normalize_type(item_type)

            # 提取名称信息
            item_name = (
                data.get("Name")
                or data.get("name")
                or data.get("title")
                or data.get("Title", "")
            )

            # 提取剧集信息
            series_name = (
                data.get("SeriesName")
                or data.get("series_name")
                or data.get("show_name")
                or data.get("ShowName", "")
            )

            season_number = (
                data.get("SeasonNumber")
                or data.get("season_number")
                or data.get("ParentIndexNumber")
                or data.get("season", "")
            )

            episode_number = (
                data.get("EpisodeNumber")
                or data.get("episode_number")
                or data.get("IndexNumber")
                or data.get("episode", "")
            )

            # 如果是剧集类型但没有剧集名，使用item_name
            if item_type in ["Series", "Season"] and not series_name:
                series_name = item_name

            # 提取年份
            year = (
                data.get("Year")
                or data.get("year")
                or data.get("ProductionYear")
                or data.get("production_year", "")
            )

            # 提取简介
            overview = (
                data.get("Overview")
                or data.get("overview")
                or data.get("summary")
                or data.get("Summary")
                or data.get("description")
                or data.get("Description", "")
            )
            overview = self.clean_text(overview)

            # 提取时长
            runtime = ""
            runtime_ticks = (
                data.get("RunTimeTicks")
                or data.get("runtime_ticks")
                or data.get("duration")
                or 0
            )

            # 尝试不同的时长格式
            if runtime_ticks:
                runtime = self.safe_get_runtime(runtime_ticks)
            elif data.get("runtime"):
                runtime_value = data.get("runtime")
                if isinstance(runtime_value, str) and runtime_value.isdigit():
                    runtime = f"{runtime_value}分钟"
                elif isinstance(runtime_value, (int, float)):
                    runtime = f"{int(runtime_value)}分钟"

            # 提取图片URL
            image_url = (
                data.get("image_url")
                or data.get("ImageUrl")
                or data.get("poster_url")
                or data.get("PosterUrl")
                or data.get("thumbnail")
                or data.get("Thumbnail", "")
            )

            result = self.create_standard_data(
                item_type=item_type,
                series_name=series_name,
                item_name=item_name,
                season_number=str(season_number) if season_number else "",
                episode_number=str(episode_number) if episode_number else "",
                year=str(year) if year else "",
                overview=overview,
                runtime=runtime,
                image_url=image_url,
                source_data="generic",
            )

            logger.debug(f"通用转换结果: {result}")
            return result

        except Exception as e:
            logger.error(f"通用数据转换失败: {e}")
            logger.debug(f"通用转换失败详情: {e}", exc_info=True)
            return {}

    def _normalize_type(self, item_type: str) -> str:
        """标准化媒体类型名称"""
        if not item_type:
            return "Episode"

        item_type = str(item_type).strip()

        # 类型映射表
        type_mapping = {
            "movie": "Movie",
            "film": "Movie",
            "电影": "Movie",
            "episode": "Episode",
            "剧集": "Episode",
            "集": "Episode",
            "season": "Season",
            "剧季": "Season",
            "季": "Season",
            "series": "Series",
            "show": "Series",
            "电视剧": "Series",
            "剧": "Series",
            "album": "Album",
            "专辑": "Album",
            "song": "Song",
            "track": "Song",
            "歌曲": "Song",
            "音乐": "Song",
            "video": "Video",
            "视频": "Video",
            "audio": "Audio",
            "音频": "Audio",
            "book": "Book",
            "图书": "Book",
            "audiobook": "AudioBook",
            "有声书": "AudioBook",
        }

        # 尝试直接匹配
        normalized = type_mapping.get(item_type.lower())
        if normalized:
            return normalized

        # 尝试部分匹配
        item_type_lower = item_type.lower()
        for key, value in type_mapping.items():
            if key in item_type_lower or item_type_lower in key:
                return value

        # 如果都没匹配到，返回首字母大写的原值
        return item_type.title()

    def extract_generic_metadata(self, data: dict) -> dict:
        """提取通用元数据"""
        metadata = {}

        # 尝试提取各种可能的元数据字段
        metadata_fields = {
            "rating": ["rating", "Rating", "score", "Score"],
            "genres": ["genres", "Genres", "genre", "Genre", "tags", "Tags"],
            "actors": ["actors", "Actors", "cast", "Cast"],
            "directors": ["directors", "Directors", "director", "Director"],
            "studios": ["studios", "Studios", "studio", "Studio", "network", "Network"],
            "language": ["language", "Language", "lang", "Lang"],
            "country": ["country", "Country", "origin", "Origin"],
        }

        for meta_key, possible_fields in metadata_fields.items():
            for field in possible_fields:
                if field in data and data[field]:
                    metadata[meta_key] = data[field]
                    break

        return metadata
