import json
import unittest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import get_firestore_client
from app.core.firebase import get_mock_custom_claims, reset_mock_custom_claims
from app.main import app
from app.services.email import clear_sent_emails, get_sent_emails


def make_mock_bearer(
    uid: str,
    email: str,
    role: str | None = None,
    provider: str = "password",
) -> dict[str, str]:
    payload: dict[str, object] = {
        "uid": uid,
        "email": email,
        "auth_provider": provider,
        "firebase": {"sign_in_provider": provider},
    }
    if role:
        payload["role"] = role
    token = f"mock:{json.dumps(payload)}"
    return {"Authorization": f"Bearer {token}"}


class TestUserAuthenticationAndInvitations(unittest.TestCase):
    def setUp(self) -> None:
        settings = get_settings()
        settings.use_in_memory_firestore = True
        settings.use_mock_firebase_auth = True
        db = get_firestore_client()
        db.clear()
        reset_mock_custom_claims()
        clear_sent_emails()
        self.client = TestClient(app)

    def test_1_email_password_registration_and_e164_normalization(self) -> None:
        headers = make_mock_bearer("uid_budi", "Budi.Santoso@Enterprise.com", provider="password")
        response = self.client.post(
            "/api/v1/auth/register-profile",
            headers=headers,
            json={
                "first_name": "Budi",
                "last_name": "Santoso",
                "phone_number": "0812-3456-7890",
                "country_code": "ID",
            },
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["uid"], "uid_budi")
        self.assertEqual(data["email"], "budi.santoso@enterprise.com")
        self.assertEqual(data["phone_number"], "+6281234567890")
        self.assertEqual(data["role"], "EXTERNAL_STAKEHOLDER")
        self.assertEqual(data["assigned_project_ids"], [])
        self.assertEqual(data["onboarding_status"], "QUARANTINED_PENDING_INVITATION")

        # Verify custom claims synced
        claims = get_mock_custom_claims("uid_budi")
        self.assertEqual(claims.get("role"), "EXTERNAL_STAKEHOLDER")

        # Verify manager alert email sent
        emails = get_sent_emails()
        self.assertEqual(len(emails), 1)
        self.assertEqual(emails[0]["type"], "NEW_USER_REGISTRATION_ALERT")
        self.assertEqual(emails[0]["target_uid"], "uid_budi")

    def test_2_sso_google_and_microsoft_registration(self) -> None:
        headers = make_mock_bearer(
            "uid_sso_1",
            "alice@workspace.enterprise.com",
            provider="google.com",
        )
        # Before profile registration, GET /api/v1/auth/me returns 404
        me_before = self.client.get("/api/v1/auth/me", headers=headers)
        self.assertEqual(me_before.status_code, 404)

        reg = self.client.post(
            "/api/v1/auth/register-profile",
            headers=headers,
            json={
                "first_name": "Alice",
                "last_name": "Tan",
                "phone_number": "+6581234567",
                "country_code": "SG",
            },
        )
        self.assertEqual(reg.status_code, 201)
        self.assertEqual(reg.json()["auth_provider"], "google.com")
        self.assertEqual(reg.json()["phone_number"], "+6581234567")

    def test_3_invalid_phone_number_rejected_with_422(self) -> None:
        headers = make_mock_bearer("uid_invalid_phone", "test@enterprise.com")
        response = self.client.post(
            "/api/v1/auth/register-profile",
            headers=headers,
            json={
                "first_name": "Invalid",
                "last_name": "Phone",
                "phone_number": "123-abc",
                "country_code": "US",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_4_missing_or_expired_token_returns_401(self) -> None:
        no_auth = self.client.get("/api/v1/auth/me")
        self.assertEqual(no_auth.status_code, 401)
        self.assertEqual(no_auth.json()["detail"], "Invalid or expired authentication token")

        expired_auth = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer expired-token"},
        )
        self.assertEqual(expired_auth.status_code, 401)

    def test_5_unauthorized_self_elevation_blocked_with_403(self) -> None:
        user_headers = make_mock_bearer("uid_ext", "ext@enterprise.com")
        self.client.post(
            "/api/v1/auth/register-profile",
            headers=user_headers,
            json={
                "first_name": "Ext",
                "last_name": "User",
                "phone_number": "+6281299998888",
                "country_code": "ID",
            },
        )

        patch_resp = self.client.patch(
            "/api/v1/users/uid_ext/role",
            headers=user_headers,
            json={"role": "EXECUTIVE"},
        )
        self.assertEqual(patch_resp.status_code, 403)
        self.assertEqual(patch_resp.json()["detail"], "Insufficient role permissions")

    def test_6_authorized_role_elevation_syncs_claims_and_logs_audit(self) -> None:
        # Register external stakeholder
        ext_headers = make_mock_bearer("uid_analyst", "analyst@enterprise.com")
        self.client.post(
            "/api/v1/auth/register-profile",
            headers=ext_headers,
            json={
                "first_name": "Rina",
                "last_name": "Wijaya",
                "phone_number": "+6281122334455",
                "country_code": "ID",
            },
        )

        # Manager elevates Rina to ADJUDICATOR
        mgr_headers = make_mock_bearer("uid_mgr", "mgr@enterprise.com", role="MANAGER")
        elevate_resp = self.client.patch(
            "/api/v1/users/uid_analyst/role",
            headers=mgr_headers,
            json={
                "role": "ADJUDICATOR",
                "assigned_project_ids": ["proj-alpha"],
            },
        )
        self.assertEqual(elevate_resp.status_code, 200)
        body = elevate_resp.json()
        self.assertEqual(body["role"], "ADJUDICATOR")
        self.assertEqual(body["assigned_project_ids"], ["proj-alpha"])
        self.assertEqual(body["onboarding_status"], "ACTIVE")

        # Check Firebase custom claims and audit_ledger
        self.assertEqual(get_mock_custom_claims("uid_analyst").get("role"), "ADJUDICATOR")
        db = get_firestore_client()
        audit_events = [
            s.to_dict()
            for s in db.collection("audit_ledger")
            .where("event_type", "==", "ROLE_ELEVATED")
            .stream()
        ]
        self.assertEqual(len(audit_events), 1)
        self.assertEqual(audit_events[0]["actor_uid"], "uid_mgr")
        self.assertEqual(audit_events[0]["target_id"], "uid_analyst")

    def test_7_quarantined_project_access_and_invitation_acceptance_flow(self) -> None:
        mgr_headers = make_mock_bearer("uid_mgr", "manager@enterprise.com", role="MANAGER")
        # Create project proj-alpha
        create_proj = self.client.post(
            "/api/v1/projects",
            headers=mgr_headers,
            json={
                "project_id": "proj-alpha",
                "name": "Project Alpha Migration",
                "description": "Core banking migration risk oversight",
            },
        )
        self.assertEqual(create_proj.status_code, 201)

        # Register new stakeholder
        stakeholder_headers = make_mock_bearer("uid_stake", "stakeholder@client.com")
        self.client.post(
            "/api/v1/auth/register-profile",
            headers=stakeholder_headers,
            json={
                "first_name": "Dimas",
                "last_name": "Pratama",
                "phone_number": "+6281344556677",
                "country_code": "ID",
            },
        )

        # Stakeholder attempts to view uninvited project -> 403 "Access Pending Project Invitation"
        denied = self.client.get("/api/v1/projects/proj-alpha", headers=stakeholder_headers)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["detail"], "Access Pending Project Invitation")

        # Manager invites stakeholder@client.com to proj-alpha
        inv_resp = self.client.post(
            "/api/v1/projects/proj-alpha/invitations",
            headers=mgr_headers,
            json={"invitee_email": "stakeholder@client.com"},
        )
        self.assertEqual(inv_resp.status_code, 201)
        invitation_id = inv_resp.json()["invitation_id"]

        # Stakeholder lists their pending invitations
        my_invites = self.client.get(
            "/api/v1/projects/invitations/me",
            headers=stakeholder_headers,
        )
        self.assertEqual(my_invites.status_code, 200)
        self.assertEqual(len(my_invites.json()), 1)

        # Stakeholder accepts the invitation
        accept_resp = self.client.post(
            f"/api/v1/projects/proj-alpha/invitations/{invitation_id}/accept",
            headers=stakeholder_headers,
        )
        self.assertEqual(accept_resp.status_code, 200)
        updated_profile = accept_resp.json()
        self.assertIn("proj-alpha", updated_profile["assigned_project_ids"])
        self.assertEqual(updated_profile["onboarding_status"], "ACTIVE")

        # Stakeholder can now access proj-alpha
        allowed = self.client.get("/api/v1/projects/proj-alpha", headers=stakeholder_headers)
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.json()["project_id"], "proj-alpha")

    def test_8_project_vector_diagnostics(self) -> None:
        from app.repositories.sentiment_repository import SentimentRepository
        from app.schemas.sentiment import SentimentCalibrationCreate

        mgr_headers = make_mock_bearer("uid_mgr_diag", "mgr.diag@enterprise.com", role="MANAGER")
        # Create project
        create_resp = self.client.post(
            "/api/v1/projects",
            headers=mgr_headers,
            json={
                "project_id": "proj-diag-01",
                "name": "Vector Diagnostics Project",
                "canonical_groups": ["BUYER", "VENDOR", "INTERNAL"],
            },
        )
        self.assertEqual(create_resp.status_code, 201)

        # Inspect zero-shot diagnostics
        diag_resp = self.client.get(
            "/api/v1/projects/proj-diag-01/vector-diagnostics",
            headers=mgr_headers,
        )
        self.assertEqual(diag_resp.status_code, 200)
        diag = diag_resp.json()
        self.assertEqual(diag["project_id"], "proj-diag-01")
        self.assertEqual(diag["embedding_dimension"], 768)
        self.assertEqual(diag["total_exemplars"], 0)
        self.assertEqual(diag["inference_mode"], "ZERO_SHOT")
        self.assertFalse(diag["nearest_neighbor_readiness"])

        # Add a calibration exemplar
        sentiment_repo = SentimentRepository(db=get_firestore_client())
        sentiment_repo.create_calibration(
            SentimentCalibrationCreate(
                calibration_id="cal-test-01",
                project_id="proj-diag-01",
                group_name="BUYER",
                dialogue_text="We require delivery milestone sign-off by end of month.",
                benchmark_score=78.5,
                rubric_breakdown={
                    "emotional_valence": 20.0,
                    "delivery_alignment": 20.0,
                    "relationship_trust": 20.0,
                    "momentum_commitment": 18.5,
                },
                embedding=[0.01] * 768,
            )
        )

        # Re-inspect vector diagnostics
        diag_resp2 = self.client.get(
            "/api/v1/projects/proj-diag-01/vector-diagnostics",
            headers=mgr_headers,
        )
        self.assertEqual(diag_resp2.status_code, 200)
        diag2 = diag_resp2.json()
        self.assertEqual(diag2["total_exemplars"], 1)
        self.assertEqual(diag2["inference_mode"], "FEW_SHOT")
        self.assertTrue(diag2["nearest_neighbor_readiness"])
        self.assertEqual(diag2["group_coverage"], {"BUYER": 1})
        self.assertEqual(len(diag2["recent_exemplars"]), 1)
        self.assertEqual(diag2["recent_exemplars"][0]["calibration_id"], "cal-test-01")


if __name__ == "__main__":
    unittest.main()
