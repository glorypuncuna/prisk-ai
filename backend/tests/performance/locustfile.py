"""Locust Load & Performance Test Suite for Prisk AI
===================================================
Simulates multi-persona enterprise traffic against Prisk AI:
  1. ExecutiveManagerUser (Weight 3): Portfolio dashboards, risk registers, compliance matrix
  2. AdjudicatorUser (Weight 5): Meeting review, XAI token attribution inspection, sentiment sliders
  3. MeetstreamBotUser (Weight 2): High-throughput meeting transcript ingestion webhooks

Run with Web UI:
  locust -f backend/tests/performance/locustfile.py --host http://localhost:8000

Run Headless (CI/CD / CLI):
  locust -f backend/tests/performance/locustfile.py --host http://localhost:8000 \
         --headless -u 50 -r 5 --run-time 1m --stop-timeout 10
"""

import json
import random
from locust import HttpUser, between, task, tag, events

PROJECT_ID = "proj-alpha"
MEETING_ID = "mtg-q3-001"

MOCK_MANAGER_HEADER = {
    "Authorization": f"Bearer mock:{json.dumps({'uid': 'uid_manager_locust', 'email': 'mgr@enterprise.com', 'role': 'MANAGER', 'assigned_project_ids': [PROJECT_ID]})}"
}
MOCK_ADJUDICATOR_HEADER = {
    "Authorization": f"Bearer mock:{json.dumps({'uid': 'uid_adj_locust', 'email': 'adj@enterprise.com', 'role': 'ADJUDICATOR', 'assigned_project_ids': [PROJECT_ID]})}"
}
MOCK_ADMIN_HEADER = {
    "Authorization": f"Bearer mock:{json.dumps({'uid': 'uid_admin_locust', 'email': 'admin@enterprise.com', 'role': 'ADMIN', 'assigned_project_ids': [PROJECT_ID]})}"
}


class ExecutiveManagerUser(HttpUser):
    """Simulates an Executive or Portfolio Manager reviewing analytics,

    historical pulse trends, and project risk registers.
    """
    weight = 3
    wait_time = between(1.0, 3.0)

    @tag("dashboard", "nfr-1.2")
    @task(4)
    def view_project_dashboard(self):
        """NFR-1.2: Validates dashboard load SLA (< 3.0s)."""
        with self.client.get(
            f"/api/v1/projects/{PROJECT_ID}",
            headers=MOCK_MANAGER_HEADER,
            name="GET /projects/{id} [Dashboard NFR-1.2]",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                if response.elapsed.total_seconds() > 3.0:
                    response.failure(f"SLA Breach: Dashboard took {response.elapsed.total_seconds()}s (> 3.0s)")
                else:
                    response.success()
            else:
                response.failure(f"Status code {response.status_code}")

    @tag("risks")
    @task(3)
    def view_risk_register(self):
        self.client.get(
            f"/api/v1/projects/{PROJECT_ID}/risks",
            headers=MOCK_MANAGER_HEADER,
            name="GET /projects/{id}/risks",
        )

    @tag("meetings")
    @task(2)
    def view_meetings_list(self):
        self.client.get(
            f"/api/v1/projects/{PROJECT_ID}/meetings",
            headers=MOCK_MANAGER_HEADER,
            name="GET /projects/{id}/meetings",
        )

    @tag("compliance")
    @task(1)
    def check_compliance_framework(self):
        self.client.get(
            "/api/v1/compliance/frameworks",
            headers=MOCK_MANAGER_HEADER,
            name="GET /compliance/frameworks",
        )


class AdjudicatorUser(HttpUser):
    """Simulates an Adjudicator reviewing meetings, inspecting XAI attributions,

    and approving/overriding draft risk observations.
    """
    weight = 5
    wait_time = between(0.5, 2.0)

    @tag("xai", "adjudication")
    @task(4)
    def view_meeting_xai_diagnostics(self):
        self.client.get(
            f"/api/v1/meetings/{MEETING_ID}/xai-diagnostics",
            headers=MOCK_ADJUDICATOR_HEADER,
            name="GET /meetings/{id}/xai-diagnostics",
        )

    @tag("adjudication")
    @task(2)
    def view_meeting_golden_record(self):
        self.client.get(
            f"/api/v1/meetings/{MEETING_ID}",
            headers=MOCK_ADJUDICATOR_HEADER,
            name="GET /meetings/{id}",
        )

    @tag("adjudication", "override")
    @task(1)
    def submit_adjudication_override(self):
        payload = {
            "revised_pulse_score": random.randint(45, 85),
            "override_reason": "Automated performance load testing synthetic review",
            "adjudicator_notes": "Adjudication validated under stress testing workload",
        }
        self.client.patch(
            f"/api/v1/meetings/{MEETING_ID}/adjudicate",
            headers=MOCK_ADJUDICATOR_HEADER,
            json=payload,
            name="PATCH /meetings/{id}/adjudicate",
        )


class MeetstreamBotUser(HttpUser):
    """Simulates meetstream.ai background bots pushing post-meeting transcripts."""
    weight = 2
    wait_time = between(2.0, 5.0)

    @tag("webhook", "nfr-1.1")
    @task
    def push_transcript_webhook(self):
        """NFR-1.1: Webhook ingestion latency (< 2.0s)."""
        payload = {
            "event_type": "transcript.completed",
            "meeting_id": f"mtg-bot-{random.randint(10000, 99999)}",
            "project_id": PROJECT_ID,
            "company_name": "Enterprise Holdings Inc",
            "title": "Automated Bot Ingestion Stress Test",
            "dialogue_blocks": [
                {
                    "speaker_name": "Staff Engineer",
                    "speaker_account_id": "spk-eng-01",
                    "text": "The distributed risk engine meets performance SLOs.",
                    "start_time": "00:00:10",
                    "end_time": "00:00:20",
                },
                {
                    "speaker_name": "Governance Officer",
                    "speaker_account_id": "spk-gov-02",
                    "text": "Ensuring PII masking and cryptographic hash ledgers are active.",
                    "start_time": "00:00:21",
                    "end_time": "00:00:35",
                },
            ],
        }

        with self.client.post(
            "/api/v1/webhooks/meetstream",
            json=payload,
            name="POST /webhooks/meetstream [Ingest NFR-1.1]",
            catch_response=True,
        ) as response:
            if response.status_code in (200, 201, 202):
                if response.elapsed.total_seconds() > 2.0:
                    response.failure(f"SLA Breach: Webhook took {response.elapsed.total_seconds()}s (> 2.0s)")
                else:
                    response.success()
            else:
                response.failure(f"Status code {response.status_code}")
