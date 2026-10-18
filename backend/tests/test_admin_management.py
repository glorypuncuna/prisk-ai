import json
import unittest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import get_firestore_client
from app.core.enums import UserRole
from app.core.firebase import get_mock_custom_claims, reset_mock_custom_claims
from app.main import app


def make_mock_bearer(
    uid: str,
    email: str,
    role: str = "ADMIN",
    provider: str = "password",
) -> dict[str, str]:
    payload: dict[str, object] = {
        "uid": uid,
        "email": email,
        "role": role,
        "auth_provider": provider,
        "firebase": {"sign_in_provider": provider},
    }
    token = f"mock:{json.dumps(payload)}"
    return {"Authorization": f"Bearer {token}"}


class TestSuperAdminManagement(unittest.TestCase):
    def setUp(self) -> None:
        settings = get_settings()
        settings.use_in_memory_firestore = True
        settings.use_mock_firebase_auth = True
        db = get_firestore_client()
        db.clear()
        reset_mock_custom_claims()
        self.client = TestClient(app)

        # Seed an active admin user
        self.admin_uid = "uid_superadmin"
        self.admin_email = "superadmin@enterprise.com"
        self.admin_headers = make_mock_bearer(
            self.admin_uid,
            self.admin_email,
            role="ADMIN",
        )
        db.collection("users").document(self.admin_uid).set(
            {
                "uid": self.admin_uid,
                "email": self.admin_email,
                "first_name": "Super",
                "last_name": "Admin",
                "phone_number": "+14155552671",
                "role": "ADMIN",
                "auth_provider": "password",
                "assigned_project_ids": [],
                "onboarding_status": "ACTIVE",
                "created_at": "2026-01-01T00:00:00Z",
                "last_login_at": "2026-01-01T00:00:00Z",
            }
        )

    def test_admin_role_at_apex_and_claims_sync(self) -> None:
        """Verify ADMIN role is recognized at the apex of the RBAC hierarchy."""
        resp = self.client.get("/api/v1/auth/me", headers=self.admin_headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["role"], "ADMIN")
        self.assertEqual(data["uid"], self.admin_uid)

    def test_admin_project_bypass_permissions(self) -> None:
        """Verify ADMIN can access, create, and list projects across all boundaries."""
        # Create a project as admin
        create_resp = self.client.post(
            "/api/v1/projects",
            headers=self.admin_headers,
            json={
                "project_id": "proj-apex",
                "name": "Apex Core Infrastructure",
                "description": "Global enterprise security audit",
            },
        )
        self.assertEqual(create_resp.status_code, 201)

        # Admin can fetch the project directly without assigned_project_ids restriction
        get_resp = self.client.get(
            "/api/v1/projects/proj-apex",
            headers=self.admin_headers,
        )
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["project_id"], "proj-apex")

    def test_admin_provisions_user_with_claims_and_audit(self) -> None:
        """Scenario: Admin calls POST /api/v1/admin/users to provision a user directly."""
        resp = self.client.post(
            "/api/v1/admin/users",
            headers=self.admin_headers,
            json={
                "email": "manager.siti@enterprise.com",
                "first_name": "Siti",
                "last_name": "Rahmawati",
                "phone_number": "08123456789",
                "country_code": "ID",
                "role": "MANAGER",
                "assigned_project_ids": ["proj-apex"],
            },
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["email"], "manager.siti@enterprise.com")
        self.assertEqual(data["role"], "MANAGER")
        self.assertEqual(data["phone_number"], "+628123456789")
        self.assertEqual(data["assigned_project_ids"], ["proj-apex"])
        self.assertEqual(data["onboarding_status"], "ACTIVE")

        # Verify custom claims synced in Firebase Auth
        claims = get_mock_custom_claims(data["uid"])
        self.assertEqual(claims.get("role"), "MANAGER")
        self.assertEqual(claims.get("assigned_project_ids"), ["proj-apex"])

        # Verify audit ledger event ADMIN_USER_CREATED
        db = get_firestore_client()
        audit_events = [
            s.to_dict()
            for s in db.collection("audit_ledger")
            .where("event_type", "==", "ADMIN_USER_CREATED")
            .stream()
        ]
        self.assertEqual(len(audit_events), 1)
        self.assertEqual(audit_events[0]["actor_uid"], self.admin_uid)
        self.assertEqual(audit_events[0]["target_id"], data["uid"])
        self.assertEqual(audit_events[0]["metadata"]["role"], "MANAGER")

    def test_non_admin_blocked_from_admin_provisioning_with_403(self) -> None:
        """Scenario: EXECUTIVE or MANAGER attempts to call POST /api/v1/admin/users."""
        exec_headers = make_mock_bearer("uid_exec", "exec@enterprise.com", role="EXECUTIVE")
        resp = self.client.post(
            "/api/v1/admin/users",
            headers=exec_headers,
            json={
                "email": "intruder@enterprise.com",
                "first_name": "John",
                "last_name": "Doe",
                "phone_number": "+14155550199",
                "country_code": "US",
                "role": "MANAGER",
            },
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"], "Insufficient role permissions")

    def test_admin_delete_user_hard_purge_and_audit(self) -> None:
        """Scenario: Admin calls DELETE /api/v1/admin/users/{target_uid}."""
        # First provision target user
        prov_resp = self.client.post(
            "/api/v1/admin/users",
            headers=self.admin_headers,
            json={
                "email": "to.terminate@enterprise.com",
                "first_name": "Target",
                "last_name": "User",
                "phone_number": "+628198765432",
                "country_code": "ID",
                "role": "EXTERNAL_STAKEHOLDER",
            },
        )
        target_uid = prov_resp.json()["uid"]

        # Delete user
        del_resp = self.client.delete(
            f"/api/v1/admin/users/{target_uid}",
            headers=self.admin_headers,
        )
        self.assertEqual(del_resp.status_code, 200)
        self.assertEqual(del_resp.json()["status"], "deleted")
        self.assertEqual(del_resp.json()["uid"], target_uid)

        # Confirm document purged from Firestore
        db = get_firestore_client()
        snap = db.collection("users").document(target_uid).get()
        self.assertFalse(snap.exists)

        # Confirm audit ledger event ADMIN_USER_DELETED
        audit_events = [
            s.to_dict()
            for s in db.collection("audit_ledger")
            .where("event_type", "==", "ADMIN_USER_DELETED")
            .stream()
        ]
        self.assertEqual(len(audit_events), 1)
        self.assertEqual(audit_events[0]["actor_uid"], self.admin_uid)
        self.assertEqual(audit_events[0]["target_id"], target_uid)

    def test_admin_self_deletion_prevented_with_400(self) -> None:
        """Scenario: Admin attempts to delete their own active account."""
        resp = self.client.delete(
            f"/api/v1/admin/users/{self.admin_uid}",
            headers=self.admin_headers,
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(
            resp.json()["detail"],
            "Administrators cannot delete their own active account",
        )

    def test_admin_list_and_search_users(self) -> None:
        """Verify GET /api/v1/admin/users lists all accounts and supports filtering."""
        # Provision two distinct users
        self.client.post(
            "/api/v1/admin/users",
            headers=self.admin_headers,
            json={
                "email": "budi.adjudicator@enterprise.com",
                "first_name": "Budi",
                "last_name": "Adjudicator",
                "phone_number": "+628111111111",
                "country_code": "ID",
                "role": "ADJUDICATOR",
            },
        )
        self.client.post(
            "/api/v1/admin/users",
            headers=self.admin_headers,
            json={
                "email": "clara.manager@enterprise.com",
                "first_name": "Clara",
                "last_name": "Manager",
                "phone_number": "+628222222222",
                "country_code": "ID",
                "role": "MANAGER",
            },
        )

        # Search by keyword 'budi'
        search_resp = self.client.get(
            "/api/v1/admin/users?q=budi",
            headers=self.admin_headers,
        )
        self.assertEqual(search_resp.status_code, 200)
        results = search_resp.json()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["email"], "budi.adjudicator@enterprise.com")

        # Filter by role 'MANAGER'
        role_resp = self.client.get(
            "/api/v1/admin/users?role=MANAGER",
            headers=self.admin_headers,
        )
        self.assertEqual(role_resp.status_code, 200)
        mgr_results = role_resp.json()
        self.assertEqual(len(mgr_results), 1)
        self.assertEqual(mgr_results[0]["email"], "clara.manager@enterprise.com")

    def test_project_ai_suggest_groups_and_governance_update(self) -> None:
        """Verify POST /api/v1/projects/{project_id}/ai-suggest-groups and PATCH /api/v1/projects/{project_id}."""
        create_resp = self.client.post(
            "/api/v1/projects",
            headers=self.admin_headers,
            json={
                "project_id": "proj-fin-ledger",
                "name": "Core Banking Ledger Modernization",
                "company_name": "Meridian Bank",
                "description": "Treasury API migration, audit compliance, and payment settlement.",
            },
        )
        self.assertEqual(create_resp.status_code, 201)
        created_proj = create_resp.json()
        self.assertEqual(created_proj["company_name"], "Meridian Bank")
        self.assertGreaterEqual(len(created_proj["canonical_groups"]), 2)

        ai_resp = self.client.post(
            "/api/v1/projects/proj-fin-ledger/ai-suggest-groups",
            headers=self.admin_headers,
            json={
                "name": "Core Banking Ledger Modernization",
                "company_name": "Meridian Bank",
                "description": "Treasury API migration, audit compliance, and payment settlement.",
            },
        )
        self.assertEqual(ai_resp.status_code, 200)
        suggestion = ai_resp.json()
        self.assertEqual(suggestion["project_id"], "proj-fin-ledger")
        self.assertIn("Chief Risk & Compliance Office", suggestion["suggested_canonical_groups"])
        self.assertIn("REGULATORY_COMPLIANCE", suggestion["suggested_risk_categories"])
        self.assertEqual(
            suggestion["recommended_alert_thresholds"]["pulse_drop_delta"], 12
        )

        patch_resp = self.client.patch(
            "/api/v1/projects/proj-fin-ledger",
            headers=self.admin_headers,
            json={
                "canonical_groups": suggestion["suggested_canonical_groups"],
                "alert_thresholds": suggestion["recommended_alert_thresholds"],
            },
        )
        self.assertEqual(patch_resp.status_code, 200)
        updated_proj = patch_resp.json()
        self.assertEqual(
            updated_proj["canonical_groups"],
            suggestion["suggested_canonical_groups"],
        )
        self.assertEqual(
            updated_proj["alert_thresholds"]["pulse_drop_delta"], 12
        )

    def test_admin_ai_governance_summary(self) -> None:
        """Verify GET /api/v1/admin/ai-governance-summary returns synthesized metrics and recommendations."""
        # Provision one quarantined stakeholder and one active manager
        self.client.post(
            "/api/v1/admin/users",
            headers=self.admin_headers,
            json={
                "email": "quarantined.stakeholder@client.com",
                "first_name": "Dana",
                "last_name": "Client",
                "phone_number": "+628123450001",
                "country_code": "ID",
                "role": "EXTERNAL_STAKEHOLDER",
                "assigned_project_ids": [],
            },
        )
        self.client.post(
            "/api/v1/projects",
            headers=self.admin_headers,
            json={
                "project_id": "proj-unassigned",
                "name": "Unassigned Initiative",
            },
        )

        digest_resp = self.client.get(
            "/api/v1/admin/ai-governance-summary",
            headers=self.admin_headers,
        )
        self.assertEqual(digest_resp.status_code, 200)
        digest = digest_resp.json()
        self.assertGreaterEqual(digest["total_users"], 1)
        self.assertGreaterEqual(digest["quarantined_users_count"], 1)
        self.assertGreaterEqual(digest["total_projects"], 1)
        self.assertTrue(len(digest["executive_summary"]) > 10)
        self.assertGreaterEqual(len(digest["key_findings"]), 1)
        self.assertGreaterEqual(len(digest["recommended_actions"]), 1)


if __name__ == "__main__":
    unittest.main()

