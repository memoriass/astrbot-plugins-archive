from __future__ import annotations

from pathlib import Path

PLUGIN_NAME = "astrbot_plugin_ani_rss"


def plugin_data_dir(plugin_name: str = PLUGIN_NAME) -> Path:
    try:
        from astrbot.api.star import StarTools

        return StarTools.get_data_dir(plugin_name)
    except Exception:
        pass

    try:
        from astrbot.core.utils.astrbot_path import get_astrbot_data_path

        return Path(get_astrbot_data_path()) / "plugin_data" / plugin_name
    except Exception:
        pass

    try:
        from astrbot.core.config.astrbot_config import ASTRBOT_CONFIG_PATH

        config_path = Path(ASTRBOT_CONFIG_PATH).resolve()
        data_path = config_path.parent
        if data_path.name == "config":
            data_path = data_path.parent
        return data_path / "plugin_data" / plugin_name
    except Exception:
        return Path.cwd() / "data" / "plugin_data" / plugin_name
