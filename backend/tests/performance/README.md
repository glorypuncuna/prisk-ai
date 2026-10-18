# Prisk AI Performance & Load Testing Guide

This directory contains the performance testing suite for **Prisk AI**, designed to validate throughput, concurrency, latency, and reliability against the project's Non-Functional Requirements (**PRD** & **TRD**).

---

## 1. Key Performance SLAs & Non-Functional Requirements (NFRs)

| Requirement ID | Target SLA / Metric | Scope / Endpoint | Technical Benchmark |
| :--- | :--- | :--- | :--- |
| **NFR-1.1** | **< 2.0s** Latency | `POST /api/v1/webhooks/meetstream` | Ingestion, PII masking, dialogue persistence |
| **NFR-1.2** | **< 3.0s** Load Time | `GET /api/v1/projects/{project_id}` | Dashboard & BigQuery historical pulse trends (up to 1,000 meetings) |
| **NFR-1.3** | **< 5 min** Completion | Async AI Summarization & Pulse | Vertex AI (`gemini-2.5-flash`) asynchronous job execution |
| **NFR-3.2** | **99.9%** Availability | All APIs under load | Maximum allowed server failure rate **< 0.1%** (5xx errors) |

---

## 2. Necessary Parameters Guide

When configuring and executing performance tests on Prisk AI, configure the following parameters based on the target environment:

### A. Workload & Traffic Parameters
| Parameter | Flag / Env | Recommended Local | Recommended Staging / Prod | Description |
| :--- | :--- | :--- | :--- | :--- |
| **Concurrency / Virtual Users** | `-c`, `--concurrency` | `10` – `25` | `50` – `200` | Number of simultaneous simulated users |
| **Ramp-Up / Spawn Rate** | `-r`, `--spawn-rate` | `2` users/sec | `5` – `10` users/sec | Rate at which new users are spawned |
| **Test Duration** | `-d`, `--duration` | `15s` – `30s` | `5m` – `15m` | Sustained benchmark duration |
| **Warmup Duration** | `-w`, `--warmup` | `2s` – `5s` | `30s` | Period to warm up caches and connections before measuring |
| **Think Time** | `--think-time-ms` | `20ms` – `50ms` | `500ms` – `2000ms` | Realistic simulated pause between user actions |

### B. SLA Threshold Parameters
| Parameter | Flag | Default | Description |
| :--- | :--- | :--- | :--- |
| **Dashboard SLA (NFR-1.2)** | `--sla-p95-dashboard` | `3000ms` | Maximum acceptable 95th-percentile response time |
| **Webhook SLA (NFR-1.1)** | `--sla-p95-webhook` | `2000ms` | Maximum acceptable 95th-percentile webhook ingestion latency |
| **Error Rate (NFR-3.2)** | `--max-error-rate` | `0.1%` | Maximum percentage of HTTP 5xx responses allowed |

### C. Cloud Run & Infrastructure Parameters
For deploying or sizing the backend on Google Cloud Run:
- **Container Concurrency:** `80` (FastAPI handles concurrent requests asynchronously per instance)
- **CPU & Memory:** `2 vCPU`, `2 GiB RAM`
- **Min Instances:** `1` (ensures zero cold-start latency for webhooks during business hours)
- **Max Instances:** `10` – `20` (allows horizontal auto-scaling under peak burst loads)
- **Database Connection Pools:** Max `50` concurrent connections for Cloud SQL / BigQuery client workers
- **Dashboard Cache TTL:** `60s` in-memory TTL cache for aggregated BigQuery pulse queries

---

## 3. How to Run the Performance Tests

### Option 1: Fast In-Process Benchmark (Zero Server Setup Required)
Uses FastAPI's native ASGI async transport with mocked database layers:
```bash
# Run with 15 concurrent users for 10 seconds:
backend/.venv/bin/python backend/tests/performance/run_perf_test.py --asgi -c 15 -d 10 -w 2

# Export report to JSON for CI/CD gates:
backend/.venv/bin/python backend/tests/performance/run_perf_test.py --asgi -c 20 -d 15 --output-json perf-report.json
```

### Option 2: Live Server Load Test
First, start the FastAPI server in one terminal:
```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Then, execute the benchmark against the live server:
```bash
backend/.venv/bin/python backend/tests/performance/run_perf_test.py --target-url http://localhost:8000 -c 30 -d 30
```

### Option 3: Distributed Load Testing with Locust
To run with Locust's interactive Web UI:
```bash
backend/.venv/bin/python -m pip install locust
locust -f backend/tests/performance/locustfile.py --host http://localhost:8000
# Open http://localhost:8089 in your browser
```

To run Locust in headless mode (e.g. inside a CI/CD pipeline):
```bash
locust -f backend/tests/performance/locustfile.py --host http://localhost:8000 \
       --headless -u 50 -r 5 --run-time 1m --stop-timeout 10
```
