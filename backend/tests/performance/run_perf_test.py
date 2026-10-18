#!/usr/bin/env python3
"""Prisk AI - Enterprise Performance & Load Testing Suite
==========================================================
Executes concurrent asynchronous load tests against Prisk AI endpoints
and validates response times against PRD/TRD Non-Functional Requirements (NFRs):

  - NFR-1.1: Webhook ingestion / real-time processing latency (< 2.0s)
  - NFR-1.2: Dashboard and historical analytics query latency (< 3.0s for 1000+ meetings)
  - NFR-3.2: System uptime & availability (< 0.1% 5xx server errors under load)

Supports both:
  1. Live HTTP/HTTPS endpoints (e.g. Cloud Run, local uvicorn: http://localhost:8000)
  2. Direct In-Process ASGI (zero external server required, uses FastAPI ASGI transport)

Usage:
  # In-process ASGI test (quick local verification):
  python backend/tests/performance/run_perf_test.py --asgi --concurrency 15 --duration 10

  # Live server load test:
  python backend/tests/performance/run_perf_test.py --target-url http://localhost:8000 -c 20 -d 30
"""

import argparse
import asyncio
import json
import math
import os
from pathlib import Path
import random
import sys
import time
from typing import Any, Callable, Coroutine

# Ensure backend directory is in python path
BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import httpx


# -----------------------------------------------------------------------------
# Configuration & Benchmark Parameters
# -----------------------------------------------------------------------------
DEFAULT_PROJECT_ID = "proj-alpha"
DEFAULT_MEETING_ID = "mtg-q3-001"

# Realistic Bearer Tokens using Mock auth format
MOCK_ADMIN_TOKEN = f"mock:{json.dumps({'uid': 'uid_admin_perf', 'email': 'admin@enterprise.com', 'role': 'ADMIN', 'assigned_project_ids': [DEFAULT_PROJECT_ID]})}"
MOCK_MANAGER_TOKEN = f"mock:{json.dumps({'uid': 'uid_manager_perf', 'email': 'mgr@enterprise.com', 'role': 'MANAGER', 'assigned_project_ids': [DEFAULT_PROJECT_ID]})}"
MOCK_ADJUDICATOR_TOKEN = f"mock:{json.dumps({'uid': 'uid_adj_perf', 'email': 'adj@enterprise.com', 'role': 'ADJUDICATOR', 'assigned_project_ids': [DEFAULT_PROJECT_ID]})}"


class MetricCollector:
    """Thread-safe statistics collector for latency measurements and status codes."""

    def __init__(self, name: str):
        self.name = name
        self.latencies_ms: list[float] = []
        self.status_codes: dict[int, int] = {}
        self.errors: int = 0
        self.start_time: float = 0.0
        self.end_time: float = 0.0

    def record(self, latency_ms: float, status_code: int) -> None:
        self.latencies_ms.append(latency_ms)
        self.status_codes[status_code] = self.status_codes.get(status_code, 0) + 1
        if status_code >= 500:
            self.errors += 1

    def record_error(self) -> None:
        self.errors += 1

    def summary(self) -> dict[str, Any]:
        count = len(self.latencies_ms)
        duration = max(0.001, self.end_time - self.start_time)
        rps = count / duration if count > 0 else 0.0

        if count == 0:
            return {
                "name": self.name,
                "count": 0,
                "rps": 0.0,
                "errors": self.errors,
                "error_rate_pct": 100.0 if self.errors > 0 else 0.0,
                "min_ms": 0.0,
                "avg_ms": 0.0,
                "p50_ms": 0.0,
                "p90_ms": 0.0,
                "p95_ms": 0.0,
                "p99_ms": 0.0,
                "max_ms": 0.0,
            }

        sorted_lat = sorted(self.latencies_ms)
        p50 = sorted_lat[int(0.50 * (count - 1))]
        p90 = sorted_lat[int(0.90 * (count - 1))]
        p95 = sorted_lat[int(0.95 * (count - 1))]
        p99 = sorted_lat[int(0.99 * (count - 1))]
        avg = sum(sorted_lat) / count
        error_rate_pct = (self.errors / (count + self.errors)) * 100.0

        return {
            "name": self.name,
            "count": count,
            "rps": round(rps, 2),
            "errors": self.errors,
            "error_rate_pct": round(error_rate_pct, 2),
            "status_codes": self.status_codes,
            "min_ms": round(sorted_lat[0], 2),
            "avg_ms": round(avg, 2),
            "p50_ms": round(p50, 2),
            "p90_ms": round(p90, 2),
            "p95_ms": round(p95, 2),
            "p99_ms": round(p99, 2),
            "max_ms": round(sorted_lat[-1], 2),
        }


# -----------------------------------------------------------------------------
# Workload Scenarios
# -----------------------------------------------------------------------------
async def scenario_dashboard_analytics(client: httpx.AsyncClient, collector: MetricCollector) -> None:
    """NFR-1.2: Project dashboard & aggregated risk/pulse metrics."""
    headers = {"Authorization": f"Bearer {MOCK_MANAGER_TOKEN}"}
    t0 = time.perf_counter()
    try:
        resp = await client.get(f"/api/v1/projects/{DEFAULT_PROJECT_ID}", headers=headers)
        latency = (time.perf_counter() - t0) * 1000
        collector.record(latency, resp.status_code)
    except Exception:
        collector.record_error()


async def scenario_meetings_list(client: httpx.AsyncClient, collector: MetricCollector) -> None:
    """Meeting records query under manager/stakeholder role."""
    headers = {"Authorization": f"Bearer {MOCK_MANAGER_TOKEN}"}
    t0 = time.perf_counter()
    try:
        resp = await client.get(f"/api/v1/projects/{DEFAULT_PROJECT_ID}/meetings", headers=headers)
        latency = (time.perf_counter() - t0) * 1000
        collector.record(latency, resp.status_code)
    except Exception:
        collector.record_error()


async def scenario_risk_register(client: httpx.AsyncClient, collector: MetricCollector) -> None:
    """Risk register querying and filtering."""
    headers = {"Authorization": f"Bearer {MOCK_MANAGER_TOKEN}"}
    t0 = time.perf_counter()
    try:
        resp = await client.get(f"/api/v1/projects/{DEFAULT_PROJECT_ID}/risks", headers=headers)
        latency = (time.perf_counter() - t0) * 1000
        collector.record(latency, resp.status_code)
    except Exception:
        collector.record_error()


async def scenario_xai_diagnostics(client: httpx.AsyncClient, collector: MetricCollector) -> None:
    """Adjudicator inspecting meeting dialogue blocks & XAI token attributions."""
    headers = {"Authorization": f"Bearer {MOCK_ADJUDICATOR_TOKEN}"}
    t0 = time.perf_counter()
    try:
        resp = await client.get(f"/api/v1/meetings/{DEFAULT_MEETING_ID}/xai-diagnostics", headers=headers)
        latency = (time.perf_counter() - t0) * 1000
        collector.record(latency, resp.status_code)
    except Exception:
        collector.record_error()


async def scenario_webhook_ingest(client: httpx.AsyncClient, collector: MetricCollector) -> None:
    """NFR-1.1: Webhook ingestion of meetstream.ai transcript payload."""
    payload = {
        "event_type": "transcript.completed",
        "meeting_id": f"mtg-perf-{random.randint(1000, 999999)}",
        "project_id": DEFAULT_PROJECT_ID,
        "company_name": "Acme Global",
        "title": "Performance Test Meeting Ingest",
        "dialogue_blocks": [
            {
                "speaker_name": "Lead Architect",
                "speaker_account_id": "spk-01",
                "text": "The distributed ledger reconciliation is on schedule, but cross-region latency is increasing.",
                "start_time": "00:01:10",
                "end_time": "00:01:25",
            },
            {
                "speaker_name": "Compliance Officer",
                "speaker_account_id": "spk-02",
                "text": "We need to ensure SOC2 Type II audit logging is immutable and encrypted before production go-live.",
                "start_time": "00:01:26",
                "end_time": "00:01:40",
            },
        ],
    }
    t0 = time.perf_counter()
    try:
        resp = await client.post("/api/v1/webhooks/meetstream", json=payload)
        latency = (time.perf_counter() - t0) * 1000
        collector.record(latency, resp.status_code)
    except Exception:
        collector.record_error()


# -----------------------------------------------------------------------------
# Worker Loop
# -----------------------------------------------------------------------------
async def worker_loop(
    worker_id: int,
    client: httpx.AsyncClient,
    scenarios: list[tuple[Callable[..., Coroutine[Any, Any, None]], MetricCollector, int]],
    stop_event: asyncio.Event,
    think_time_ms: float = 50.0,
) -> None:
    """Simulates a concurrent user continuously issuing requests across weighted scenarios."""
    weights = [s[2] for s in scenarios]
    while not stop_event.is_set():
        # Weighted random choice of scenario
        choice = random.choices(scenarios, weights=weights, k=1)[0]
        func, collector, _ = choice
        await func(client, collector)
        if think_time_ms > 0:
            await asyncio.sleep(think_time_ms / 1000.0)


# -----------------------------------------------------------------------------
# Main Test Orchestrator
# -----------------------------------------------------------------------------
async def run_performance_test(
    base_url: str,
    concurrency: int,
    duration_sec: int,
    warmup_sec: int,
    think_time_ms: float,
    use_asgi: bool,
    sla_p95_dashboard_ms: float,
    sla_p95_webhook_ms: float,
    max_error_rate_pct: float,
    output_json: str | None = None,
) -> int:
    """Executes the load test, gathers metrics, checks SLAs, and reports results."""
    print("=" * 80)
    print("  PRISk AI ENTERPRISE PERFORMANCE & LOAD TEST")
    print("=" * 80)
    print(f"Target Mode:      {'In-Process ASGI' if use_asgi else base_url}")
    print(f"Concurrency:      {concurrency} virtual concurrent users")
    print(f"Test Duration:    {duration_sec}s (Warmup: {warmup_sec}s)")
    print(f"Think Time:       {think_time_ms}ms between requests")
    print("-" * 80)
    print("SLA Thresholds (PRD / TRD Standards):")
    print(f"  - NFR-1.1 Webhook Ingest Latency:   p95 < {sla_p95_webhook_ms:.0f} ms")
    print(f"  - NFR-1.2 Dashboard Query Latency:  p95 < {sla_p95_dashboard_ms:.0f} ms")
    print(f"  - NFR-3.2 Reliability / Uptime:     Error Rate < {max_error_rate_pct:.2f}%")
    print("=" * 80)

    # Initialize in-memory mock backend state if testing in-process ASGI
    if use_asgi:
        os.environ["USE_IN_MEMORY_FIRESTORE"] = "true"
        os.environ["USE_MOCK_FIREBASE_AUTH"] = "true"
        from app.core.config import get_settings
        from app.core.database import _in_memory_db
        from app.main import app, seed_development_data

        settings = get_settings()
        settings.use_in_memory_firestore = True
        settings.use_mock_firebase_auth = True
        _in_memory_db._collections.clear()
        seed_development_data()
        transport = httpx.ASGITransport(app=app)
        client = httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=30.0)
    else:
        client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=30.0)

    # Setup Collectors
    col_dashboard = MetricCollector("GET /projects/{id} (Dashboard)")
    col_meetings = MetricCollector("GET /projects/{id}/meetings")
    col_risks = MetricCollector("GET /projects/{id}/risks")
    col_xai = MetricCollector("GET /meetings/{id}/xai-diagnostics")
    col_webhook = MetricCollector("POST /webhooks/meetstream (Ingest)")

    # Define scenario weights (3:2:2:2:1 traffic mix)
    scenario_configs = [
        (scenario_dashboard_analytics, col_dashboard, 3),
        (scenario_meetings_list, col_meetings, 2),
        (scenario_risk_register, col_risks, 2),
        (scenario_xai_diagnostics, col_xai, 2),
        (scenario_webhook_ingest, col_webhook, 1),
    ]

    stop_event = asyncio.Event()

    # 1. Warm-up Phase
    if warmup_sec > 0:
        print(f"\n[1/3] Warming up endpoints ({warmup_sec}s)...")
        warmup_stop = asyncio.Event()
        warmup_tasks = [
            asyncio.create_task(
                worker_loop(i, client, scenario_configs, warmup_stop, think_time_ms)
            )
            for i in range(min(5, concurrency))
        ]
        await asyncio.sleep(warmup_sec)
        warmup_stop.set()
        await asyncio.gather(*warmup_tasks, return_exceptions=True)
        # Clear warmup metrics
        for _, c, _ in scenario_configs:
            c.latencies_ms.clear()
            c.status_codes.clear()
            c.errors = 0

    # 2. Benchmark Phase
    print(f"\n[2/3] Executing Load Test ({duration_sec}s with {concurrency} concurrent workers)...")
    t_start = time.perf_counter()
    for _, c, _ in scenario_configs:
        c.start_time = t_start

    tasks = [
        asyncio.create_task(
            worker_loop(i, client, scenario_configs, stop_event, think_time_ms)
        )
        for i in range(concurrency)
    ]

    await asyncio.sleep(duration_sec)
    stop_event.set()
    t_end = time.perf_counter()
    for _, c, _ in scenario_configs:
        c.end_time = t_end

    await asyncio.gather(*tasks, return_exceptions=True)
    await client.aclose()

    # 3. Analyze Results
    print("\n[3/3] Performance Test Results Summary:")
    print("-" * 105)
    headers = f"{'Scenario':<38} | {'Reqs':>6} | {'RPS':>7} | {'Avg':>7} | {'p50':>7} | {'p95':>7} | {'p99':>7} | {'Err%':>6}"
    print(headers)
    print("-" * 105)

    all_summaries = []
    total_reqs = 0
    total_errors = 0
    sla_failures = []

    for _, c, _ in scenario_configs:
        s = c.summary()
        all_summaries.append(s)
        total_reqs += s["count"]
        total_errors += s["errors"]

        print(
            f"{s['name']:<38} | "
            f"{s['count']:>6} | "
            f"{s['rps']:>7.1f} | "
            f"{s['avg_ms']:>6.1f}ms | "
            f"{s['p50_ms']:>6.1f}ms | "
            f"{s['p95_ms']:>6.1f}ms | "
            f"{s['p99_ms']:>6.1f}ms | "
            f"{s['error_rate_pct']:>5.1f}%"
        )

    # Check SLA thresholds
    dash_p95 = col_dashboard.summary()["p95_ms"]
    if dash_p95 > sla_p95_dashboard_ms:
        sla_failures.append(
            f"NFR-1.2 VIOLATION: Dashboard p95 latency {dash_p95:.1f}ms exceeds SLA limit {sla_p95_dashboard_ms:.1f}ms"
        )

    webhook_p95 = col_webhook.summary()["p95_ms"]
    if webhook_p95 > sla_p95_webhook_ms:
        sla_failures.append(
            f"NFR-1.1 VIOLATION: Webhook ingest p95 latency {webhook_p95:.1f}ms exceeds SLA limit {sla_p95_webhook_ms:.1f}ms"
        )

    overall_error_rate = (total_errors / max(1, total_reqs + total_errors)) * 100.0
    if overall_error_rate > max_error_rate_pct:
        sla_failures.append(
            f"NFR-3.2 VIOLATION: Error rate {overall_error_rate:.2f}% exceeds max threshold {max_error_rate_pct:.2f}%"
        )

    overall_duration = t_end - t_start
    overall_rps = total_reqs / max(0.001, overall_duration)

    print("-" * 105)
    print(f"Total Requests Processed:  {total_reqs:,}")
    print(f"Aggregate Throughput:      {overall_rps:.2f} req/sec")
    print(f"Overall Error Rate:        {overall_error_rate:.2f}% ({total_errors} failed requests)")
    print("=" * 105)

    if sla_failures:
        print("\n❌ SLA VERIFICATION FAILED:")
        for failure in sla_failures:
            print(f"  • {failure}")
        exit_code = 1
    else:
        print("\n✅ ALL NFR SLAs PASSED:")
        print(f"  • NFR-1.1 Webhook Latency:   {webhook_p95:.1f}ms <= {sla_p95_webhook_ms:.0f}ms (PASS)")
        print(f"  • NFR-1.2 Dashboard Latency: {dash_p95:.1f}ms <= {sla_p95_dashboard_ms:.0f}ms (PASS)")
        print(f"  • NFR-3.2 Availability:      {overall_error_rate:.2f}% <= {max_error_rate_pct:.2f}% (PASS)")
        exit_code = 0

    if output_json:
        report = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "concurrency": concurrency,
            "duration_sec": duration_sec,
            "total_requests": total_reqs,
            "aggregate_rps": round(overall_rps, 2),
            "error_rate_pct": round(overall_error_rate, 2),
            "sla_passed": len(sla_failures) == 0,
            "sla_failures": sla_failures,
            "scenarios": all_summaries,
        }
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"\nReport exported to: {output_json}")

    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prisk AI Asynchronous Performance and Load Testing Tool"
    )
    parser.add_argument(
        "--target-url",
        type=str,
        default="http://localhost:8000",
        help="Base URL for live target server (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--asgi",
        action="store_true",
        help="Run load test directly against FastAPI in-process ASGI (no server needed)",
    )
    parser.add_argument(
        "-c",
        "--concurrency",
        type=int,
        default=10,
        help="Number of concurrent virtual users (default: 10)",
    )
    parser.add_argument(
        "-d",
        "--duration",
        type=int,
        default=10,
        help="Duration of the benchmark phase in seconds (default: 10)",
    )
    parser.add_argument(
        "-w",
        "--warmup",
        type=int,
        default=2,
        help="Warmup phase duration in seconds (default: 2)",
    )
    parser.add_argument(
        "--think-time-ms",
        type=float,
        default=20.0,
        help="Simulated user delay between calls in milliseconds (default: 20ms)",
    )
    parser.add_argument(
        "--sla-p95-dashboard",
        type=float,
        default=3000.0,
        help="NFR-1.2 max p95 latency for dashboard in ms (default: 3000ms)",
    )
    parser.add_argument(
        "--sla-p95-webhook",
        type=float,
        default=2000.0,
        help="NFR-1.1 max p95 latency for webhook in ms (default: 2000ms)",
    )
    parser.add_argument(
        "--max-error-rate",
        type=float,
        default=0.1,
        help="NFR-3.2 max allowed error rate percentage (default: 0.1%%)",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default=None,
        help="Path to export JSON benchmark results (e.g. perf-report.json)",
    )

    args = parser.parse_args()

    exit_code = asyncio.run(
        run_performance_test(
            base_url=args.target_url,
            concurrency=args.concurrency,
            duration_sec=args.duration,
            warmup_sec=args.warmup,
            think_time_ms=args.think_time_ms,
            use_asgi=args.asgi,
            sla_p95_dashboard_ms=args.sla_p95_dashboard,
            sla_p95_webhook_ms=args.sla_p95_webhook,
            max_error_rate_pct=args.max_error_rate,
            output_json=args.output_json,
        )
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
