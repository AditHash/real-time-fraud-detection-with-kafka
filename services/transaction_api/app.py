from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from aiokafka import AIOKafkaProducer

from common.codec import json_dumps, utc_now_iso
from common.kafka import create_producer, stop_safely
from common.logging import setup_logging
from common.settings import kafka_bootstrap_servers, topic_transactions


logger = logging.getLogger("transaction_api")


class TransactionIn(BaseModel):
    transaction_id: str | None = Field(
        default=None, description="Optional transaction id; generated if omitted."
    )
    features: dict[str, Any] = Field(
        default_factory=dict, description="Transaction feature payload (JSON)."
    )
    event_time: str | None = Field(
        default=None, description="Optional ISO timestamp; defaults to now (UTC)."
    )


def create_app() -> FastAPI:
    setup_logging("transaction_api")
    app = FastAPI(title="Transaction API", version="0.1.0")

    @app.on_event("startup")
    async def _startup() -> None:
        producer = await create_producer(client_id="transaction-api")
        app.state.producer = producer
        logger.info(
            "startup",
            extra={
                "bootstrap_servers": kafka_bootstrap_servers(),
                "topic": topic_transactions(),
            },
        )

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await stop_safely(getattr(app.state, "producer", None))

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/transactions")
    async def publish_transaction(body: TransactionIn) -> dict[str, Any]:
        producer: AIOKafkaProducer | None = getattr(app.state, "producer", None)
        if producer is None:
            raise HTTPException(status_code=503, detail="Kafka producer not ready")

        transaction_id = body.transaction_id or str(uuid.uuid4())
        event = {
            "transaction_id": transaction_id,
            "event_time": body.event_time or utc_now_iso(),
            "features": body.features,
        }

        topic = topic_transactions()
        await producer.send_and_wait(
            topic,
            key=transaction_id.encode("utf-8"),
            value=json_dumps(event),
        )

        logger.info("published", extra={"topic": topic, "transaction_id": transaction_id})
        return {"status": "published", "transaction_id": transaction_id, "topic": topic}

    return app


app = create_app()


def _uvicorn_app() -> str:
    return "services.transaction_api.app:app"


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(_uvicorn_app(), host=host, port=port, log_level="info")
