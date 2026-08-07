"""Logging utilities for SchedFlow.

Provides structured logging via structlog with default configuration
and helper functions for obtaining logger instances.
"""

import logging
import os

import structlog

from schedflow.configs.settings import settings

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.DEBUG))

# Suppress PyMongo heartbeat logs that flood the console every ~10 seconds
logging.getLogger("pymongo").setLevel(logging.WARNING)


if not structlog.is_configured():
    structlog.stdlib.recreate_defaults()


def get_logger(name: str):
    """
    Get a structlog logger instance with the given name.

    :param name: the name of the logger
    :return: a structlog logger instance
    """
    return structlog.get_logger(name)


if __name__ == '__main__':
    logger = structlog.get_logger("schedflow.test")
    logger1 = structlog.get_logger("aaa2")
    logger.info("test info")
    logger1.debug("test debug")
    logger1.warning("test warning")
    logger.error("test error")
