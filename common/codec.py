from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def json_dumps(obj: Any) -> bytes:
    return json.dumps(obj, separators=(",", ":"), default=str).encode("utf-8")


def json_loads(data: bytes) -> Any:
    return json.loads(data.decode("utf-8"))
