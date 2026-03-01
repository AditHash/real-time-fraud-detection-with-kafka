from __future__ import annotations

import logging
import os

from pythonjsonlogger import jsonlogger


def setup_logging(service_name: str) -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()

    root = logging.getLogger()
    root.setLevel(level)

    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s %(service)s"
    )
    handler.setFormatter(formatter)
    root.addHandler(handler)

    logging.LoggerAdapter(logging.getLogger(__name__), {"service": service_name})
