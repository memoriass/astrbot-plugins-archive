"""
媒体处理器模块
提供模块化的媒体数据处理功能
"""

from .base_processor import BaseMediaProcessor
from .emby_processor import EmbyProcessor
from .generic_processor import GenericProcessor
from .jellyfin_processor import JellyfinProcessor
from .plex_processor import PlexProcessor
from .processor_manager import ProcessorManager

__all__ = [
    "BaseMediaProcessor",
    "EmbyProcessor",
    "JellyfinProcessor",
    "PlexProcessor",
    "GenericProcessor",
    "ProcessorManager",
]
