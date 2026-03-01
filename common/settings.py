from __future__ import annotations

import os


def kafka_bootstrap_servers() -> str:
    return os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")


def topic_transactions() -> str:
    return os.getenv("TOPIC_TRANSACTIONS", "transactions")


def topic_fraud_alerts() -> str:
    return os.getenv("TOPIC_FRAUD_ALERTS", "fraud_alerts")


def group_rule_engine() -> str:
    return os.getenv("GROUP_RULE_ENGINE", "rule-engine")


def group_ml_engine() -> str:
    return os.getenv("GROUP_ML_ENGINE", "ml-engine")


def group_alert_service() -> str:
    return os.getenv("GROUP_ALERT_SERVICE", "alert-service")
