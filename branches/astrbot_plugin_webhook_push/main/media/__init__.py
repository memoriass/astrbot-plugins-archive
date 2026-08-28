"""
媒体处理模块
包含媒体数据预处理、核心处理和数据丰富功能
按照处理流程组织：预处理 -> 核心处理 -> 数据丰富
"""

from .data_processor import MediaDataProcessor
from .enrichment import EnrichmentManager
from .media_handler import MediaHandler
from .processors.base_processor import BaseMediaProcessor
from .processors.emby_processor import EmbyProcessor
from .processors.generic_processor import GenericProcessor
from .processors.jellyfin_processor import JellyfinProcessor
from .processors.plex_processor import PlexProcessor
from .processors.processor_manager import ProcessorManager

__all__ = [
    "MediaDataProcessor",
    "MediaHandler",
    "EnrichmentManager",
    "BaseMediaProcessor",
    "EmbyProcessor",
    "JellyfinProcessor",
    "PlexProcessor",
    "GenericProcessor",
    "ProcessorManager",
]
