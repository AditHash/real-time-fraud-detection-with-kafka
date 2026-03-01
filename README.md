# Real-Time Fraud Detection with Kafka (Python + FastAPI)

Production-style, local-first fraud detection simulator:

- Kafka event streaming (Docker Compose)
- Rule-based screening + ML confirmation (scikit-learn model)
- Multiple independent services (FastAPI + Kafka consumers)
- Real-time dashboard (SSE) + polling fallback

## Features

- **Event-driven architecture**: publish transactions once, process them in independent consumers.
- **Two-stage detection**: rules generate *candidates*, ML confirms *alerts* (reduces false positives).
- **Real-time UI**: dashboard streams new alerts over SSE and falls back to polling.
- **Reproducible model training**: notebook exports `model/model.pkl` and `model/model_meta.json` (threshold + feature list).
- **Local persistence**: alert service stores alerts in SQLite (`storage/alerts.db`).

## Architecture

Kafka topics:

- `transactions`: all incoming transactions/events
- `rule_candidates`: transactions that matched one or more rules (screening stage)
- `fraud_alerts`: ML-confirmed fraud alerts (final stage)

Services (Docker Compose):

```
              ┌────────────────────┐
HTTP / UI ───▶│ transaction-api     │───▶ Kafka: transactions
              └────────────────────┘
                          │
                          ▼
              ┌────────────────────┐
              │ rule-engine         │───▶ Kafka: rule_candidates
              └────────────────────┘
                          │
                          ▼
              ┌────────────────────┐
              │ ml-engine           │───▶ Kafka: fraud_alerts
              └────────────────────┘
                          │
                          ▼
              ┌────────────────────┐
              │ alert-service       │───▶ SQLite: storage/alerts.db
              │  /alerts + SSE      │
              └────────────────────┘
                          │
                          ▼
              ┌────────────────────┐
              │ dashboard (FastAPI) │───▶ Browser UI (SSE + fallback polling)
              └────────────────────┘
```

Optional:

- `csv-producer` (demo profile): streams `data/creditcard.csv` into `transactions`

## Workflow (end-to-end)

1) A transaction is created via:
   - Dashboard “Send test transaction” (recommended), or
   - HTTP `POST /transactions`, or
   - `csv-producer` streaming a CSV dataset
2) `transaction-api` publishes an event to Kafka `transactions`
3) `rule-engine` consumes `transactions` and publishes a **candidate** to `rule_candidates` when rules match
4) `ml-engine` consumes `rule_candidates`, scores with `model/model.pkl`, and publishes a **confirmed** alert to `fraud_alerts` if score ≥ threshold (from `model/model_meta.json`)
5) `alert-service` consumes both `rule_candidates` and `fraud_alerts`, stores messages in SQLite, and exposes:
   - polling API `GET /alerts`
   - real-time stream `GET /alerts/stream` (SSE)
6) `dashboard` shows alerts live via SSE (with polling fallback)

## Quickstart (Docker Compose)

Prereqs:

- Docker Desktop (Windows/macOS) or Docker Engine (Linux)
- `docker compose` (Compose v2)

Bring up the stack:

```bash
docker compose up -d --build
```

Open:

- Dashboard: `http://localhost:8002`
- Transaction API health: `http://localhost:8000/health`
- Alert Service health: `http://localhost:8001/health`

Stop everything:

```bash
docker compose down -v
```

## Testing / Verifying Processing

### 1) Generate events from the dashboard

Open `http://localhost:8002` and click **Send** (High amount / Low V14).

### 2) Generate an event from CLI (optional)

Linux/macOS (bash):

```bash
curl -X POST http://localhost:8000/transactions \
  -H "Content-Type: application/json" \
  -d '{"features":{"Amount":5000,"V14":-10}}'
```

Windows (PowerShell):

```powershell
$body = @{ features = @{ Amount = 5000; V14 = -10 } } | ConvertTo-Json -Depth 5
Invoke-WebRequest -Method Post http://localhost:8000/transactions -ContentType "application/json" -Body $body
```

### 3) Inspect Kafka topics (optional)

```bash
docker compose exec kafka kafka-topics --bootstrap-server kafka:9092 --list
docker compose exec kafka kafka-console-consumer --bootstrap-server kafka:9092 --topic transactions --from-beginning --max-messages 1
docker compose exec kafka kafka-console-consumer --bootstrap-server kafka:9092 --topic rule_candidates --from-beginning --max-messages 1
docker compose exec kafka kafka-console-consumer --bootstrap-server kafka:9092 --topic fraud_alerts --from-beginning --max-messages 1
```

### 4) Stream alerts via SSE (optional)

Open `http://localhost:8001/alerts/stream` (browser) or use an SSE-capable client.

## Model Training (Phase 1)

Notebook:

- `notebooks/model_training.ipynb`

Artifacts:

- `model/model.pkl` (selected trained model)
- `model/model_meta.json` (selected threshold + numeric feature list)

Important:

- `data/` is intentionally not committed to git.
- The ML engine uses `selected_threshold` from `model/model_meta.json`.

## Configuration (env vars)

Kafka:

- `KAFKA_BOOTSTRAP_SERVERS` (default `kafka:9092` inside Compose)

Topics:

- `TOPIC_TRANSACTIONS` (default `transactions`)
- `TOPIC_RULE_CANDIDATES` (default `rule_candidates`)
- `TOPIC_FRAUD_ALERTS` (default `fraud_alerts`)

Rule engine:

- `RULE_AMOUNT_THRESHOLD` (default `2000`)
- `RULE_V14_LTE` (default `-8`)

ML engine:

- `MODEL_DIR` (default `model`)
- `ML_THRESHOLD` (fallback if meta missing; default `0.5`)

Alert service:

- `ALERT_DB_PATH` (default `storage/alerts.db`)

## Concepts Covered

- Kafka topics, partitions, and consumer groups
- Event-driven microservices with independent consumers
- Two-stage detection pipelines (screen → confirm)
- Model artifact export + inference using scikit-learn
- Real-time streaming UI with Server-Sent Events (SSE)
- Local persistence with SQLite
- Docker Compose orchestration and service wiring

## Repo Structure (high level)

- `docker-compose.yml`: Kafka + services stack
- `notebooks/model_training.ipynb`: Phase 1 model training
- `model/`: exported model + metadata
- `services/transaction_api/`: FastAPI publish endpoint
- `consumers/rule_engine/`: rules → candidates
- `consumers/ml_engine/`: candidates → confirmed alerts
- `services/alert_service/`: Kafka consumer + SQLite + APIs (`/alerts`, `/alerts/stream`)
- `services/dashboard/`: UI (SSE + fallback polling) + proxy endpoints
- `producer/`: optional CSV streamer (`--profile demo`)

## Special Thanks (Datasets)

Kaggle credit card fraud datasets used for experimentation/training:

- https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud/data
- https://www.kaggle.com/datasets/nelgiriyewithana/credit-card-fraud-detection-dataset-2023/data
