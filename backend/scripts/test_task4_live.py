import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import _in_memory_db
from app.core.enums import UserRole
from app.core.firebase import reset_mock_custom_claims
from app.main import create_app
from app.repositories.meeting_repository import MeetingRepository
from app.repositories.sentiment_repository import SentimentRepository
from app.schemas.meeting import DialogueBlockCreate, MeetingCreate, MeetingStatus
from app.schemas.sentiment import CorrectedContextCreate
from app.services.sentiment_service import SentimentService


def run_task4_demo() -> None:
    print("=" * 68)
    print("RUNNING TASK 4 VERIFICATION: SENTIMENT RUBRIC, FEW-SHOT & ON-DEMAND XAI")
    print("=" * 68)

    settings = get_settings()
    settings.use_in_memory_firestore = True
    settings.use_mock_firebase_auth = True

    _in_memory_db.clear()
    reset_mock_custom_claims()

    app = create_app()
    client = TestClient(app)
    db = _in_memory_db
    meeting_repo = MeetingRepository(db=db)
    sentiment_repo = SentimentRepository(db=db)
    sentiment_svc = SentimentService(db=db)

    adjudicator_uid = "uid_adj_demo"
    project_id = "proj-task4-demo"
    token_payload = {
        "uid": adjudicator_uid,
        "email": "adjudicator@enterprise.com",
        "role": UserRole.ADJUDICATOR.value,
        "auth_provider": "password",
        "firebase": {"sign_in_provider": "password"},
    }
    headers = {"Authorization": f"Bearer mock:{json.dumps(token_payload)}"}

    db.collection("users").document(adjudicator_uid).set(
        {
            "uid": adjudicator_uid,
            "email": "adjudicator@enterprise.com",
            "role": UserRole.ADJUDICATOR.value,
            "assigned_project_ids": [project_id],
            "onboarding_status": "ACTIVE",
        }
    )
    db.collection("projects").document(project_id).set(
        {
            "project_id": project_id,
            "name": "Core Banking Modernization",
            "canonical_groups": [
                "Client Legal & Compliance",
                "Client Executive Sponsor",
                "Internal Delivery Team",
            ],
            "owner_uid": adjudicator_uid,
        }
    )

    # 1. Seed a meeting with scrubbed dialogue blocks
    meeting_id = "mtg-demo-task4"
    meeting_repo.create_meeting(
        MeetingCreate(
            meeting_id=meeting_id,
            project_id=project_id,
            title="Q4 Compliance & UAT Sign-off",
            status=MeetingStatus.PROCESSING_POST_MEETING,
        )
    )
    meeting_repo.create_dialogue_block(
        meeting_id=meeting_id,
        block=DialogueBlockCreate(
            block_id="blk-0001",
            sequence_index=0,
            speaker_alias="Sarah Jenkins (Acme Legal)",
            text_scrubbed=(
                "We cannot sign off on the UAT deployment if the audit logs are delayed again. "
                "Reach my office at [PHONE_NUMBER] if we need an emergency review."
            ),
            word_count=26,
        ),
    )
    meeting_repo.create_dialogue_block(
        meeting_id=meeting_id,
        block=DialogueBlockCreate(
            block_id="blk-0002",
            sequence_index=1,
            speaker_alias="David Kim (Delivery Lead)",
            text_scrubbed=(
                "Confirmed, our engineering team resolved the bottleneck and completed the milestone."
            ),
            word_count=11,
        ),
    )

    print("\n--- [STEP 1] 4.1 & 4.2 Cold-Start Zero-Shot Baseline Scoring ---")
    resp_cold = client.post(
        f"/api/v1/meetings/{meeting_id}/analyze",
        headers=headers,
    )
    assert resp_cold.status_code == 200, resp_cold.text
    cold_data = resp_cold.json()
    print(f"Inference Mode: {cold_data['inference_mode']} (Few-Shot Count: {cold_data['few_shot_count']})")
    print(f"Overall Meeting Pulse Score: {cold_data['pulse_score']}")
    print(f"Group Scores:\n{json.dumps(cold_data['group_scores'], indent=2)}")

    print("\n--- [STEP 2] 4.2 Seeding 5 Human Override Vectors (768-dim) & Running Few-Shot ---")
    for i in range(5):
        sample_text = f"UAT audit logs delay and compliance blocker on milestone {i + 1}."
        emb = sentiment_svc.generate_embedding(sample_text)
        sentiment_repo.create_corrected_context(
            CorrectedContextCreate(
                correction_id=f"corr-demo-{i + 1:02d}",
                project_id=project_id,
                group_name="Client Legal & Compliance",
                scrubbed_text=sample_text,
                embedding=emb,
                ai_initial_score=45.0,
                human_adjusted_score=25.0 + i,
                rubric_breakdown={
                    "emotional_valence": 6.0,
                    "delivery_alignment": 6.0,
                    "relationship_trust": 7.0,
                    "momentum_commitment": 6.0 + i,
                },
                adjudicator_uid=adjudicator_uid,
            )
        )

    resp_warm = client.post(
        f"/api/v1/meetings/{meeting_id}/analyze",
        headers=headers,
    )
    assert resp_warm.status_code == 200, resp_warm.text
    warm_data = resp_warm.json()
    print(f"Inference Mode: {warm_data['inference_mode']} (Few-Shot Count: {warm_data['few_shot_count']})")
    print(f"Calibrated Meeting Pulse Score: {warm_data['pulse_score']}")

    print("\n--- [STEP 3] 4.3 On-Demand Explainable AI (XAI) with Substring Offset Verification ---")
    resp_xai = client.post(
        f"/api/v1/meetings/{meeting_id}/blocks/blk-0001/explain",
        headers=headers,
    )
    assert resp_xai.status_code == 200, resp_xai.text
    xai_data = resp_xai.json()
    print(f"Block ID: {xai_data['block_id']} | Pulse Score: {xai_data['pulse_score']}")
    print(f"4-Dimension Rubric Breakdown: {json.dumps(xai_data['rubric_breakdown'])}")
    print("Verified Verbatim Substring Attributions:")
    for attr in xai_data["attributions"]:
        slice_check = xai_data["scrubbed_text"][attr["start_char"] : attr["end_char"]]
        assert slice_check == attr["verbatim_phrase"], "Substring offset mismatch!"
        print(
            f"  - [{attr['start_char']}:{attr['end_char']}] "
            f"(weight={attr['attribution_weight']:+.2f}, dim={attr['rubric_dimension']}): "
            f"\"{attr['verbatim_phrase']}\""
        )

    print("\n" + "=" * 68)
    print("ALL TASK 4 CHECKS PASSED!")
    print("=" * 68)


if __name__ == "__main__":
    run_task4_demo()
