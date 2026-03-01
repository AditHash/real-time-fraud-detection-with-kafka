# real-time-fraud-detection-with-kafka

## Phase 1 (Model training)

- Notebook: `notebooks/model_training.ipynb`
- Output model: `model/model.pkl`

## Phase 2 (Kafka + Zookeeper via Docker Compose)

Start:

```bash
docker compose up -d
```

Kafka bootstrap servers:

- From your host: `localhost:29092`
- From other containers in the compose network: `kafka:9092`

Create topics:

```bash
docker compose exec kafka kafka-topics --bootstrap-server kafka:9092 --create --if-not-exists --topic transactions --partitions 3 --replication-factor 1
docker compose exec kafka kafka-topics --bootstrap-server kafka:9092 --create --if-not-exists --topic fraud_alerts --partitions 3 --replication-factor 1
```

Stop:

```bash
docker compose down
```
