from __future__ import annotations

import asyncio
from typing import Optional

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from common.settings import kafka_bootstrap_servers


async def create_producer(*, client_id: str) -> AIOKafkaProducer:
    producer = AIOKafkaProducer(bootstrap_servers=kafka_bootstrap_servers(), client_id=client_id)
    await producer.start()
    return producer


async def create_consumer(
    *,
    topic: str,
    group_id: str,
    client_id: str,
    auto_offset_reset: str = "earliest",
    enable_auto_commit: bool = True,
    max_poll_records: int = 500,
) -> AIOKafkaConsumer:
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=kafka_bootstrap_servers(),
        group_id=group_id,
        client_id=client_id,
        auto_offset_reset=auto_offset_reset,
        enable_auto_commit=enable_auto_commit,
        max_poll_records=max_poll_records,
        value_deserializer=None,
        key_deserializer=None,
    )
    await consumer.start()
    return consumer


async def stop_safely(obj: Optional[object]) -> None:
    if obj is None:
        return
    stop = getattr(obj, "stop", None)
    if stop is None:
        return
    await stop()


async def sleep_with_cancel(seconds: float) -> None:
    try:
        await asyncio.sleep(seconds)
    except asyncio.CancelledError:
        raise
