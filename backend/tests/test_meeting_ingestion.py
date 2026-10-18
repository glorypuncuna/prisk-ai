import hashlib
import hmac
import json
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import _in_memory_db
from app.core.enums import UserRole
from app.core.firebase import reset_mock_custom_claims
from app.main import create_app
from app.repositories.meeting_repository import MeetingRepository
from app.schemas.meeting import DialogueBlockCreate, MeetingCreate, MeetingStatus
from app.services.dlp_service import DLPService
from app.services.meetstream_service import MeetStreamService


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


class TestMeetingIngestionAndDLP(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = get_settings()
        self.settings.use_in_memory_firestore = True
        self.settings.use_mock_firebase_auth = True
        self.settings.meetstream_webhook_secret = "test-webhook-secret-key-12345"

        _in_memory_db.clear()
        reset_mock_custom_claims()

        self.db = _in_memory_db
        self.meeting_repo = MeetingRepository(db=self.db)
        self.app = create_app()
        self.client = TestClient(self.app)

        # Seed test manager user
        self.manager_uid = "uid_manager_test"
        self.project_id = "proj-test-dlp"
        self.manager_headers = make_mock_bearer(
            self.manager_uid, "manager@test.com", UserRole.MANAGER.value
        )
        self.db.collection("users").document(self.manager_uid).set(
            {
                "uid": self.manager_uid,
                "email": "manager@test.com",
                "role": UserRole.MANAGER.value,
                "assigned_project_ids": [self.project_id],
                "onboarding_status": "ACTIVE",
            }
        )
        self.db.collection("projects").document(self.project_id).set(
            {
                "project_id": self.project_id,
                "name": "Test Project DLP",
                "owner_uid": self.manager_uid,
            }
        )

        # Seed quarantined stakeholder user
        self.stakeholder_uid = "uid_stakeholder_test"
        self.stakeholder_headers = make_mock_bearer(
            self.stakeholder_uid, "stakeholder@test.com", UserRole.EXTERNAL_STAKEHOLDER.value
        )
        self.db.collection("users").document(self.stakeholder_uid).set(
            {
                "uid": self.stakeholder_uid,
                "email": "stakeholder@test.com",
                "role": UserRole.EXTERNAL_STAKEHOLDER.value,
                "assigned_project_ids": [],
                "onboarding_status": "QUARANTINED",
            }
        )


    def test_dispatch_meeting_bot_success(self) -> None:
        """3.1 Test POST /api/v1/meetings/dispatch-bot with Google Meet link and chat consent notice."""
        payload = {
            "meeting_link": "https://meet.google.com/abc-defg-hij",
            "project_id": self.project_id,
            "title": "Quarterly Vendor Risk Sync",
            "bot_name": "pRisk AI Compliance Notetaker",
            "chat_consent_notice": "pRisk AI is recording meeting sentiment with automated DLP redaction.",
        }
        resp = self.client.post(
            "/api/v1/meetings/dispatch-bot",
            json=payload,
            headers=self.manager_headers,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertIn("meeting_id", data)
        self.assertEqual(data["status"], "DISPATCHED")
        self.assertEqual(data["chat_consent_notice"], payload["chat_consent_notice"])
        self.assertTrue(data["bot_id"].startswith("bot-"))

        # Verify meeting saved in Firestore with LIVE status
        meeting_doc = self.meeting_repo.get_meeting(data["meeting_id"])
        self.assertIsNotNone(meeting_doc)
        self.assertEqual(meeting_doc.status, MeetingStatus.LIVE.value)

    def test_dispatch_meeting_bot_forbidden_for_stakeholder(self) -> None:
        """3.1 Test that unprivileged users cannot dispatch bots."""
        payload = {
            "meeting_link": "https://meet.google.com/abc-defg-hij",
            "project_id": self.project_id,
        }
        resp = self.client.post(
            "/api/v1/meetings/dispatch-bot",
            json=payload,
            headers=self.stakeholder_headers,
        )
        self.assertEqual(resp.status_code, 403)

    def test_webhook_hmac_signature_validation(self) -> None:
        """3.2 Test HMAC-SHA256 signature verification on /webhooks/meetstream/completed."""
        payload = {
            "bot_id": "bot-test-hmac",
            "transcript_id": "tr-test-hmac",
            "custom_attributes": {"meeting_id": "meet-test-hmac", "project_id": self.project_id},
        }
        body_bytes = json.dumps(payload).encode("utf-8")
        valid_sig = hmac.new(
            self.settings.meetstream_webhook_secret.encode("utf-8"),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()

        # 1. Invalid signature should fail with 401
        invalid_resp = self.client.post(
            "/webhooks/meetstream/completed",
            content=body_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Meetstream-Signature": "sha256=invalidhexsignature0000000000",
            },
        )
        self.assertEqual(invalid_resp.status_code, 401)

        # 2. Valid signature should succeed
        valid_resp = self.client.post(
            "/webhooks/meetstream/completed",
            content=body_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Meetstream-Signature": f"sha256={valid_sig}",
            },
        )
        self.assertEqual(valid_resp.status_code, 200, valid_resp.text)
        res_data = valid_resp.json()
        self.assertEqual(res_data["status"], "success")

    def test_dlp_scrubbing_preserves_person_and_company_names(self) -> None:
        """3.3 Test that DLP pass redacts emails, phones, CCs while preserving person and company names."""
        dlp = DLPService()
        raw_text = (
            "Alice Smith from Acme Corp reported that our vendor email is contact@vendor.com "
            "and billing phone is 415-555-0199 with card 4111-2222-3333-4444."
        )
        scrubbed, flags = dlp.deidentify_text(raw_text)

        # Verify sensitive contact/financial tokens redacted
        self.assertNotIn("contact@vendor.com", scrubbed)
        self.assertNotIn("415-555-0199", scrubbed)
        self.assertNotIn("4111-2222-3333-4444", scrubbed)
        self.assertIn("[EMAIL_ADDRESS]", scrubbed)
        self.assertIn("[PHONE_NUMBER]", scrubbed)
        self.assertIn("[CREDIT_CARD_NUMBER]", scrubbed)

        # Verify person and company names are PRESERVED
        self.assertIn("Alice Smith", scrubbed)
        self.assertIn("Acme Corp", scrubbed)

        self.assertIn("EMAIL_ADDRESS", flags)
        self.assertIn("PHONE_NUMBER", flags)
        self.assertIn("CREDIT_CARD_NUMBER", flags)

    def test_transactional_write_and_upstream_transcript_deletion(self) -> None:
        """3.4 & 3.5 Test transactional Firestore write and subsequent upstream transcript deletion."""
        meeting_id = "meet-transactional-test"
        bot_id = "bot-to-delete-123"

        self.meeting_repo.create_meeting(
            MeetingCreate(
                meeting_id=meeting_id,
                project_id=self.project_id,
                title="Google Meet Pipeline Ingestion",
                status=MeetingStatus.LIVE,
            )
        )
        # Update with bot_id
        self.meeting_repo.update_meeting(meeting_id, {"meetstream_bot_id": bot_id})

        transcript = [
            {
                "speaker": "John Doe",
                "text": "Hello, my phone is +1 415 555 1234 and I represent MegaCorp.",
                "start_time": 0.0,
                "end_time": 4.0,
            },
            {
                "speaker": "Sarah Jane",
                "text": "Thanks John. Please send invoice to billing@megacorp.com.",
                "start_time": 4.5,
                "end_time": 8.5,
            },
        ]

        payload = {
            "bot_id": bot_id,
            "meeting_id": meeting_id,
            "transcript": transcript,
        }
        body_bytes = json.dumps(payload).encode("utf-8")
        sig = hmac.new(
            self.settings.meetstream_webhook_secret.encode("utf-8"),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()

        with patch.object(MeetStreamService, "delete_upstream_transcript", return_value=True) as mock_delete:
            resp = self.client.post(
                "/webhooks/meetstream/completed",
                content=body_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-Meetstream-Signature": f"sha256={sig}",
                },
            )
            self.assertEqual(resp.status_code, 200, resp.text)

            # Check that upstream transcript delete was called strictly after
            mock_delete.assert_called_once_with(bot_id)

        # Verify meeting status is transitioned to PENDING_ADJUDICATION via automatic AI handoff
        meeting = self.meeting_repo.get_meeting(meeting_id)
        self.assertIsNotNone(meeting)
        self.assertEqual(meeting.status, MeetingStatus.PENDING_ADJUDICATION.value)
        self.assertIsNotNone(meeting.pulse_score)

        # Verify dialogue blocks were persisted in Firestore subcollection
        blocks = self.meeting_repo.list_dialogue_blocks(meeting_id)
        self.assertEqual(len(blocks), 2)
        self.assertIn("[PHONE_NUMBER]", blocks[0].text_scrubbed)
        self.assertIn("John Doe", blocks[0].speaker_alias)
        self.assertIn("[EMAIL_ADDRESS]", blocks[1].text_scrubbed)
        self.assertIn("Sarah Jane", blocks[1].speaker_alias)

    def test_abort_upstream_deletion_on_database_write_failure(self) -> None:
        """3.5 Test that upstream deletion is aborted if Firestore write raises an exception."""
        meeting_id = "meet-failure-test"
        bot_id = "bot-should-not-delete"

        payload = {
            "bot_id": bot_id,
            "meeting_id": meeting_id,
            "transcript": [{"speaker": "User", "text": "Testing failure handling"}],
        }
        body_bytes = json.dumps(payload).encode("utf-8")
        sig = hmac.new(
            self.settings.meetstream_webhook_secret.encode("utf-8"),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()

        # Force save_scrubbed_dialogue_blocks to raise an exception
        with patch.object(
            MeetingRepository,
            "save_scrubbed_dialogue_blocks",
            side_effect=RuntimeError("Firestore connection timeout"),
        ):
            with patch.object(MeetStreamService, "delete_upstream_transcript") as mock_delete:
                resp = self.client.post(
                    "/webhooks/meetstream/completed",
                    content=body_bytes,
                    headers={
                        "Content-Type": "application/json",
                        "X-Meetstream-Signature": f"sha256={sig}",
                    },
                )
                self.assertEqual(resp.status_code, 500)
                # Ensure upstream deletion was NEVER called
                mock_delete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
