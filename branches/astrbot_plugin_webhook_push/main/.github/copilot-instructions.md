# AI Coding Instructions for AstrBot Media Webhook Plugin

## Overview
This is a Python plugin for AstrBot that receives webhooks from media servers (Emby, Jellyfin, Plex) and sends formatted notifications to chat groups. It supports multiple bot adapters and enriches episode data with TMDB.

## Architecture
- **main.py**: Plugin entry point, webhook server (aiohttp), message queue, batch processing, duplicate detection via hash.
- **media_handler.py**: Orchestrates media processing and TMDB enrichment.
- **processors/**: Handles different media servers (Emby, Jellyfin, Plex, Generic) via BaseMediaProcessor interface.
- **adapters/**: Sends messages via different bot platforms (aiocqhttp, llonebot, napcat) using AdapterFactory.
- **tmdb_enricher.py**: Fetches episode details and images from TMDB API.

## Key Patterns
- **Processor Pattern**: Each media server has a processor inheriting from BaseMediaProcessor (can_handle, convert_to_standard).
- **Adapter Pattern**: Bot platforms use adapters inheriting from BaseAdapter for merge-forward messaging.
- **Factory Pattern**: AdapterFactory creates adapters based on platform name.
- **Async Queue Processing**: Batches messages every 300s, sends individually if <3 messages, merge-forward if >=3.
- **Duplicate Detection**: Hashes requests excluding images/timestamps, caches for 300s.

## Conventions
- Use `astrbot.api.logger` for logging.
- Config via AstrBot's config dict (see _conf_schema.json).
- Message components from `astrbot.api.message_components` (Plain, Image.fromURL).
- Standard media data dict: item_type, series_name, item_name, season_number, episode_number, year, overview, runtime, image_url, source_data.
- HTML unescape and clean text in processors.
- Runtime conversion: runtime_ticks // 600000000 for minutes.

## Workflows
- **Install**: `pip install -r requirements.txt` (only aiohttp).
- **Debug**: Check AstrBot logs; use `/webhook status` command.
- **Add Processor**: Inherit BaseMediaProcessor, implement can_handle (check headers/data), convert_to_standard (map to standard dict).
- **Add Adapter**: Inherit BaseAdapter, implement send_forward_messages and build_forward_node for platform-specific merge-forward.
- **TMDB Enrichment**: Only for Episodes; searches by series name, enriches overview/image if TMDB key provided.

## Examples
- **Webhook URL**: `http://bot-server:60071/media-webhook`
- **Message Format**: "🤖 📺 新剧集更新 [Jellyfin]\n剧集名称: Attack on Titan\n集号: S04E28\n剧情简介: ...\n时长: 24分钟\n✨ 数据来源: TMDB"
- **Config**: group_id, webhook_port=60071, tmdb_api_key, platform_name="auto"