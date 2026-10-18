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
from app.core.storage import _in_memory_worm_blobs
from app.main import app, seed_development_data


class TestAllButtonsBackendIntegration(unittest.TestCase):
    """Exhaustive integration test verifying that every button in the frontend application

    has a corresponding, functioning backend endpoint that executes successfully.
    """

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
        seed_development_data()
        self.client = TestClient(app)

        self.admin_headers = {
            "Authorization": f"Bearer mock:{json.dumps({'uid': 'uid_admin_enterprise_com', 'email': 'admin@enterprise.com', 'role': 'ADMIN', 'assigned_project_ids': ['proj-alpha']})}"
        }
        self.mgr_headers = {
            "Authorization": f"Bearer mock:{json.dumps({'uid': 'uid_manager_enterprise_com', 'email': 'manager@enterprise.com', 'role': 'MANAGER', 'assigned_project_ids': ['proj-alpha']})}"
        }
        self.adjudicator_headers = {
            "Authorization": f"Bearer mock:{json.dumps({'uid': 'uid_adj_enterprise_com', 'email': 'adjudicator@enterprise.com', 'role': 'ADJUDICATOR', 'assigned_project_ids': ['proj-alpha']})}"
        }

    def test_health_check_button(self) -> None:
        """Health check endpoint verification."""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

    def test_admin_console_buttons(self) -> None:
        """Buttons on AdminUsersPage: Refresh Backlog, Elevate/Demote Role, Delete User, AI Governance Summary."""
        # 1. Quarantined backlog
        q_resp = self.client.get("/api/v1/admin/users/quarantined", headers=self.admin_headers)
        self.assertEqual(q_resp.status_code, 200)
        self.assertIsInstance(q_resp.json(), list)

        # 2. Update role button
        role_resp = self.client.patch(
            "/api/v1/admin/users/uid_manager_enterprise_com/role",
            headers=self.admin_headers,
            json={"role": "MANAGER"},
        )
        self.assertEqual(role_resp.status_code, 200)
        self.assertEqual(role_resp.json()["role"], "MANAGER")

        # 3. AI Governance Summary button
        gov_resp = self.client.get("/api/v1/admin/ai-governance-summary", headers=self.admin_headers)
        self.assertEqual(gov_resp.status_code, 200)
        self.assertIn("executive_summary", gov_resp.json())

        # 4. Delete user button
        # Seed a dummy user first
        self.db.collection("users").document("temp_delete_user").set({
            "uid": "temp_delete_user",
            "email": "temp@enterprise.com",
            "role": "EXTERNAL_STAKEHOLDER",
            "onboarding_status": "QUARANTINED",
            "assigned_project_ids": [],
            "created_at": "2026-10-18T00:00:00Z",
        })
        del_resp = self.client.delete("/api/v1/admin/users/temp_delete_user", headers=self.admin_headers)
        self.assertEqual(del_resp.status_code, 200)

    def test_projects_page_buttons(self) -> None:
        """Buttons on ProjectsPage: Create Project, AI Suggest Groups, Vector Diagnostics, Send Invitation, Accept Invitation."""
        # 1. Create project
        create_resp = self.client.post(
            "/api/v1/projects",
            headers=self.mgr_headers,
            json={
                "project_id": "proj-beta",
                "name": "Project Beta Financial",
                "company_name": "Beta Global Inc",
                "description": "Enterprise cloud compliance and financial risk tracking",
                "canonical_groups": ["BUYER", "VENDOR", "INTERNAL"],
            },
        )
        self.assertEqual(create_resp.status_code, 201)
        self.assertEqual(create_resp.json()["project_id"], "proj-beta")

        # 2. AI Suggest Groups button
        suggest_resp = self.client.post(
            "/api/v1/projects/proj-beta/ai-suggest-groups",
            headers=self.mgr_headers,
            json={
                "name": "Project Beta Financial",
                "company_name": "Beta Global Inc",
                "description": "Financial risk tracking and cross-border regulatory compliance",
            },
        )
        self.assertEqual(suggest_resp.status_code, 200)
        self.assertIn("suggested_canonical_groups", suggest_resp.json())

        # 3. Vector diagnostics button
        diag_resp = self.client.get("/api/v1/projects/proj-beta/vector-diagnostics", headers=self.mgr_headers)
        self.assertEqual(diag_resp.status_code, 200)
        self.assertEqual(diag_resp.json()["project_id"], "proj-beta")
        self.assertEqual(diag_resp.json()["embedding_dimension"], 768)

        # 4. Send invitation button
        inv_resp = self.client.post(
            "/api/v1/projects/proj-beta/invitations",
            headers=self.mgr_headers,
            json={
                "email": "invitee@enterprise.com",
                "target_role": "ADJUDICATOR",
            },
        )
        self.assertEqual(inv_resp.status_code, 201)
        token = inv_resp.json()["invitation_id"]

        # 5. Accept invitation button
        self.db.collection("users").document("uid_invitee_01").set({
            "uid": "uid_invitee_01",
            "email": "invitee@enterprise.com",
            "first_name": "Invited",
            "last_name": "Member",
            "phone_number": "+6281100002222",
            "role": "EXTERNAL_STAKEHOLDER",
            "assigned_project_ids": [],
            "onboarding_status": "QUARANTINED",
            "created_at": "2026-10-18T00:00:00Z",
        })
        accept_resp = self.client.post(
            f"/api/v1/projects/invitations/{token}/accept",
            headers={
                "Authorization": f"Bearer mock:{json.dumps({'uid': 'uid_invitee_01', 'email': 'invitee@enterprise.com', 'role': 'EXTERNAL_STAKEHOLDER'})}"
            },
        )
        self.assertEqual(accept_resp.status_code, 200)
        self.assertIn("proj-beta", accept_resp.json()["assigned_project_ids"])

    def test_meeting_capture_and_calendar_buttons(self) -> None:
        """Buttons on MeetingCapturePage & CalendarArchivePage: Dispatch Bot, List Meetings, Get Meeting, Run AI Analysis, Regenerate Insights."""
        # 1. Dispatch Bot button
        dispatch_resp = self.client.post(
            "/api/v1/meetings/dispatch-bot",
            headers=self.mgr_headers,
            json={
                "project_id": "proj-alpha",
                "meeting_link": "https://meet.google.com/abc-defg-hij",
                "title": "Weekly Architectural Review",
                "bot_name": "pRiskAI Notetaker",
            },
        )
        self.assertEqual(dispatch_resp.status_code, 200)
        new_mtg_id = dispatch_resp.json()["meeting_id"]

        # 2. List Meetings button / Calendar View
        list_resp = self.client.get("/api/v1/meetings?project_id=proj-alpha", headers=self.mgr_headers)
        self.assertEqual(list_resp.status_code, 200)
        self.assertGreaterEqual(len(list_resp.json()), 1)

        # 3. Get Meeting Details
        get_resp = self.client.get(f"/api/v1/meetings/{new_mtg_id}", headers=self.mgr_headers)
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["meeting_id"], new_mtg_id)

        # 4. Run AI Analysis button (Analyze Meeting)
        analyze_resp = self.client.post(
            "/api/v1/meetings/mtg_alpha_adjudication/analyze",
            headers=self.mgr_headers,
        )
        self.assertEqual(analyze_resp.status_code, 200)
        self.assertIn("pulse_score", analyze_resp.json())

        # 5. Regenerate Insights button
        regen_resp = self.client.post(
            "/api/v1/meetings/mtg_alpha_adjudication/regenerate-insights",
            headers=self.mgr_headers,
        )
        self.assertEqual(regen_resp.status_code, 200)
        self.assertIn("pulse_score", regen_resp.json())

    def test_adjudication_workspace_buttons(self) -> None:
        """Buttons on AdjudicationWorkspacePage: Get Workspace, Split Dialogue Bubble, Session Grouping, Score Slider Adjust, XAI Explain, Commit Golden Record."""
        mtg_id = "mtg_alpha_adjudication"

        # 1. Get Adjudication Workspace
        adj_resp = self.client.get(f"/api/v1/meetings/{mtg_id}/adjudication", headers=self.mgr_headers)
        self.assertEqual(adj_resp.status_code, 200)
        self.assertEqual(adj_resp.json()["meeting"]["meeting_id"], mtg_id)
        self.assertGreaterEqual(len(adj_resp.json()["dialogue_blocks"]), 3)

        # 2. Cursor Split Bubble button (Alt+S)
        split_resp = self.client.post(
            f"/api/v1/meetings/{mtg_id}/blocks/blk-0003/split",
            headers=self.mgr_headers,
            json={"split_char_index": 45},
        )
        self.assertEqual(split_resp.status_code, 200)
        self.assertEqual(len(split_resp.json()["child_blocks"]), 2)
        self.assertEqual(split_resp.json()["parent_block_id"], "blk-0003")

        # 3. Speaker to Group mapping dropdown
        group_resp = self.client.patch(
            f"/api/v1/meetings/{mtg_id}/session-grouping",
            headers=self.mgr_headers,
            json={
                "ephemeral_speaker_account_id": "ms_spk_01",
                "group_name": "Client Legal & Compliance",
            },
        )
        self.assertEqual(group_resp.status_code, 200)
        self.assertEqual(group_resp.json()["ephemeral_speaker_map"]["ms_spk_01"], "Client Legal & Compliance")

        # 4. Dialogue block slider score adjustment
        score_resp = self.client.patch(
            f"/api/v1/meetings/{mtg_id}/blocks/blk-0001/score",
            headers=self.mgr_headers,
            json={
                "final_pulse_score": 45.0,
                "group_name": "Client Legal & Compliance",
                "is_pinned": True,
            },
        )
        self.assertEqual(score_resp.status_code, 200)
        self.assertEqual(score_resp.json()["block"]["sentiment_score"], 45.0)

        # 5. XAI Explain button
        xai_resp = self.client.post(
            f"/api/v1/meetings/{mtg_id}/blocks/blk-0001/explain",
            headers=self.mgr_headers,
        )
        self.assertEqual(xai_resp.status_code, 200)
        self.assertIn("attributions", xai_resp.json())

        # 6. Commit Golden Record button
        commit_resp = self.client.post(
            f"/api/v1/meetings/{mtg_id}/commit-golden-record",
            headers=self.mgr_headers,
            json={
                "approved_risk_ids": ["RSK-ALPHA-01"],
                "dismissed_risk_ids": [],
            },
        )
        self.assertEqual(commit_resp.status_code, 200)
        self.assertTrue(commit_resp.json()["success"])
        self.assertEqual(commit_resp.json()["status"], "GOLDEN_RECORD")

    def test_pulse_trends_dashboard_buttons(self) -> None:
        """Buttons on PulseDashboardPage: Window Selectors 7D, 30D, QTD, Custom."""
        for window in ["7D", "30D", "QTD", "Custom"]:
            resp = self.client.get(
                f"/api/v1/analytics/pulse-trends?project_id=proj-alpha&time_window={window}",
                headers=self.mgr_headers,
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn("proj-alpha", data["project_ids"])
            self.assertEqual(data["time_window"], window.upper())
            self.assertIn("ai_commentary", data)

    def test_risk_register_buttons(self) -> None:
        """Buttons on RiskRegisterPage: AI Discover Emerging Risks, Register Custom Risk, Inline Patch (Impact, Probability, Status, Owner), AI Mitigation Synthesizer, Audit Trail."""
        # 1. AI Discover Emerging Risks button
        disc_resp = self.client.post(
            "/api/v1/risks/ai-discover",
            headers=self.mgr_headers,
            json={"project_id": "proj-alpha", "min_drop_threshold": 15.0},
        )
        self.assertEqual(disc_resp.status_code, 200)
        self.assertIn("discovered_risks", disc_resp.json())

        # 2. Create custom risk button
        create_resp = self.client.post(
            "/api/v1/risks",
            headers=self.mgr_headers,
            json={
                "project_id": "proj-alpha",
                "title": "Vendor SLA Breached on Database Migration",
                "category": "OPERATIONAL",
                "impact": 4,
                "probability": 3,
                "associated_groups": ["Internal Delivery Team"],
            },
        )
        self.assertEqual(create_resp.status_code, 201)
        new_risk_id = create_resp.json()["risk_id"]

        # 3. Inline patch Impact (1-5) and Probability (1-5)
        patch_resp = self.client.patch(
            f"/api/v1/risks/{new_risk_id}",
            headers=self.mgr_headers,
            json={
                "impact": 5,
                "probability": 5,
                "status": "OPEN",
            },
        )
        self.assertEqual(patch_resp.status_code, 200)
        self.assertEqual(patch_resp.json()["severity_score"], 25)
        self.assertEqual(patch_resp.json()["severity_band"], "CRITICAL")

        # 4. AI Mitigation Synthesizer button
        mit_resp = self.client.post(
            f"/api/v1/risks/{new_risk_id}/ai-mitigation",
            headers=self.mgr_headers,
            json={"project_id": "proj-alpha", "target_residual_severity": 10},
        )
        self.assertEqual(mit_resp.status_code, 200)
        self.assertIn("mitigation_strategy", mit_resp.json())
        self.assertIn("suggested_action_items", mit_resp.json())

        # 5. Audit Trail drawer button
        audit_resp = self.client.get(
            f"/api/v1/risks/{new_risk_id}/audit-trail",
            headers=self.mgr_headers,
        )
        self.assertEqual(audit_resp.status_code, 200)
        self.assertIn("audit_events", audit_resp.json())
        self.assertIsInstance(audit_resp.json()["audit_events"], list)

    def test_compliance_console_buttons(self) -> None:
        """Buttons on ComplianceConsolePage: Frameworks Matrix, AI Compliance Narrative, Export Package, List Packages, Download URL, Download Binary, Verify SHA-256 Digest, GDPR Purge."""
        # 1. Frameworks Matrix
        fw_resp = self.client.get("/api/v1/compliance/frameworks", headers=self.mgr_headers)
        self.assertEqual(fw_resp.status_code, 200)
        self.assertIn("frameworks", fw_resp.json())

        # 2. AI Compliance Narrative Synthesizer button
        narrative_resp = self.client.post(
            "/api/v1/compliance/ai-narrative",
            headers=self.mgr_headers,
            json={
                "project_id": "proj-alpha",
                "company_name": "Acme Financial Corp",
                "target_frameworks": ["ISO_31000", "COSO", "SOC_2", "GDPR"],
            },
        )
        self.assertEqual(narrative_resp.status_code, 200)
        self.assertTrue(narrative_resp.json()["zero_verbatim_quotes_verified"])

        # 3. Export Sealed Compliance Package button
        export_resp = self.client.post(
            "/api/v1/compliance/export",
            headers=self.mgr_headers,
            json={
                "project_id": "proj-alpha",
                "company_name": "Acme Financial Corp",
                "target_frameworks": ["ISO_31000", "COSO", "SOC_2"],
                "format": "PDF",
            },
        )
        self.assertEqual(export_resp.status_code, 201)
        pkg_id = export_resp.json()["package_id"]
        sha256 = export_resp.json()["sha256_hash"]

        # 4. List Compliance Packages
        list_pkg_resp = self.client.get("/api/v1/compliance/packages?project_id=proj-alpha", headers=self.mgr_headers)
        self.assertEqual(list_pkg_resp.status_code, 200)
        self.assertGreaterEqual(len(list_pkg_resp.json()), 1)

        # 5. Get Compliance Package Download URL button
        dl_url_resp = self.client.get(f"/api/v1/compliance/packages/{pkg_id}/download-url", headers=self.mgr_headers)
        self.assertEqual(dl_url_resp.status_code, 200)
        self.assertIn("download_url", dl_url_resp.json())
        self.assertEqual(dl_url_resp.json()["sha256_hash"], sha256)

        # 6. Direct Binary Download button
        dl_bin_resp = self.client.get(f"/api/v1/compliance/packages/{pkg_id}/download", headers=self.mgr_headers)
        self.assertEqual(dl_bin_resp.status_code, 200)
        self.assertIn("Content-Disposition", dl_bin_resp.headers)
        self.assertEqual(hashlib.sha256(dl_bin_resp.content).hexdigest(), sha256)

        # 7. Verify SHA-256 Digest button
        verify_resp = self.client.get(f"/api/v1/compliance/packages/{pkg_id}/verify", headers=self.mgr_headers)
        self.assertEqual(verify_resp.status_code, 200)
        self.assertTrue(verify_resp.json()["integrity_valid"])

        # 8. Seeded PKG-ALPHA-01 verification and download
        seed_verify_resp = self.client.get("/api/v1/compliance/packages/PKG-ALPHA-01/verify", headers=self.mgr_headers)
        self.assertEqual(seed_verify_resp.status_code, 200)
        self.assertTrue(seed_verify_resp.json()["integrity_valid"])

        # 9. GDPR Article 17 Purge button
        purge_resp = self.client.post(
            "/api/v1/compliance/gdpr-purge",
            headers=self.mgr_headers,
            json={
                "meeting_id": "mtg_alpha_adjudication",
                "reason": "Data Subject Right-to-Erasure Request #GDPR-2026-081",
            },
        )
        self.assertEqual(purge_resp.status_code, 200)
        self.assertIn("PURGED", purge_resp.json()["status"])
        self.assertIn("tombstone_audit_event_id", purge_resp.json())


if __name__ == "__main__":
    unittest.main()
