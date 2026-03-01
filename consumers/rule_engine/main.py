from __future__ import annotations

import asyncio
import logging
import os
import signal
import uuid
from typing import Any

from aiokafka import AIOKafkaProducer

from common.codec import json_dumps, json_loads, utc_now_iso
from common.kafka import create_consumer, create_producer, stop_safely
from common.logging import setup_logging
from common.settings import group_rule_engine, topic_fraud_alerts, topic_transactions


logger = logging.getLogger("rule_engine")


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def evaluate_rules(event: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    features = event.get("features") or {}
    if not isinstance(features, dict):
        return ["features_not_a_dict"]

    amount_threshold = float(os.getenv("RULE_AMOUNT_THRESHOLD", "2000"))
    amount = _as_float(features.get("Amount"))
    if amount is not None and amount >= amount_threshold:
        reasons.append(f"amount_gte_{amount_threshold}")

    v14_threshold = float(os.getenv("RULE_V14_LTE", "-8"))
    v14 = _as_float(features.get("V14"))
    if v14 is not None and v14 <= v14_threshold:
        reasons.append(f"v14_lte_{v14_threshold}")

    return reasons


async def send_alert(producer: AIOKafkaProducer, event: dict[str, Any], reasons: list[str]) -> None:
    transaction_id = str(event.get("transaction_id") or "")
    alert = {
        "alert_id": str(uuid.uuid4()),
        "transaction_id": transaction_id,
        "event_time": event.get("event_time"),
        "detected_time": utc_now_iso(),
        "source": "rule_engine",
        "reasons": reasons,
        "transaction": event,
    }
    topic = topic_fraud_alerts()
    await producer.send_and_wait(
        topic,
        key=transaction_id.encode("utf-8") if transaction_id else None,
        value=json_dumps(alert),
    )


async def run() -> None:
    setup_logging("rule_engine")

    consumer = await create_consumer(
        topic=topic_transactions(),
        group_id=group_rule_engine(),
        client_id="rule-engine",
    )
    producer = await create_producer(client_id="rule-engine")

    stop_event = asyncio.Event()

    def _stop(*_: object) -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_a: _stop())

    logger.info(
        "started",
        extra={
            "topic_in": topic_transactions(),
            "topic_out": topic_fraud_alerts(),
            "group_id": group_rule_engine(),
        },
    )

    try:
        async for msg in consumer:
            if stop_event.is_set():
                break

            try:
                event = json_loads(msg.value)
                if not isinstance(event, dict):
                    continue
            except Exception:
                logger.exception("bad_message", extra={"topic": msg.topic, "partition": msg.partition})
                continue

            reasons = evaluate_rules(event)
            if reasons:
                await send_alert(producer, event, reasons)
                logger.info(
                    "alert",
                    extra={
                        "transaction_id": event.get("transaction_id"),
                        "reasons": reasons,
                    },
                )

            if stop_event.is_set():
                break
    finally:
        await stop_safely(consumer)
        await stop_safely(producer)


if __name__ == "__main__":
    asyncio.run(run())
