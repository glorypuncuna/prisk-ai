import json
import unittest

from fastapi.testclient import TestClient

from app.core.bigquery import (
    _in_memory_bq_audit_events,
    _in_memory_bq_golden_records,
    _in_memory_bq_pulse_history,
)
from app.core.config import get_settings
from app.core.database import _in_memory_db
from app.core.enums import UserRole
from app.core.firebase import reset_mock_custom_claims
from app.main import create_app
from app.repositories.meeting_repository import MeetingRepository
from app.repositories.risk_repository import RiskRepository
from app.repositories.sentiment_repository import SentimentRepository
from app.schemas.meeting import DialogueBlockCreate, MeetingCreate, MeetingStatus
from app.schemas.risk import RiskCategory, RiskRegisterCreate, RiskStatus
from app.services.adjudication_service import compute_deterministic_rollups


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


class TestHITLAdjudicationAndRollups(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = get_settings()
        self.settings.use_in_memory_firestore = True
        self.settings.use_mock_firebase_auth = True

        _in_memory_db.clear()
        _in_memory_bq_golden_records.clear()
        _in_memory_bq_pulse_history.clear()
        _in_memory_bq_audit_events.clear()
        reset_mock_custom_claims()

        self.db = _in_memory_db
        self.meeting_repo = MeetingRepository(db=self.db)
        self.sentiment_repo = SentimentRepository(db=self.db)
        self.risk_repo = RiskRepository(db=self.db)
        self.app = create_app()
        self.client = TestClient(self.app)

        self.project_id = "proj-adjudication"
        self.adjudicator_uid = "uid_adjudicator_task5"
        self.adjudicator_headers = make_mock_bearer(
            self.adjudicator_uid,
            "adjudicator@enterprise.com",
            UserRole.ADJUDICATOR.value,
        )

        self.db.collection("users").document(self.adjudicator_uid).set(
            {
                "uid": self.adjudicator_uid,
                "email": "adjudicator@enterprise.com",
                "role": UserRole.ADJUDICATOR.value,
                "assigned_project_ids": [self.project_id],
                "onboarding_status": "ACTIVE",
            }
        )
        self.db.collection("projects").document(self.project_id).set(
            {
                "project_id": self.project_id,
                "name": "Core Banking Modernization",
                "canonical_groups": [
                    "Client Legal & Compliance",
                    "Client Executive Sponsor",
                    "Internal Delivery Team",
                ],
                "owner_uid": self.adjudicator_uid,
            }
        )

        self.meeting_id = "mtg-hitl-01"
        self.meeting_repo.create_meeting(
            MeetingCreate(
                meeting_id=self.meeting_id,
                project_id=self.project_id,
                title="Q4 Compliance Gate Review",
                status=MeetingStatus.PENDING_ADJUDICATION,
                pulse_score=55.0,
                ephemeral_speaker_map={"ms_spk_01": "BUYER", "ms_spk_02": "INTERNAL"},
            )
        )
        self.meeting_repo.create_dialogue_block(
            meeting_id=self.meeting_id,
            block=DialogueBlockCreate(
                block_id="blk-0001",
                sequence_index=0,
                speaker_alias="Sarah Jenkins",
                display_speaker_label="Sarah Jenkins",
                ephemeral_speaker_account_id="ms_spk_01",
                group_id="BUYER",
                group_name="BUYER",
                text_scrubbed="We cannot sign off on UAT deployment. The audit logs are delayed again [PHONE_NUMBER].",
                word_count=14,
                dlp_redaction_flags=["PHONE_NUMBER"],
                sentiment_score=34.0,
                ai_initial_score=34.0,
                rubric_scores={
                    "emotional_valence": 8,
                    "delivery_alignment": 7,
                    "relationship_trust": 9,
                    "momentum_commitment": 10,
                },
            ),
        )
        self.meeting_repo.create_dialogue_block(
            meeting_id=self.meeting_id,
            block=DialogueBlockCreate(
                block_id="blk-0002",
                sequence_index=1,
                speaker_alias="Sarah Jenkins",
                display_speaker_label="Sarah Jenkins",
                ephemeral_speaker_account_id="ms_spk_01",
                group_id="BUYER",
                group_name="BUYER",
                text_scrubbed="Please send the updated compliance schedule before Friday.",
                word_count=8,
                sentiment_score=46.0,
                ai_initial_score=46.0,
                rubric_scores={
                    "emotional_valence": 11,
                    "delivery_alignment": 11,
                    "relationship_trust": 12,
                    "momentum_commitment": 12,
                },
            ),
        )
        self.meeting_repo.create_dialogue_block(
            meeting_id=self.meeting_id,
            block=DialogueBlockCreate(
                block_id="blk-0003",
                sequence_index=2,
                speaker_alias="David Kim",
                display_speaker_label="David Kim",
                ephemeral_speaker_account_id="ms_spk_02",
                group_id="INTERNAL",
                group_name="INTERNAL",
                text_scrubbed="Confirmed, our engineering team resolved the bottleneck and completed the milestone.",
                word_count=11,
                sentiment_score=80.0,
                ai_initial_score=80.0,
                rubric_scores={
                    "emotional_valence": 20,
                    "delivery_alignment": 20,
                    "relationship_trust": 20,
                    "momentum_commitment": 20,
                },
            ),
        )

    def test_5_2_bubble_split_inherits_parent_scores_and_logs_audit(self) -> None:
        """5.2 Verify POST /api/v1/meetings/{id}/blocks/{id}/split creates two child blocks inheriting parent rubric/score/group."""
        split_idx = 38  # After "We cannot sign off on UAT deployment."
        resp = self.client.post(
            f"/api/v1/meetings/{self.meeting_id}/blocks/blk-0001/split",
            json={"split_char_index": split_idx},
            headers=self.adjudicator_headers,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["parent_block_id"], "blk-0001")
        self.assertEqual(len(data["child_blocks"]), 2)

        child_a, child_b = data["child_blocks"]
        self.assertEqual(child_a["block_id"], "blk-0001a")
        self.assertEqual(child_b["block_id"], "blk-0001b")
        self.assertEqual(child_a["sentiment_score"], 34.0)
        self.assertEqual(child_b["sentiment_score"], 34.0)
        self.assertEqual(child_a["group_name"], "BUYER")
        self.assertEqual(child_b["group_name"], "BUYER")
        self.assertTrue(child_a["is_split"])
        self.assertTrue(child_b["is_split"])
        self.assertEqual(child_a["parent_block_id"], "blk-0001")
        self.assertEqual(child_b["parent_block_id"], "blk-0001")

        # Verify total blocks is now 4 in sequential order
        self.assertEqual(len(data["blocks"]), 4)
        seq_indices = [b["sequence_index"] for b in data["blocks"]]
        self.assertEqual(seq_indices, [0, 1, 2, 3])

        # Verify BUBBLE_SPLIT event in audit_ledger
        audit_snaps = list(
            self.db.collection("audit_ledger")
            .where("event_type", "==", "BUBBLE_SPLIT")
            .stream()
        )
        self.assertEqual(len(audit_snaps), 1)

    def test_5_3_ephemeral_session_grouping_updates_unpinned_blocks(self) -> None:
        """5.3 Verify PATCH /api/v1/meetings/{id}/session-grouping auto-updates all unpinned blocks from the same speaker."""
        # Pin blk-0002 to a custom group first so we can verify pinned blocks are untouched
        pin_resp = self.client.patch(
            f"/api/v1/meetings/{self.meeting_id}/blocks/blk-0002/score",
            json={"group_name": "Client Executive Sponsor", "is_pinned": True},
            headers=self.adjudicator_headers,
        )
        self.assertEqual(pin_resp.status_code, 200, pin_resp.text)

        # Assign speaker ms_spk_01 to "Client Legal & Compliance"
        resp = self.client.patch(
            f"/api/v1/meetings/{self.meeting_id}/session-grouping",
            json={
                "ephemeral_speaker_account_id": "ms_spk_01",
                "group_name": "Client Legal & Compliance",
            },
            headers=self.adjudicator_headers,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()

        self.assertEqual(
            data["ephemeral_speaker_map"]["ms_spk_01"],
            "Client Legal & Compliance",
        )
        # blk-0001 is unpinned -> updated; blk-0002 is pinned -> preserved
        self.assertIn("blk-0001", data["updated_block_ids"])
        self.assertNotIn("blk-0002", data["updated_block_ids"])

        blocks_by_id = {b["block_id"]: b for b in data["blocks"]}
        self.assertEqual(
            blocks_by_id["blk-0001"]["group_name"], "Client Legal & Compliance"
        )
        self.assertEqual(
            blocks_by_id["blk-0002"]["group_name"], "Client Executive Sponsor"
        )

    def test_5_4_deterministic_word_count_weighted_rollups(self) -> None:
        """5.4 Verify deterministic word-count-weighted Group Pulse Score and arithmetic mean Overall Pulse Score."""
        sample_blocks = [
            {"group_name": "Group A", "sentiment_score": 20.0, "word_count": 10},
            {"group_name": "Group A", "sentiment_score": 80.0, "word_count": 30},
            {"group_name": "Group B", "sentiment_score": 90.0, "word_count": 5},
        ]
        # Group A weighted average: (20*10 + 80*30) / 40 = 2600 / 40 = 65.0
        # Group B weighted average: (90*5) / 5 = 90.0
        # Overall Meeting Pulse: (65.0 + 90.0) / 2 = 77.5
        overall, groups = compute_deterministic_rollups(sample_blocks)
        self.assertEqual(groups["Group A"]["pulse_score"], 65.0)
        self.assertEqual(groups["Group B"]["pulse_score"], 90.0)
        self.assertEqual(overall, 77.5)

        # Verify slider override endpoint updates score, marks is_human_overridden, and recalculates rollups
        resp = self.client.patch(
            f"/api/v1/meetings/{self.meeting_id}/blocks/blk-0001/score",
            json={"final_pulse_score": 20.0},
            headers=self.adjudicator_headers,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        res_data = resp.json()
        self.assertEqual(res_data["block"]["sentiment_score"], 20.0)
        self.assertTrue(res_data["block"]["is_human_overridden"])
        # BUYER has blk-0001 (14 words, score 20) + blk-0002 (8 words, score 46)
        # BUYER weighted avg = (280 + 368) / 22 = 648 / 22 = 29.5
        # INTERNAL has blk-0003 (11 words, score 80) -> 80.0
        # Overall = (29.5 + 80.0) / 2 = 54.8
        self.assertEqual(res_data["group_scores"]["BUYER"]["pulse_score"], 29.5)
        self.assertEqual(res_data["group_scores"]["INTERNAL"]["pulse_score"], 80.0)
        self.assertEqual(res_data["pulse_score"], 54.8)

    def test_5_5_commit_golden_record_strips_speakers_embeds_overrides_and_streams_bq(
        self,
    ) -> None:
        """5.5 Verify POST /api/v1/meetings/{id}/commit-golden-record strips ephemeral speaker IDs, saves corrected_contexts, promotes risks, and streams to BigQuery."""
        # Create a draft risk for this meeting
        self.risk_repo.create_risk(
            RiskRegisterCreate(
                risk_id="RSK-HITL-01",
                project_id=self.project_id,
                meeting_id=self.meeting_id,
                title="Audit Log Delay Risk",
                description="Delayed audit logs blocking UAT sign-off.",
                category=RiskCategory.COMPLIANCE,
                status=RiskStatus.DRAFT_PENDING_ADJUDICATION,
                impact=4,
                probability=4,
            )
        )

        # Override blk-0001 score via slider
        self.client.patch(
            f"/api/v1/meetings/{self.meeting_id}/blocks/blk-0001/score",
            json={"final_pulse_score": 22.0, "group_name": "Client Legal & Compliance"},
            headers=self.adjudicator_headers,
        )

        # Commit Golden Record
        commit_resp = self.client.post(
            f"/api/v1/meetings/{self.meeting_id}/commit-golden-record",
            json={"approved_risk_ids": ["RSK-HITL-01"]},
            headers=self.adjudicator_headers,
        )
        self.assertEqual(commit_resp.status_code, 200, commit_resp.text)
        commit_data = commit_resp.json()

        self.assertEqual(commit_data["status"], MeetingStatus.GOLDEN_RECORD.value)
        self.assertIsNone(commit_data["ephemeral_speaker_map"])
        self.assertEqual(commit_data["corrected_contexts_saved"], 1)
        self.assertEqual(commit_data["promoted_risk_ids"], ["RSK-HITL-01"])
        self.assertEqual(commit_data["bigquery_rows_streamed"], 3)

        # Verify Firestore meeting record stripped ephemeral_speaker_map and participants
        locked_meeting = self.meeting_repo.get_meeting(self.meeting_id)
        self.assertIsNotNone(locked_meeting)
        self.assertEqual(locked_meeting.status, MeetingStatus.GOLDEN_RECORD.value)
        self.assertIsNone(locked_meeting.ephemeral_speaker_map)
        self.assertEqual(locked_meeting.participants, [])

        # Verify all dialogue blocks stripped ephemeral_speaker_account_id and speaker_alias
        final_blocks = self.meeting_repo.list_dialogue_blocks(self.meeting_id)
        for b in final_blocks:
            self.assertIsNone(b.ephemeral_speaker_account_id)
            self.assertIsNone(b.speaker_alias)

        # Verify 768-dim CorrectedContext was persisted
        contexts = self.sentiment_repo.list_corrected_contexts(
            project_id=self.project_id
        )
        self.assertEqual(len(contexts), 1)
        self.assertEqual(contexts[0].human_adjusted_score, 22.0)
        self.assertEqual(contexts[0].ai_initial_score, 34.0)
        self.assertIsNotNone(contexts[0].embedding)
        self.assertEqual(len(contexts[0].embedding), 768)

        # Verify risk was promoted to OPEN
        promoted_risk = self.risk_repo.get_risk("RSK-HITL-01")
        self.assertIsNotNone(promoted_risk)
        self.assertEqual(promoted_risk.status, RiskStatus.OPEN)

        # Verify BigQuery streaming rows
        self.assertEqual(len(_in_memory_bq_golden_records), 3)
        self.assertGreaterEqual(len(_in_memory_bq_pulse_history), 2)
        self.assertGreaterEqual(len(_in_memory_bq_audit_events), 1)

        # Verify locked Golden Record rejects further edits
        reject_resp = self.client.patch(
            f"/api/v1/meetings/{self.meeting_id}/blocks/blk-0001/score",
            json={"final_pulse_score": 50.0},
            headers=self.adjudicator_headers,
        )
        self.assertEqual(reject_resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
