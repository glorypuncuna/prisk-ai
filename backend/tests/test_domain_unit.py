import json
import sys
import unittest
from pathlib import Path

# Ensure backend package is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.core.database import InMemoryFirestoreClient, record_audit_event
from app.core.firebase import (
    get_mock_custom_claims,
    reset_mock_custom_claims,
    set_firebase_custom_user_claims,
    verify_firebase_id_token,
)
from app.core.phone import normalize_e164_phone
from app.services.email import (
    clear_sent_emails,
    get_sent_emails,
    notify_managers_of_new_registration,
    send_project_invitation_email,
)


class TestTask1DomainLogic(unittest.TestCase):
    def setUp(self) -> None:
        settings = get_settings()
        settings.use_in_memory_firestore = True
        settings.use_mock_firebase_auth = True
        self.db = InMemoryFirestoreClient()
        reset_mock_custom_claims()
        clear_sent_emails()

    def test_e164_phone_normalization_and_validation(self) -> None:
        # National format with country code
        self.assertEqual(normalize_e164_phone("0812-3456-7890", "ID"), "+6281234567890")
        self.assertEqual(normalize_e164_phone("8123 4567", "SG"), "+6581234567")
        self.assertEqual(normalize_e164_phone("(415) 555-2671", "US"), "+14155552671")

        # Already E.164 formatted
        self.assertEqual(normalize_e164_phone("+6281234567890", "ID"), "+6281234567890")

        # Invalid numbers raise ValueError
        with self.assertRaises(ValueError):
            normalize_e164_phone("123-abc", "US")

        with self.assertRaises(ValueError):
            normalize_e164_phone("", "ID")

        with self.assertRaises(ValueError):
            normalize_e164_phone("+012345678", "ID")

    def test_firebase_jwt_verification_and_custom_claims_sync(self) -> None:
        set_firebase_custom_user_claims("uid_budi", {"role": "EXTERNAL_STAKEHOLDER"})
        self.assertEqual(get_mock_custom_claims("uid_budi")["role"], "EXTERNAL_STAKEHOLDER")

        token = f"mock:{json.dumps({'uid': 'uid_budi', 'email': 'budi@enterprise.com'})}"
        claims = verify_firebase_id_token(token)
        self.assertEqual(claims["uid"], "uid_budi")
        self.assertEqual(claims["role"], "EXTERNAL_STAKEHOLDER")

        # Role elevation updates custom claims
        set_firebase_custom_user_claims("uid_budi", {"role": "ADJUDICATOR"})
        refreshed_claims = verify_firebase_id_token(token)
        self.assertEqual(refreshed_claims["role"], "ADJUDICATOR")

        # Invalid/expired token raises ValueError
        with self.assertRaises(ValueError):
            verify_firebase_id_token("expired-token")

    def test_firestore_crud_and_where_filters(self) -> None:
        users = self.db.collection("users")
        users.document("uid_1").set(
            {
                "uid": "uid_1",
                "email": "budi@enterprise.com",
                "role": "EXTERNAL_STAKEHOLDER",
                "assigned_project_ids": [],
            }
        )
        users.document("uid_2").set(
            {
                "uid": "uid_2",
                "email": "mgr@enterprise.com",
                "role": "MANAGER",
                "assigned_project_ids": ["proj-alpha"],
            }
        )

        snap = users.document("uid_1").get()
        self.assertTrue(snap.exists)
        self.assertEqual((snap.to_dict() or {})["email"], "budi@enterprise.com")

        managers = users.where("role", "==", "MANAGER").stream()
        self.assertEqual(len(managers), 1)
        self.assertEqual(managers[0].id, "uid_2")

    def test_audit_ledger_event_recorded(self) -> None:
        event = record_audit_event(
            db=self.db,
            event_type="ROLE_ELEVATED",
            actor_uid="uid_mgr",
            target_id="uid_1",
            metadata={"previous_role": "EXTERNAL_STAKEHOLDER", "new_role": "ADJUDICATOR"},
        )
        self.assertEqual(event["event_type"], "ROLE_ELEVATED")
        snap = self.db.collection("audit_ledger").document(event["event_id"]).get()
        self.assertTrue(snap.exists)
        self.assertEqual((snap.to_dict() or {})["metadata"]["new_role"], "ADJUDICATOR")

    def test_manager_email_alert_and_invitation_dispatch(self) -> None:
        self.db.collection("users").document("uid_mgr").set(
            {
                "uid": "uid_mgr",
                "email": "manager@enterprise.com",
                "role": "MANAGER",
            }
        )
        user_profile = {
            "uid": "uid_new",
            "email": "new.user@enterprise.com",
            "first_name": "Siti",
            "last_name": "Rahma",
            "phone_number": "+6281234567890",
            "role": "EXTERNAL_STAKEHOLDER",
        }
        dispatched = notify_managers_of_new_registration(self.db, user_profile)
        self.assertEqual(len(dispatched), 1)
        self.assertEqual(dispatched[0]["to"], "manager@enterprise.com")
        self.assertEqual(dispatched[0]["type"], "NEW_USER_REGISTRATION_ALERT")

        inv_email = send_project_invitation_email(
            self.db,
            invitation={
                "invitation_id": "inv_123",
                "project_id": "proj-alpha",
                "invitee_email": "new.user@enterprise.com",
                "invited_by_uid": "uid_mgr",
            },
            project_name="Project Alpha",
        )
        self.assertEqual(inv_email["type"], "PROJECT_INVITATION")
        self.assertEqual(len(get_sent_emails()), 2)


if __name__ == "__main__":
    unittest.main()
