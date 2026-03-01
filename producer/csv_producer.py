from __future__ import annotations

import asyncio
import csv
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from common.codec import json_dumps, utc_now_iso
from common.kafka import create_producer, stop_safely
from common.logging import setup_logging
from common.settings import topic_transactions

logger = logging.getLogger("csv_producer")


def _coerce_value(v: str) -> Any:
    if v == "":
        return None
    try:
        if "." in v or "e" in v.lower():
            return float(v)
        return int(v)
    except Exception:
        return v


async def run() -> None:
    setup_logging("csv_producer")

    data_path = Path(os.getenv("DATA_PATH", "data/creditcard.csv")).resolve()
    if not data_path.exists():
        raise FileNotFoundError(f"CSV not found: {data_path}")

    sleep_ms = int(os.getenv("PRODUCER_SLEEP_MS", "10"))
    max_messages = int(os.getenv("MAX_MESSAGES", "0"))  # 0 = no limit

    producer = await create_producer(client_id="csv-producer")
    sent = 0

    label_keys = ("Class", "class", "isFraud", "is_fraud", "fraud", "target", "label")

    try:
        with data_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row_idx, row in enumerate(reader, start=1):
                features = {k: _coerce_value(v) for k, v in row.items() if k is not None}

                label = None
                for key in label_keys:
                    if key in features:
                        label = features.pop(key)
                        break

                transaction_id = str(uuid.uuid4())
                event = {
                    "transaction_id": transaction_id,
                    "event_time": utc_now_iso(),
                    "row_idx": row_idx,
                    "label": label,
                    "features": features,
                }

                await producer.send_and_wait(
                    topic_transactions(),
                    key=transaction_id.encode("utf-8"),
                    value=json_dumps(event),
                )

                sent += 1
                if sent % 1000 == 0:
                    logger.info("sent", extra={"count": sent})

                if max_messages and sent >= max_messages:
                    break

                if sleep_ms > 0:
                    await asyncio.sleep(sleep_ms / 1000.0)

    finally:
        await stop_safely(producer)

    logger.info("done", extra={"sent": sent, "csv": str(data_path)})


if __name__ == "__main__":
    asyncio.run(run())
