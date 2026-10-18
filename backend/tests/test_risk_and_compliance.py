from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
import unittest

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.bigquery import (
    _in_memory_bq_audit_events,
    _in_memory_bq_compliance_packages,
    _in_memory_bq_golden_records,
    _in_memory_bq_portfolio_risks,
)
from app.core.config import get_settings
from app.core.database import _in_memory_db, get_firestore_client
from app.core.storage import ComplianceStorageClient, _in_memory_worm_blobs
from app.main import app


class TestEnterpriseRiskAndComplianceWORM(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = get_settings()
        self.settings.use_in_memory_firestore = True
        self.settings.use_mock_firebase_auth = True
        _in_memory_db._collections.clear()
        _in_memory_worm_blobs.clear()
        _in_memory_bq_golden_records.clear()
        _in_memory_bq_audit_events.clear()
        _in_memory_bq_portfolio_risks.clear()
        _in_memory_bq_compliance_packages.clear()
        self.db = get_firestore_client()
        self.client = TestClient(app)

        self.admin_headers = {
            "Authorization": f"Bearer mock:{json.dumps({'uid': 'admin-001', 'email': 'admin@prisk.ai', 'role': 'ADMIN'})}"
        }
        self.exec_headers = {
            "Authorization": f"Bearer mock:{json.dumps({'uid': 'exec-001', 'email': 'exec@prisk.ai', 'role': 'EXECUTIVE'})}"
        }
        self.mgr_headers = {
            "Authorization": f"Bearer mock:{json.dumps({'uid': 'mgr-001', 'email': 'mgr@prisk.ai', 'role': 'MANAGER', 'assigned_project_ids': ['proj-alpha']})}"
        }


    def test_section_6_risk_register_5x5_heatmap_sla_and_systemic_spike(self) -> None:
        """Verify Tasks 6.1, 6.2, 6.3, and 6.4: COSO 5x5 matrix, overrides, SLA tiers, and Systemic Risk Spike."""
        # 6.1 Create risk in project-1 with Impact=5, Probability=4 -> Severity 20 (CRITICAL)
        create_resp = self.client.post(
            "/api/v1/risks",
            headers=self.admin_headers,
            json={
                "project_id": "proj-alpha",
                "company_name": "Alpha FinTech",
                "associated_groups": ["Client Legal & Compliance", "BUYER"],
                "title": "Regulatory Data Residency Gap",
                "description": "Cross-border replication policy lacks regional encryption keys.",
                "category": "COMPLIANCE",
                "impact": 5,
                "probability": 4,
                "owner_uid": "mgr-001",
            },
        )
        self.assertEqual(create_resp.status_code, 201)
        risk_data = create_resp.json()
        risk_id = risk_data["risk_id"]
        self.assertEqual(risk_data["severity_score"], 20)
        self.assertEqual(risk_data["severity_band"], "CRITICAL")
        self.assertEqual(risk_data["sla_escalation_tier"], "24h")

        # 6.1 Override risk via PATCH and append commentary
        patch_resp = self.client.patch(
            f"/api/v1/risks/{risk_id}",
            headers=self.admin_headers,
            json={
                "impact": 5,
                "probability": 5,
                "comment": "Escalated after legal architecture review.",
                "mitigation_plan": {"strategy": "Deploy regional KMS keys in Q4"},
            },
        )
        self.assertEqual(patch_resp.status_code, 200)
        updated_risk = patch_resp.json()
        self.assertEqual(updated_risk["severity_score"], 25)
        self.assertEqual(updated_risk["severity_band"], "CRITICAL")
        self.assertEqual(len(updated_risk["qualitative_commentary"]), 1)

        # Verify immutable audit trail drawer endpoint
        trail_resp = self.client.get(
            f"/api/v1/risks/{risk_id}/audit-trail",
            headers=self.admin_headers,
        )
        self.assertEqual(trail_resp.status_code, 200)
        trail_json = trail_resp.json()
        self.assertGreaterEqual(len(trail_json["audit_events"]), 2)

        # 6.2 Verify 5x5 Heatmap matrix has 25 cells and counts risk at (5, 5)
        heatmap_resp = self.client.get(
            "/api/v1/risks/heatmap?project_id=proj-alpha",
            headers=self.admin_headers,
        )
        self.assertEqual(heatmap_resp.status_code, 200)
        cells = heatmap_resp.json()["heatmap_cells"]
        self.assertEqual(len(cells), 25)
        cell_5_5 = next(c for c in cells if c["impact"] == 5 and c["probability"] == 5)
        self.assertEqual(cell_5_5["risk_count"], 1)
        self.assertIn(risk_id, cell_5_5["risk_ids"])

        # 6.3 Backdate SLA start by 75 hours to trigger 24h, 48h, and 72h SLA escalation
        past_75h = (datetime.now(timezone.utc) - timedelta(hours=75)).isoformat()
        doc_ref = self.db.collection("risk_register").document(risk_id)
        snap_dict = doc_ref.get().to_dict() or {}
        esc_cfg = dict(snap_dict.get("escalation_config") or {})
        esc_cfg["sla_started_at"] = past_75h
        esc_cfg["last_escalated_tier_hours"] = 0
        doc_ref.set({"escalation_config": esc_cfg, "created_at": past_75h}, merge=True)

        # 6.4 Create 2 more critical risks across distinct projects (proj-beta, proj-gamma) -> >= 3 critical projects
        for pid in ("proj-beta", "proj-gamma"):
            r_resp = self.client.post(
                "/api/v1/risks",
                headers=self.admin_headers,
                json={
                    "project_id": pid,
                    "title": f"Critical Infrastructure Exposure in {pid}",
                    "description": "High-severity operational bottleneck identified.",
                    "category": "OPERATIONAL",
                    "impact": 5,
                    "probability": 4,
                },
            )
            self.assertEqual(r_resp.status_code, 201)

        # Trigger Cloud Scheduler 15-minute cron endpoint POST /internal/jobs/evaluate-escalations
        cron_resp = self.client.post("/internal/jobs/evaluate-escalations")
        self.assertEqual(cron_resp.status_code, 200)
        cron_data = cron_resp.json()
        self.assertIn(risk_id, cron_data["escalated_72h_risk_ids"])
        self.assertTrue(cron_data["systemic_spike"]["is_active"])
        self.assertTrue(cron_data["systemic_spike"]["triggered_by_critical_projects"])
        self.assertGreaterEqual(
            cron_data["systemic_spike"]["concurrent_critical_project_count"], 3
        )

        # Verify portfolio analytics endpoint returns systemic spike and 25 heatmap cells
        analytics_resp = self.client.get(
            "/api/v1/analytics/portfolio-risks",
            headers=self.exec_headers,
        )
        self.assertEqual(analytics_resp.status_code, 200)
        analytics_data = analytics_resp.json()
        self.assertEqual(analytics_data["total_risks"], 3)
        self.assertTrue(analytics_data["systemic_spike"]["is_active"])

    def test_section_7_compliance_export_zero_quotes_worm_and_gdpr_purge(self) -> None:
        """Verify Tasks 7.1, 7.2, 7.3, 7.4, and 7.5: Crosswalk, Sanitization, PDF/CSV/JSON WORM Export, and GDPR Purge."""
        # Seed a meeting with dialogue blocks containing verbatim quotes and PII
        meeting_id = "mtg-gdpr-001"
        self.db.collection("meetings").document(meeting_id).set(
            {
                "meeting_id": meeting_id,
                "project_id": "proj-alpha",
                "title": "Executive Vendor Contract Review",
                "platform": "google_meet",
                "meeting_date": "2026-10-18T10:00:00Z",
                "status": "COMMITTED",
                "pulse_score": 42.5,
                "group_scores": {"BUYER": 38.0, "VENDOR": 68.0},
                "participants": ["Alice Henderson", "Bob Vance"],
                "model_metadata": {"upstream_transcript_deleted": True},
            }
        )
        verbatim_utt = "We cannot sign this addendum until the indemnification cap is doubled immediately"
        self.db.collection("meetings").document(meeting_id).collection(
            "dialogue_blocks"
        ).document("blk-01").set(
            {
                "block_id": "blk-01",
                "sequence_index": 1,
                "speaker_alias": "Alice Henderson",
                "group_id": "BUYER",
                "group_name": "Client Legal & Compliance",
                "text_scrubbed": verbatim_utt,
                "word_count": 12,
                "dlp_redaction_flags": ["EMAIL_ADDRESS"],
                "sentiment_score": 35.0,
            }
        )

        # Seed a sentiment calibration linked to this meeting
        self.db.collection("sentiment_calibrations").document("cal-gdpr-01").set(
            {
                "calibration_id": "cal-gdpr-01",
                "project_id": "proj-alpha",
                "meeting_id": meeting_id,
                "source_block_id": "blk-01",
                "dialogue_text": verbatim_utt,
                "benchmark_score": 35.0,
                "embedding": [0.01] * 768,
            }
        )

        # Create a risk linked to the meeting that accidentally includes a verbatim quote, email, and internal commentary
        risk_resp = self.client.post(
            "/api/v1/risks",
            headers=self.admin_headers,
            json={
                "project_id": "proj-alpha",
                "meeting_id": meeting_id,
                "associated_groups": ["Client Legal & Compliance"],
                "title": 'Contractual Liability Dispute by Alice Henderson ("indemnification cap is doubled")',
                "description": (
                    f'Participant Alice Henderson stated "{verbatim_utt}" '
                    "and emailed legal@alphafintech.com regarding SSN 123-45-6789."
                ),
                "category": "FINANCIAL",
                "impact": 4,
                "probability": 4,
            },
        )
        self.assertEqual(risk_resp.status_code, 201)
        risk_id = risk_resp.json()["risk_id"]

        # Append internal commentary that must be excluded from external compliance packages
        self.client.patch(
            f"/api/v1/risks/{risk_id}",
            headers=self.admin_headers,
            json={"comment": "INTERNAL SECRET NOTE: Do not share this margin note externally."},
        )

        # 7.1 Verify static framework crosswalk endpoint
        fw_resp = self.client.get(
            "/api/v1/compliance/frameworks",
            headers=self.exec_headers,
        )
        self.assertEqual(fw_resp.status_code, 200)
        fw_matrix = fw_resp.json()
        self.assertIn("ISO_31000", fw_matrix["supported_frameworks"])
        self.assertIn("GDPR", fw_matrix["supported_frameworks"])

        # 7.3 & 7.4 Export Compliance Package in PDF, CSV, and JSON across all 5 frameworks
        for fmt in ("PDF", "CSV", "JSON"):
            exp_resp = self.client.post(
                "/api/v1/compliance/export",
                headers=self.exec_headers,
                json={
                    "project_id": "proj-alpha",
                    "company_name": "Alpha FinTech Corp",
                    "target_frameworks": ["ISO_31000", "COSO", "SOC_2", "HIPAA", "GDPR"],
                    "format": fmt,
                },
            )
            self.assertEqual(exp_resp.status_code, 201)
            pkg = exp_resp.json()
            pkg_id = pkg["package_id"]
            self.assertEqual(pkg["status"], "SEALED_WORM")
            self.assertEqual(len(pkg["sha256_hash"]), 64)
            self.assertTrue(pkg["zero_verbatim_quotes_verified"])

            # Verify all 5 structured sections exist
            sections = pkg["sections"]
            self.assertIn("header_and_metadata", sections)
            self.assertIn("framework_control_mapping_table", sections)
            self.assertIn("sanitized_risk_register", sections)
            self.assertIn("mitigation_lifecycle_audit_summary", sections)
            self.assertIn("privacy_and_data_governance_attestation", sections)

            # 7.2 Verify zero verbatim quotes, PII redaction, and internal commentary exclusion
            serialized = json.dumps(sections)
            self.assertNotIn(verbatim_utt, serialized)
            self.assertNotIn("legal@alphafintech.com", serialized)
            self.assertNotIn("123-45-6789", serialized)
            self.assertNotIn("Alice Henderson", serialized)
            self.assertNotIn("INTERNAL SECRET NOTE", serialized)
            self.assertNotIn("qualitative_commentary", serialized)

            # Verify download matches recorded SHA-256 hash
            dl_resp = self.client.get(
                f"/api/v1/compliance/packages/{pkg_id}/download",
                headers=self.exec_headers,
            )
            self.assertEqual(dl_resp.status_code, 200)
            computed_sha = hashlib.sha256(dl_resp.content).hexdigest()
            self.assertEqual(computed_sha, pkg["sha256_hash"])
            if fmt == "PDF":
                self.assertTrue(dl_resp.content.startswith(b"%PDF-1.4"))

            # Verify cryptographic integrity endpoint
            ver_resp = self.client.get(
                f"/api/v1/compliance/packages/{pkg_id}/verify",
                headers=self.exec_headers,
            )
            self.assertEqual(ver_resp.status_code, 200)
            self.assertTrue(ver_resp.json()["integrity_verified"])

            # Verify WORM Retention Lock blocks deletion or overwrite of sealed artifact
            storage_client = ComplianceStorageClient()
            with self.assertRaises(PermissionError):
                storage_client.delete_compliance_package(pkg_id, "proj-alpha")

        # 7.5 Execute GDPR Article 17 cascading purge on `mtg-gdpr-001`
        purge_resp = self.client.delete(
            f"/api/v1/meetings/{meeting_id}/purge",
            headers=self.admin_headers,
        )
        self.assertEqual(purge_resp.status_code, 200)
        purge_data = purge_resp.json()
        self.assertEqual(purge_data["status"], "PURGED_GDPR_ARTICLE_17")
        self.assertEqual(purge_data["purged_dialogue_blocks_count"], 1)
        self.assertEqual(purge_data["purged_calibrations_count"], 1)
        self.assertEqual(purge_data["purged_risks_count"], 1)
        self.assertGreaterEqual(purge_data["redacted_compliance_packages_count"], 1)

        # Verify meeting, dialogue blocks, calibration, and risk are deleted from Firestore
        self.assertFalse(self.db.collection("meetings").document(meeting_id).get().exists)
        self.assertFalse(
            self.db.collection("sentiment_calibrations").document("cal-gdpr-01").get().exists
        )
        self.assertFalse(self.db.collection("risk_register").document(risk_id).get().exists)

        # Verify tombstone event exists in immutable audit_ledger
        tombstone_id = purge_data["tombstone_audit_event_id"]
        tombstone_doc = self.db.collection("audit_ledger").document(tombstone_id).get()
        self.assertTrue(tombstone_doc.exists)
        self.assertEqual(
            tombstone_doc.to_dict()["event_type"],
            "GDPR_ARTICLE_17_ERASURE_TOMBSTONE",
        )

    def test_ai_risk_discovery_from_pulse_drop(self) -> None:
        """Task 6.1: Test automated AI risk discovery from pulse drops (>15 pts or <40)."""
        # Create meeting 1 with normal pulse
        self.db.collection("meetings").document("mtg-ai-disc-01").set({
            "meeting_id": "mtg-ai-disc-01",
            "project_id": "proj-alpha",
            "title": "Sprint 1 Kickoff",
            "meeting_date": "2026-10-01T10:00:00Z",
            "pulse_score": 75.0,
            "group_pulse_scores": {"Vendor Engineering": 72.0, "Buyer Core": 78.0},
        })
        # Create meeting 2 with a severe Vendor pulse drop (>15 pts, 72.0 -> 48.0)
        self.db.collection("meetings").document("mtg-ai-disc-02").set({
            "meeting_id": "mtg-ai-disc-02",
            "project_id": "proj-alpha",
            "title": "Sprint 1 Review",
            "meeting_date": "2026-10-08T10:00:00Z",
            "pulse_score": 52.0,
            "group_pulse_scores": {"Vendor Engineering": 48.0, "Buyer Core": 56.0},
        })
        # Add a dialogue block to meeting 2
        self.db.collection("meetings").document("mtg-ai-disc-02").collection("dialogue_blocks").document("blk-01").set({
            "block_id": "blk-01",
            "meeting_id": "mtg-ai-disc-02",
            "sequence_index": 0,
            "text_scrubbed": "Vendor delivery team is severely blocked by API dependency bottlenecks.",
            "speaker_alias": "Vendor Lead",
            "word_count": 9,
        })


        # Discover risks with auto_register=False
        resp = self.client.post(
            "/api/v1/risks/ai-discover",
            headers=self.mgr_headers,
            json={"project_id": "proj-alpha", "auto_register": False},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreaterEqual(data["total_risks_found"], 1)
        self.assertEqual(data["registered_count"], 0)
        discovered = data["discovered_risks"][0]
        self.assertIn("Vendor Engineering", discovered["associated_groups"])
        self.assertIn("48.0", discovered["trigger_reason"])
        self.assertEqual(discovered["status"], "DRAFT_PENDING_ADJUDICATION")

        # Discover risks with auto_register=True
        resp_reg = self.client.post(
            "/api/v1/risks/ai-discover",
            headers=self.admin_headers,
            json={"project_id": "proj-alpha", "auto_register": True},
        )
        self.assertEqual(resp_reg.status_code, 200)
        reg_data = resp_reg.json()
        self.assertGreaterEqual(reg_data["registered_count"], 1)
        auto_risk_id = reg_data["discovered_risks"][0]["risk_id"]
        self.assertIsNotNone(auto_risk_id)

        # Verify created in Firestore
        risk_doc = self.db.collection("risk_register").document(auto_risk_id).get()
        self.assertTrue(risk_doc.exists)

    def test_ai_mitigation_synthesis(self) -> None:
        """Task 6.1: Test proactive mitigation synthesis and one-click apply."""
        # Create a risk
        risk_resp = self.client.post(
            "/api/v1/risks",
            headers=self.admin_headers,
            json={
                "project_id": "proj-alpha",
                "title": "Vendor Milestone Bottleneck Risk",
                "description": "Critical API integration delayed due to unresolved architectural blockers.",
                "category": "OPERATIONAL",
                "impact": 4,
                "probability": 4,
                "associated_groups": ["Vendor Engineering"],
            },
        )
        self.assertEqual(risk_resp.status_code, 201)
        risk_id = risk_resp.json()["risk_id"]

        # Call AI mitigation endpoint with apply_to_risk=True
        mit_resp = self.client.post(
            f"/api/v1/risks/{risk_id}/ai-mitigation",
            headers=self.mgr_headers,
            json={"apply_to_risk": True, "context_notes": "Urgent executive intervention required"},
        )
        self.assertEqual(mit_resp.status_code, 200)
        mit_data = mit_resp.json()
        self.assertEqual(mit_data["risk_id"], risk_id)
        self.assertTrue(mit_data["applied"])
        self.assertIsNotNone(mit_data["mitigation_strategy"])
        self.assertGreaterEqual(len(mit_data["suggested_action_items"]), 1)
        self.assertIsNotNone(mit_data["executive_escalation_brief"])
        self.assertLess(mit_data["residual_impact"], 5)

        # Verify updated risk in database has mitigation_plan populated
        refreshed_risk = self.client.get(f"/api/v1/risks/{risk_id}", headers=self.mgr_headers).json()
        self.assertIsNotNone(refreshed_risk.get("mitigation_plan"))
        self.assertEqual(
            refreshed_risk["mitigation_plan"]["mitigation_strategy"],
            mit_data["mitigation_strategy"],
        )

    def test_ai_compliance_narrative_and_gdpr_purge_endpoint(self) -> None:
        """Task 7.1 & 7.2: Test AI compliance narrative synthesis and compliance GDPR purge endpoint."""
        # Test AI compliance narrative preview
        narr_resp = self.client.post(
            "/api/v1/compliance/ai-narrative",
            headers=self.mgr_headers,
            json={
                "project_id": "proj-alpha",
                "company_name": "Alpha FinTech Corp",
                "target_frameworks": ["ISO_31000", "COSO", "SOC_2", "HIPAA", "GDPR"],
            },
        )
        self.assertEqual(narr_resp.status_code, 200)
        narr_data = narr_resp.json()
        self.assertTrue(narr_data["zero_verbatim_quotes_verified"])
        self.assertIn("ISO_31000", narr_data["framework_treatment_summaries"])
        self.assertIn("GDPR", narr_data["framework_treatment_summaries"])
        self.assertIn("continuous_monitoring_attestation", narr_data)
        self.assertIn("zero_audio_privacy_statement", narr_data)

        # Test POST /api/v1/compliance/gdpr-purge
        self.db.collection("meetings").document("mtg-compliance-purge-01").set({
            "meeting_id": "mtg-compliance-purge-01",
            "project_id": "proj-alpha",
            "title": "GDPR Purge Target Meeting",
            "meeting_date": "2026-10-10T14:00:00Z",
            "pulse_score": 60.0,
        })
        purge_resp = self.client.post(
            "/api/v1/compliance/gdpr-purge",
            headers=self.admin_headers,
            json={"meeting_id": "mtg-compliance-purge-01"},
        )
        self.assertEqual(purge_resp.status_code, 200)
        self.assertEqual(purge_resp.json()["status"], "PURGED_GDPR_ARTICLE_17")
        self.assertFalse(self.db.collection("meetings").document("mtg-compliance-purge-01").get().exists)


if __name__ == "__main__":
    unittest.main()

