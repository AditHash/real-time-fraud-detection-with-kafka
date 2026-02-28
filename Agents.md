# AGENTS.md

## Project: Real-Time Fraud Detection Simulator (Kafka + ML)

This document defines how coding agents (including Codex-style agents) should operate within this repository.

---

## 🎯 Project Goal

Build a production-style Real-Time Fraud Detection System using:

* Kaggle credit card fraud datasets
* ML model trained in Jupyter Notebook
* Kafka-based streaming architecture
* Multiple independent consumers

The development will happen in phases.

---

# 🚦 Development Phases

## Phase 1 — Data Exploration & Model Training (Notebook First)

This phase MUST be completed before building Kafka services.

### Location

notebooks/model_training.ipynb

### Objectives

1. Load Kaggle dataset from `/data/`
2. Perform exploratory data analysis (EDA)
3. Handle class imbalance
4. Train baseline ML model
5. Evaluate metrics
6. Export trained model to `/model/model.pkl`

### Constraints

* Use Python
* Use pandas, numpy, scikit-learn
* No deep learning initially
* Keep model simple (Logistic Regression or RandomForest)
* Focus on interpretability

### Required Outputs

* model/model.pkl
* metrics summary (precision, recall, F1, ROC-AUC)
* explanation of class imbalance handling

Notebook must be clean and structured:

1. Imports
2. Data loading
3. EDA
4. Preprocessing
5. Train/test split
6. Model training
7. Evaluation
8. Model export

---

## Phase 2 — Kafka Infrastructure Setup

After model.pkl is created.

### Required Services

* Kafka
* Zookeeper

Must use Docker Compose.

No cloud services at this stage.

---

## Phase 3 — Streaming Architecture

### Topic Design

* transactions
* fraud_alerts
* dead_letter (optional advanced)

### Services

1. Producer

   * Reads dataset
   * Streams events to `transactions`

2. Rule Engine Consumer

   * Applies rule-based fraud detection
   * Publishes suspicious transactions to `fraud_alerts`

3. ML Engine Consumer

   * Loads `model.pkl`
   * Predicts fraud probability
   * Publishes high-risk events to `fraud_alerts`

4. Storage Service

   * Persists transactions

5. Alert Service

   * Consumes `fraud_alerts`
   * Logs and stores alerts

Each service must be independently runnable.

---

# 📂 Project Structure

real-time-fraud-detection-kafka/
│
├── data/                  # Not committed to Git
├── notebooks/
│   └── model_training.ipynb
├── producer/
├── consumers/
├── model/
│   └── model.pkl
├── docker-compose.yml
├── requirements.txt
└── AGENTS.md

---

# 🧠 Engineering Principles

1. Do NOT write production logic inside notebooks.
2. Notebooks are only for experimentation and model training.
3. Services must be modular and cleanly separated.
4. Avoid hardcoded paths.
5. Use environment variables where appropriate.
6. Code must be readable and production-style.

---

# 📏 Coding Standards

* Python 3.10+
* Type hints encouraged
* Structured logging preferred over print
* No global mutable state
* Handle exceptions explicitly

---

# 🔁 Iteration Strategy

Agents must:

1. Complete Phase 1 fully.
2. Confirm `model.pkl` exists.
3. Then proceed to Kafka implementation.
4. Avoid skipping phases.

---

# ❌ What NOT To Do

* Do not mix notebook code with streaming services.
* Do not push datasets to GitHub.
* Do not overcomplicate ML in first iteration.
* Do not introduce distributed training.

---

# 🏁 Definition of Phase 1 Completion

Phase 1 is complete when:

* Model achieves reasonable recall on fraud class
* model.pkl is exported
* Notebook is clean and reproducible

Only then move to Kafka.

---

This document guides AI agents and contributors to build the system incrementally and professionally.
