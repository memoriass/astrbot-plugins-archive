"""日志适配器 - 将 AstrBot logger 适配为类似 nonebot 的接口"""

try:
    from astrbot.api import logger as astrbot_logger
except ImportError:
    import logging

    logging.basicConfig(level=logging.INFO)
    astrbot_logger = logging.getLogger("astrbot_mock")


class LoggerAdapter:
    """日志适配器类"""

    @staticmethod
    def info(message: str, *args, **kwargs):
        """信息日志"""
        astrbot_logger.info(message)

    @staticmethod
    def debug(message: str, *args, **kwargs):
        """调试日志"""
        astrbot_logger.debug(message)

    @staticmethod
    def trace(message: str, *args, **kwargs):
        """Trace日志 (映射为 debug)"""
        astrbot_logger.debug(message)

    @staticmethod
    def warning(message: str, *args, **kwargs):
        """警告日志"""
        astrbot_logger.warning(message)

    @staticmethod
    def error(message: str, *args, **kwargs):
        """错误日志"""
        astrbot_logger.error(message)

    @staticmethod
    def exception(message: str, *args, **kwargs):
        """异常日志"""
        astrbot_logger.error(message, exc_info=True)

    @staticmethod
    def success(message: str, *args, **kwargs):
        """成功日志"""
        astrbot_logger.info(f"✓ {message}")


# 创建全局 logger 实例
logger = LoggerAdapter()

__all__ = ["logger"]
