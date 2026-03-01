from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from joblib import load

from aiokafka import AIOKafkaProducer

from common.codec import json_dumps, json_loads, utc_now_iso
from common.kafka import create_consumer, create_producer, stop_safely
from common.logging import setup_logging
from common.settings import group_ml_engine, topic_fraud_alerts, topic_rule_candidates


logger = logging.getLogger("ml_engine")


def load_meta(model_dir: Path) -> dict[str, Any]:
    meta_path = model_dir / "model_meta.json"
    if not meta_path.exists():
        return {}
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _coerce_row(features: dict[str, Any], cols: list[str]) -> pd.DataFrame:
    row: dict[str, float] = {}
    for c in cols:
        v = features.get(c, 0.0)
        try:
            row[c] = float(v)
        except Exception:
            row[c] = 0.0
    return pd.DataFrame([row], columns=cols)


def predict_proba(model: Any, X: pd.DataFrame) -> float:
    if hasattr(model, "predict_proba"):
        p = model.predict_proba(X)
        return float(p[0, 1])
    pred = model.predict(X)
    return float(pred[0])


async def send_alert(
    producer: AIOKafkaProducer,
    *,
    event: dict[str, Any],
    proba: float,
    threshold: float,
    model_name: str,
    rule_reasons: list[str] | None = None,
) -> None:
    transaction_id = str(event.get("transaction_id") or "")
    alert = {
        "alert_id": str(uuid.uuid4()),
        "transaction_id": transaction_id,
        "event_time": event.get("event_time"),
        "detected_time": utc_now_iso(),
        "source": "ml_engine",
        "model": model_name,
        "score": proba,
        "threshold": threshold,
        "rule_reasons": rule_reasons or [],
        "transaction": event,
    }
    topic = topic_fraud_alerts()
    await producer.send_and_wait(
        topic,
        key=transaction_id.encode("utf-8") if transaction_id else None,
        value=json_dumps(alert),
    )


async def run() -> None:
    setup_logging("ml_engine")

    model_dir = Path(os.getenv("MODEL_DIR", "model")).resolve()
    model_path = model_dir / "model.pkl"
    if not model_path.exists():
        raise FileNotFoundError(f"Missing model artifact: {model_path}")

    model = load(model_path)
    meta = load_meta(model_dir)

    numeric_features = meta.get("numeric_features") or meta.get("numeric_features".upper()) or []
    if not isinstance(numeric_features, list) or not numeric_features:
        raise ValueError("model_meta.json missing 'numeric_features' list; re-run Phase 1 notebook export.")

    threshold = float(meta.get("selected_threshold", os.getenv("ML_THRESHOLD", "0.5")))
    model_name = str(meta.get("selected_model", "model"))

    consumer = await create_consumer(
        topic=topic_rule_candidates(),
        group_id=group_ml_engine(),
        client_id="ml-engine",
    )
    producer = await create_producer(client_id="ml-engine")

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
            "topic_in": topic_rule_candidates(),
            "topic_out": topic_fraud_alerts(),
            "group_id": group_ml_engine(),
            "model_path": str(model_path),
            "model_name": model_name,
            "threshold": threshold,
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

            base_event = event.get("transaction") if isinstance(event.get("transaction"), dict) else event
            rule_reasons = event.get("reasons") if isinstance(event.get("reasons"), list) else []

            features = base_event.get("features") or {}
            if not isinstance(features, dict):
                continue

            X = _coerce_row(features, numeric_features)
            proba = predict_proba(model, X)

            if proba >= threshold:
                await send_alert(
                    producer,
                    event=base_event,
                    proba=proba,
                    threshold=threshold,
                    model_name=model_name,
                    rule_reasons=rule_reasons,
                )
                logger.info(
                    "alert",
                    extra={
                        "transaction_id": base_event.get("transaction_id"),
                        "score": proba,
                        "threshold": threshold,
                        "rule_reasons": rule_reasons,
                    },
                )

            if stop_event.is_set():
                break
    finally:
        await stop_safely(consumer)
        await stop_safely(producer)


if __name__ == "__main__":
    asyncio.run(run())
