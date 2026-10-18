import hashlib
import hmac
import json
import os
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings
from app.core.database import get_firestore_client
from app.core.enums import UserRole
from app.core.firebase import initialize_firebase_app
from app.main import create_app
from app.repositories.meeting_repository import MeetingRepository
from app.services.dlp_service import DLPService
from fastapi.testclient import TestClient


def run_live_tests() -> None:
    print("=" * 60)
    print("🚀 RUNNING TASK 3 VERIFICATION SUITE")
    print("=" * 60)

    settings = get_settings()
    print(f"[*] Environment: {settings.environment}")
    print(f"[*] GCP Project ID: {settings.gcp_project_id}")
    print(f"[*] Credentials Path: {settings.google_application_credentials}")

    # -------------------------------------------------------------
    # 1. LIVE GOOGLE CLOUD DLP TEST
    # -------------------------------------------------------------
    print("\n--- [TEST 1] Testing Google Cloud DLP Service ---")
    dlp = DLPService()
    test_text = (
        "Alice Smith from Contoso Corp met with Bob Vance. "
        "Reach out at alice@contoso.com or +1 415 555 0199 with SSN 000-12-3456."
    )
    print(f"Input Text:\n  '{test_text}'")
    scrubbed, flags = dlp.deidentify_text(test_text)
    print(f"Scrubbed Output:\n  '{scrubbed}'")
    print(f"Redaction Flags:\n  {flags}")

    assert "alice@contoso.com" not in scrubbed, "Email was not redacted!"
    assert "415 555 0199" not in scrubbed, "Phone number was not redacted!"
    assert "000-12-3456" not in scrubbed, "SSN was not redacted!"
    assert "Alice Smith" in scrubbed, "Speaker name was improperly redacted!"
    assert "Contoso Corp" in scrubbed, "Company name was improperly redacted!"
    assert "Bob Vance" in scrubbed, "Participant name was improperly redacted!"
    print("✅ TEST 1 PASSED: DLP successfully redacted PII while preserving names!")

    # -------------------------------------------------------------
    # 2. BOT DISPATCH TEST (POST /api/v1/meetings/dispatch-bot)
    # -------------------------------------------------------------
    print("\n--- [TEST 2] Testing Bot Dispatch Endpoint ---")
    settings.use_in_memory_firestore = True
    settings.use_mock_firebase_auth = True
    settings.meetstream_webhook_secret = "test-webhook-secret-1234"

    app = create_app()
    client = TestClient(app)
    db = get_firestore_client()

    manager_uid = "mgr_e2e_live_test"
    project_id = "proj-e2e-live"
    token_payload = {
        "uid": manager_uid,
        "email": "manager@enterprise.com",
        "role": UserRole.MANAGER.value,
        "auth_provider": "password",
        "firebase": {"sign_in_provider": "password"},
    }
    bearer_token = f"mock:{json.dumps(token_payload)}"

    db.collection("users").document(manager_uid).set(
        {
            "uid": manager_uid,
            "email": "manager@enterprise.com",
            "role": UserRole.MANAGER.value,
            "assigned_project_ids": [project_id],
            "onboarding_status": "ACTIVE",
        }
    )
    db.collection("projects").document(project_id).set(
        {
            "project_id": project_id,
            "name": "E2E Enterprise Project",
            "owner_uid": manager_uid,
        }
    )

    dispatch_resp = client.post(
        "/api/v1/meetings/dispatch-bot",
        json={
            "meeting_link": "https://meet.google.com/xyz-uvw-rst",
            "project_id": project_id,
            "title": "Board Risk Assessment Review",
            "bot_name": "pRisk AI Executive Notetaker",
        },
        headers={"Authorization": f"Bearer {bearer_token}"},
    )
    assert dispatch_resp.status_code == 200, f"Bot dispatch failed: {dispatch_resp.text}"
    dispatch_data = dispatch_resp.json()
    meeting_id = dispatch_data["meeting_id"]
    bot_id = dispatch_data["bot_id"]
    print(f"Bot Dispatched: meeting_id={meeting_id}, bot_id={bot_id}")
    print("✅ TEST 2 PASSED: Meeting bot successfully dispatched with consent notice!")

    # -------------------------------------------------------------
    # 3. WEBHOOK RECEIVER & TRANSCRIPT PERSISTENCE TEST
    # -------------------------------------------------------------
    print("\n--- [TEST 3] Testing Webhook Ingestion & DLP Pipeline ---")
    webhook_payload = {
        "bot_id": bot_id,
        "meeting_id": meeting_id,
        "custom_attributes": {"meeting_id": meeting_id, "project_id": project_id},
        "transcript": [
            {
                "speaker": "Executive Chair",
                "text": "Welcome everyone. Please update your direct line +1 415 555 9988.",
                "start_time": 0.0,
                "end_time": 4.5,
            },
            {
                "speaker": "Chief Risk Officer",
                "text": "Confirmed. Send confidential audit to secops@enterprise.com right away.",
                "start_time": 5.0,
                "end_time": 9.2,
            },
        ],
    }
    raw_body = json.dumps(webhook_payload).encode("utf-8")
    sig = hmac.new(
        settings.meetstream_webhook_secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()

    wh_resp = client.post(
        "/webhooks/meetstream/completed",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Meetstream-Signature": f"sha256={sig}",
        },
    )
    assert wh_resp.status_code == 200, f"Webhook processing failed: {wh_resp.text}"
    wh_data = wh_resp.json()
    print(f"Webhook Response:\n  {wh_data}")
    assert wh_data["status"] == "success"
    assert wh_data["meeting_status"] == "PROCESSING_POST_MEETING"
    assert wh_data["upstream_transcript_deleted"] is True

    # Check persisted dialogue blocks in Firestore
    repo = MeetingRepository(db=db)
    blocks = repo.list_dialogue_blocks(meeting_id)
    print(f"Persisted Dialogue Blocks Count: {len(blocks)}")
    assert len(blocks) == 2, "Expected 2 dialogue blocks to be persisted"
    assert "[PHONE_NUMBER]" in blocks[0].text_scrubbed
    assert "[EMAIL_ADDRESS]" in blocks[1].text_scrubbed
    assert "Executive Chair" in blocks[0].speaker_alias
    assert "Chief Risk Officer" in blocks[1].speaker_alias

    # Check audit ledger
    audit_events = list(db.collection("audit_ledger").stream())
    print(f"Audit Ledger Events Logged: {len(audit_events)}")
    assert len(audit_events) >= 2, "Expected audit events for dispatch and upstream deletion"

    print("✅ TEST 3 PASSED: Full webhook, DLP scrub, DB commit, and upstream delete flow verified!")
    print("\n" + "=" * 60)
    print("🎉 ALL TASK 3 TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    run_live_tests()
