from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse

from common.codec import json_loads
from common.kafka import create_consumer, stop_safely
from common.logging import setup_logging
from common.settings import group_alert_service, topic_fraud_alerts

logger = logging.getLogger("alert_service")


def _db_path() -> Path:
    return Path(os.getenv("ALERT_DB_PATH", "storage/alerts.db")).resolve()


def _connect_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS alerts (
          alert_id TEXT PRIMARY KEY,
          transaction_id TEXT,
          detected_time TEXT,
          source TEXT,
          score REAL,
          model TEXT,
          payload_json TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_detected_time ON alerts(detected_time)")
    conn.commit()
    return conn


def _insert_alert(conn: sqlite3.Connection, alert: dict[str, Any], payload_json: str) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO alerts(alert_id, transaction_id, detected_time, source, score, model, payload_json)
        VALUES(?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(alert.get("alert_id")),
            str(alert.get("transaction_id")),
            str(alert.get("detected_time")),
            str(alert.get("source")),
            float(alert.get("score")) if alert.get("score") is not None else None,
            str(alert.get("model")) if alert.get("model") is not None else None,
            payload_json,
        ),
    )
    conn.commit()


async def _consumer_loop(app: FastAPI) -> None:
    consumer = await create_consumer(
        topic=topic_fraud_alerts(),
        group_id=group_alert_service(),
        client_id="alert-service",
    )
    app.state.consumer = consumer

    logger.info(
        "consumer_started",
        extra={
            "topic": topic_fraud_alerts(),
            "group_id": group_alert_service(),
            "db": str(app.state.db_path),
        },
    )

    try:
        async for msg in consumer:
            if app.state.stop_event.is_set():
                break

            try:
                payload = msg.value.decode("utf-8")
                alert = json_loads(msg.value)
                if not isinstance(alert, dict):
                    continue
            except Exception:
                logger.exception("bad_alert_message")
                continue

            try:
                await asyncio.to_thread(_insert_alert, app.state.db, alert, payload)
            except Exception:
                logger.exception("db_insert_failed")
                continue

            for q in list(app.state.subscribers):
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    continue

    finally:
        await stop_safely(consumer)


def create_app() -> FastAPI:
    setup_logging("alert_service")
    app = FastAPI(title="Alert Service", version="0.1.0")

    @app.on_event("startup")
    async def _startup() -> None:
        app.state.stop_event = asyncio.Event()
        app.state.db_path = _db_path()
        app.state.db = _connect_db(app.state.db_path)
        app.state.subscribers = set()
        app.state.consumer_task = asyncio.create_task(_consumer_loop(app))

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        app.state.stop_event.set()

        task = getattr(app.state, "consumer_task", None)
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        await stop_safely(getattr(app.state, "consumer", None))

        db = getattr(app.state, "db", None)
        if db is not None:
            db.close()

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "topic": topic_fraud_alerts(),
            "group_id": group_alert_service(),
            "db": str(_db_path()),
        }

    @app.get("/alerts")
    async def list_alerts(
        limit: int = Query(default=100, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        def _query() -> list[dict[str, Any]]:
            cur = app.state.db.execute(
                "SELECT alert_id, transaction_id, detected_time, source, score, model, payload_json "
                "FROM alerts ORDER BY detected_time DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = cur.fetchall()
            return [
                {
                    "alert_id": r[0],
                    "transaction_id": r[1],
                    "detected_time": r[2],
                    "source": r[3],
                    "score": r[4],
                    "model": r[5],
                    "payload": r[6],
                }
                for r in rows
            ]

        alerts = await asyncio.to_thread(_query)
        return {"items": alerts, "limit": limit, "offset": offset}

    @app.get("/alerts/stream")
    async def stream_alerts() -> StreamingResponse:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1000)
        app.state.subscribers.add(queue)

        async def gen() -> AsyncIterator[bytes]:
            try:
                yield b"event: ready\ndata: ok\n\n"
                while True:
                    try:
                        payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                        yield f"data: {payload}\n\n".encode("utf-8")
                    except asyncio.TimeoutError:
                        yield b": keep-alive\n\n"
            finally:
                app.state.subscribers.discard(queue)

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.get("/alerts/{alert_id}")
    async def get_alert(alert_id: str) -> dict[str, Any]:
        def _query_one() -> dict[str, Any] | None:
            cur = app.state.db.execute(
                "SELECT payload_json FROM alerts WHERE alert_id = ?",
                (alert_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return {"alert_id": alert_id, "payload": row[0]}

        result = await asyncio.to_thread(_query_one)
        if result is None:
            raise HTTPException(status_code=404, detail="Not found")
        return result

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8001"))
    uvicorn.run("services.alert_service.app:app", host=host, port=port, log_level="info")
