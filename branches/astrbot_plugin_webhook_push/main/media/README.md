# Media Processing Module

这个模块包含了媒体处理相关的所有功能，按照处理流程进行了清晰的组织。

## 处理流程

**预处理  核心处理  数据丰富**

## 目录结构

`
media/
 __init__.py                   # 模块初始化文件
 README.md                     # 模块说明文档
 data_processor.py             # 媒体数据预处理器（检测、去重、哈希）
 media_handler.py              # 主媒体处理器
 processors/                   # 媒体源处理器
    __init__.py
    base_processor.py         # 基础处理器
    emby_processor.py         # Emby处理器
    jellyfin_processor.py     # Jellyfin处理器
    plex_processor.py         # Plex处理器
    generic_processor.py      # 通用处理器
    processor_manager.py      # 处理器管理器
 enrichment/                   # 数据丰富模块
     __init__.py               # 数据丰富模块初始化
     base_provider.py          # 提供者基础接口
     enrichment_manager.py     # 数据丰富管理器（总入口）
     tmdb_provider.py          # TMDB 提供者
     tvdb_provider.py          # TVDB 提供者
     bgm_provider.py           # BGM.tv 图片提供者
`

## 功能说明

### 预处理
- data_processor.py: MediaDataProcessor 负责媒体数据的检测、去重、哈希计算等预处理功能

### 核心处理
- media_handler.py: MediaHandler 主要的媒体处理入口，协调各种处理器
- processors/: 各种媒体服务器的专用处理器（Emby、Jellyfin、Plex等）

### 数据丰富
- enrichment_manager.py: EnrichmentManager 数据丰富模块的总入口，统一管理所有提供者
- ase_provider.py: 定义了 MediaEnrichmentProvider 和 MediaImageProvider 基础接口
- 	mdb_provider.py: TMDBProvider 提供 TMDB API 的数据丰富和图片获取
- 	vdb_provider.py: TVDBProvider 提供 TVDB API 的数据丰富
- gm_provider.py: BGMTVImageProvider 提供 BGM.tv 的动漫图片获取

## 数据丰富架构

### 提供者类型

1. **数据丰富提供者** (MediaEnrichmentProvider):
   - 丰富媒体元数据（如剧集简介、评分、演员等）
   - 按优先级排序，优先级数字越小越优先

2. **图片提供者** (MediaImageProvider):
   - 获取媒体图片资源
   - 支持多种图片来源的降级机制

### 支持的提供者

| 提供者 | 类型 | 功能 | 优先级 |
|--------|------|------|--------|
| TMDB | 数据丰富 + 图片 | 剧集元数据、剧集截图、海报 | 1 |
| TVDB | 数据丰富 | 剧集元数据 | 2 |
| BGM.tv | 图片 | 动漫图片 | 3 |

### 降级机制

图片获取按以下优先级降级：

1. **TMDB 剧集截图** - 最相关，剧集特有的视觉内容
2. **Fanart.tv 海报** - 高质量官方海报
3. **Fanart.tv 横幅** - 备用海报资源
4. **TMDB 剧集海报** - 最后的备选方案
5. **BGM.tv 图片** - 动漫作品专用

### 扩展新提供者

要添加新的数据源，只需：

1. 实现 MediaEnrichmentProvider 或 MediaImageProvider 接口
2. 在 EnrichmentManager 中注册新提供者
3. 设置合适的优先级

`python
# 示例：添加新的图片提供者
from .enrichment import EnrichmentManager, MyImageProvider

manager = EnrichmentManager(config)
manager.add_image_provider(MyImageProvider())
`

## 职责分离

- **main.py**: Webhook接收、消息队列管理、消息发送
- **预处理**: 数据检测、去重、预处理
- **核心处理**: 媒体数据转换和标准化
- **数据丰富**: 多源元数据丰富和智能图片获取
