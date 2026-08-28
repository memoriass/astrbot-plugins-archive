"""AstrBot logger 适配器。"""

try:
    from astrbot.api import logger as astrbot_logger
except ImportError:
    import logging

    logging.basicConfig(level=logging.INFO)
    astrbot_logger = logging.getLogger("astrbot_mock")


class LoggerAdapter:
    @staticmethod
    def info(message: str, *args, **kwargs):
        astrbot_logger.info(message)

    @staticmethod
    def debug(message: str, *args, **kwargs):
        astrbot_logger.debug(message)

    @staticmethod
    def trace(message: str, *args, **kwargs):
        astrbot_logger.debug(message)

    @staticmethod
    def warning(message: str, *args, **kwargs):
        astrbot_logger.warning(message)

    @staticmethod
    def error(message: str, *args, **kwargs):
        astrbot_logger.error(message)

    @staticmethod
    def exception(message: str, *args, **kwargs):
        astrbot_logger.error(message, exc_info=True)

    @staticmethod
    def success(message: str, *args, **kwargs):
        astrbot_logger.info(f"✓ {message}")


logger = LoggerAdapter()

__all__ = ["logger"]
