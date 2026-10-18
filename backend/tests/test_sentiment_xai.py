from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import _in_memory_db
from app.core.enums import UserRole
from app.core.firebase import reset_mock_custom_claims
from app.main import create_app
from app.repositories.meeting_repository import MeetingRepository
from app.repositories.risk_repository import RiskRepository
from app.repositories.sentiment_repository import SentimentRepository
from app.schemas.meeting import DialogueBlockCreate, MeetingCreate, MeetingStatus
from app.schemas.sentiment import (
    CorrectedContextCreate,
    ExplainRationaleResponse,
    PostMeetingAnalysisResponse,
    RubricScoresSchema,
    SpanAttribution,
)
from app.services.sentiment_service import (
    SentimentService,
    strip_speaker_identity,
    verify_and_locate_substrings,
)


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


class TestSentimentRubricFewShotAndXAI(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = get_settings()
        self.settings.use_in_memory_firestore = True
        self.settings.use_mock_firebase_auth = True

        _in_memory_db.clear()
        reset_mock_custom_claims()

        self.db = _in_memory_db
        self.meeting_repo = MeetingRepository(db=self.db)
        self.sentiment_repo = SentimentRepository(db=self.db)
        self.risk_repo = RiskRepository(db=self.db)
        self.sentiment_service = SentimentService(db=self.db)
        self.app = create_app()
        self.client = TestClient(self.app)

        self.project_id = "proj-sentiment-xai"
        self.adjudicator_uid = "uid_adjudicator_01"
        self.adjudicator_headers = make_mock_bearer(
            self.adjudicator_uid, "adjudicator@enterprise.com", UserRole.ADJUDICATOR.value
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

    def test_4_1_speaker_blind_sanitization_and_structured_output_schema(self) -> None:
        """4.1 Verify speaker identities are stripped before LLM prompt construction and structured schema produces 4-dim rubric, MoM, and draft risks."""
        raw_blocks = [
            {
                "block_id": "blk-0001",
                "sequence_index": 0,
                "speaker_alias": "Sarah Jenkins (Chief Counsel)",
                "display_speaker_label": "Sarah Jenkins",
                "ephemeral_speaker_account_id": "ms_spk_99",
                "text_scrubbed": "We cannot sign off on the UAT deployment because audit logs are delayed.",
            },
            {
                "block_id": "blk-0002",
                "sequence_index": 1,
                "speaker_alias": "David Kim (VP Engineering)",
                "display_speaker_label": "David Kim",
                "ephemeral_speaker_account_id": "ms_spk_100",
                "text_scrubbed": "Our team will deliver the updated audit schema documentation by Friday.",
            },
        ]

        blind_blocks = strip_speaker_identity(raw_blocks)
        self.assertEqual(len(blind_blocks), 2)
        dumped_json = json.dumps([b.model_dump() for b in blind_blocks])
        self.assertNotIn("Sarah Jenkins", dumped_json)
        self.assertNotIn("David Kim", dumped_json)
        self.assertNotIn("ms_spk_99", dumped_json)
        self.assertNotIn("speaker_alias", dumped_json)

        analysis, meta = self.sentiment_service.analyze_meeting_blocks(
            project_id=self.project_id,
            blocks=raw_blocks,
            canonical_groups=[
                "Client Legal & Compliance",
                "Internal Delivery Team",
            ],
        )
        self.assertIsInstance(analysis, PostMeetingAnalysisResponse)
        self.assertTrue(meta["speaker_blind"])
        self.assertEqual(len(analysis.block_results), 2)

        first_res = analysis.block_results[0]
        self.assertEqual(
            first_res.pulse_score,
            first_res.rubric_breakdown.total_score(),
        )
        self.assertIn(
            first_res.suggested_group_name,
            ["Client Legal & Compliance", "Internal Delivery Team"],
        )
        self.assertGreaterEqual(len(analysis.draft_risks), 1)
        self.assertGreaterEqual(len(analysis.action_items), 1)

    def test_4_2_zero_shot_cold_start_and_top_5_few_shot_vector_retrieval(self) -> None:
        """4.2 Verify Cold-Start Zero-Shot fallback when 0 overrides exist, and Top-5 Few-Shot vector search when overrides exist."""
        blocks = [
            {
                "block_id": "blk-0001",
                "sequence_index": 0,
                "text_scrubbed": "Compliance gate review is blocked by delayed audit documentation.",
            }
        ]

        # 1. Cold-Start: zero stored vectors for project
        _, cold_meta = self.sentiment_service.analyze_meeting_blocks(
            project_id=self.project_id,
            blocks=blocks,
        )
        self.assertEqual(cold_meta["inference_mode"], "ZERO_SHOT")
        self.assertEqual(cold_meta["few_shot_count"], 0)

        # 2. Seed 7 CorrectedContext overrides (768-dim text-embedding-004 vectors)
        for i in range(7):
            text_sample = (
                f"Audit documentation delay on milestone {i} caused compliance sign-off concern."
                if i < 5
                else f"Unrelated routine lunch scheduling discussion {i}."
            )
            emb = self.sentiment_service.generate_embedding(text_sample)
            self.assertEqual(len(emb), 768)
            self.sentiment_repo.create_corrected_context(
                CorrectedContextCreate(
                    correction_id=f"corr-{i + 1:02d}",
                    project_id=self.project_id,
                    group_name="Client Legal & Compliance",
                    scrubbed_text=text_sample,
                    embedding=emb,
                    ai_initial_score=45.0,
                    human_adjusted_score=28.0 + i,
                    rubric_breakdown={
                        "emotional_valence": 7.0,
                        "delivery_alignment": 6.0,
                        "relationship_trust": 8.0,
                        "momentum_commitment": 7.0 + i,
                    },
                    adjudicator_uid=self.adjudicator_uid,
                )
            )

        # 3. Verify top-5 nearest neighbor retrieval via Firestore find_nearest
        _, warm_meta = self.sentiment_service.analyze_meeting_blocks(
            project_id=self.project_id,
            blocks=blocks,
        )
        self.assertEqual(warm_meta["inference_mode"], "FEW_SHOT")
        self.assertEqual(warm_meta["few_shot_count"], 5)
        self.assertEqual(len(warm_meta["few_shot_ids"]), 5)

    def test_4_3_on_demand_xai_endpoint_and_verbatim_offset_validation(self) -> None:
        """4.3 Verify POST /api/v1/meetings/{id}/blocks/{id}/explain validates exact substrings and rejects hallucinated spans."""
        meeting_id = "mtg-xai-test-01"
        block_id = "blk-0014"
        scrubbed_text = (
            "We cannot sign off on the UAT deployment if the audit logs are delayed again. "
            "Reach my office at [PHONE_NUMBER] if we need an emergency review."
        )

        self.meeting_repo.create_meeting(
            MeetingCreate(
                meeting_id=meeting_id,
                project_id=self.project_id,
                title="UAT Gate Review",
                status=MeetingStatus.PENDING_ADJUDICATION,
            )
        )
        self.meeting_repo.create_dialogue_block(
            meeting_id=meeting_id,
            block=DialogueBlockCreate(
                block_id=block_id,
                sequence_index=14,
                speaker_alias="Sarah Jenkins",
                group_name="Client Legal & Compliance",
                text_scrubbed=scrubbed_text,
                word_count=len(scrubbed_text.split()),
                sentiment_score=38.0,
            ),
        )

        # Direct unit test of anti-hallucination offset verifier
        raw_spans = [
            SpanAttribution(
                verbatim_phrase="cannot sign off on the UAT deployment",
                attribution_weight=-0.85,
                rubric_dimension="delivery_alignment",
                rationale="Explicit blocker statement halting milestone sign-off.",
            ),
            SpanAttribution(
                verbatim_phrase="audit logs are delayed again",
                attribution_weight=-0.72,
                rubric_dimension="relationship_trust",
                rationale="Repeated delivery delay indicating trust erosion.",
            ),
            SpanAttribution(
                verbatim_phrase="THIS PHRASE WAS HALLUCINATED BY LLM",
                attribution_weight=-0.99,
                rubric_dimension="emotional_valence",
                rationale="Should be stripped by server-side offset verifier.",
            ),
        ]
        verified = verify_and_locate_substrings(scrubbed_text, raw_spans)
        self.assertEqual(len(verified), 2)
        for v in verified:
            self.assertEqual(
                scrubbed_text[v.start_char : v.end_char],
                v.verbatim_phrase,
            )

        # Call REST endpoint POST /api/v1/meetings/{id}/blocks/{id}/explain
        resp = self.client.post(
            f"/api/v1/meetings/{meeting_id}/blocks/{block_id}/explain",
            headers=self.adjudicator_headers,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["meeting_id"], meeting_id)
        self.assertEqual(data["block_id"], block_id)
        self.assertIn("rubric_breakdown", data)
        self.assertGreaterEqual(len(data["attributions"]), 1)

        for attr in data["attributions"]:
            start = attr["start_char"]
            end = attr["end_char"]
            phrase = attr["verbatim_phrase"]
            self.assertEqual(scrubbed_text[start:end], phrase)

        # Verify audit event XAI_INVOKED was recorded
        audit_snaps = list(
            self.db.collection("audit_ledger")
            .where("event_type", "==", "XAI_INVOKED")
            .stream()
        )
        self.assertEqual(len(audit_snaps), 1)

    def test_post_meeting_analyze_endpoint_updates_blocks_and_draft_risks(self) -> None:
        """Verify POST /api/v1/meetings/{id}/analyze scores blocks, populates MoM, and creates DRAFT_PENDING_ADJUDICATION risks."""
        meeting_id = "mtg-post-analyze-01"
        self.meeting_repo.create_meeting(
            MeetingCreate(
                meeting_id=meeting_id,
                project_id=self.project_id,
                title="Vendor Security Review",
                status=MeetingStatus.PROCESSING_POST_MEETING,
            )
        )
        self.meeting_repo.create_dialogue_block(
            meeting_id=meeting_id,
            block=DialogueBlockCreate(
                block_id="blk-0001",
                sequence_index=0,
                speaker_alias="Client Lead",
                text_scrubbed="The security audit is delayed and blocked by missing compliance artifacts.",
                word_count=11,
            ),
        )

        resp = self.client.post(
            f"/api/v1/meetings/{meeting_id}/analyze",
            headers=self.adjudicator_headers,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        res_data = resp.json()
        self.assertEqual(res_data["status"], MeetingStatus.PENDING_ADJUDICATION.value)

        updated_meeting = self.meeting_repo.get_meeting(meeting_id)
        self.assertIsNotNone(updated_meeting)
        self.assertEqual(updated_meeting.status, MeetingStatus.PENDING_ADJUDICATION.value)
        self.assertIsNotNone(updated_meeting.pulse_score)
        self.assertIsNotNone(updated_meeting.mom_summary)

        blocks = self.meeting_repo.list_dialogue_blocks(meeting_id)
        self.assertEqual(len(blocks), 1)
        self.assertIsNotNone(blocks[0].sentiment_score)
        self.assertIsNotNone(blocks[0].embedding)
        self.assertEqual(len(blocks[0].embedding), 768)

        draft_risks = self.risk_repo.list_risks(
            project_id=self.project_id,
            status="DRAFT_PENDING_ADJUDICATION",
        )
        self.assertGreaterEqual(len(draft_risks), 1)

    def test_4_4_longitudinal_pulse_trends_endpoint_and_windows(self) -> None:
        """Task 4.1: Verify GET /api/v1/analytics/pulse-trends across 7D, 30D, QTD, and Custom windows with AI synthesis."""
        now = datetime.now(timezone.utc)
        meeting_1_id = "mtg_pulse_1"
        meeting_2_id = "mtg_pulse_2"

        self.meeting_repo.create_meeting(
            MeetingCreate(
                meeting_id=meeting_1_id,
                project_id=self.project_id,
                title="Sprint 10 Checkpoint",
                meeting_date=(now - timedelta(days=12)).isoformat(),
                status=MeetingStatus.GOLDEN_RECORD,
                pulse_score=42.0,
                group_scores={"BUYER": {"pulse_score": 45.0, "block_count": 5}, "VENDOR": {"pulse_score": 39.0, "block_count": 5}},
            )
        )
        self.meeting_repo.create_meeting(
            MeetingCreate(
                meeting_id=meeting_2_id,
                project_id=self.project_id,
                title="Sprint 11 Alignment Demo",
                meeting_date=(now - timedelta(days=2)).isoformat(),
                status=MeetingStatus.GOLDEN_RECORD,
                pulse_score=78.0,
                group_scores={"BUYER": {"pulse_score": 80.0, "block_count": 6}, "VENDOR": {"pulse_score": 76.0, "block_count": 6}},
            )
        )

        # Test 30D window
        resp_30d = self.client.get(
            f"/api/v1/analytics/pulse-trends?project_id={self.project_id}&time_window=30D",
            headers=self.adjudicator_headers,
        )
        self.assertEqual(resp_30d.status_code, 200, resp_30d.text)
        data_30d = resp_30d.json()
        self.assertEqual(data_30d["time_window"], "30D")
        self.assertEqual(len(data_30d["trajectory_points"]), 2)
        self.assertEqual(data_30d["aggregate_metrics"]["total_meetings"], 2)
        self.assertEqual(data_30d["aggregate_metrics"]["average_pulse"], 60.0)
        self.assertEqual(data_30d["aggregate_metrics"]["pulse_change"], 36.0)
        self.assertIn("BUYER", data_30d["aggregate_metrics"]["group_averages"])
        self.assertIsNotNone(data_30d["ai_commentary"]["headline"])
        self.assertGreaterEqual(len(data_30d["ai_commentary"]["key_drivers_of_shifts"]), 1)

        # Test 7D window (only meeting 2 is within 7 days)
        resp_7d = self.client.get(
            f"/api/v1/analytics/pulse-trends?project_id={self.project_id}&time_window=7D",
            headers=self.adjudicator_headers,
        )
        self.assertEqual(resp_7d.status_code, 200)
        data_7d = resp_7d.json()
        self.assertEqual(len(data_7d["trajectory_points"]), 1)
        self.assertEqual(data_7d["trajectory_points"][0]["meeting_id"], meeting_2_id)

        # Test Custom window
        start_str = (now - timedelta(days=15)).strftime("%Y-%m-%d")
        end_str = (now - timedelta(days=5)).strftime("%Y-%m-%d")
        resp_custom = self.client.get(
            f"/api/v1/analytics/pulse-trends?project_id={self.project_id}&time_window=Custom&start_date={start_str}&end_date={end_str}",
            headers=self.adjudicator_headers,
        )
        self.assertEqual(resp_custom.status_code, 200)
        data_custom = resp_custom.json()
        self.assertEqual(len(data_custom["trajectory_points"]), 1)
        self.assertEqual(data_custom["trajectory_points"][0]["meeting_id"], meeting_1_id)

    def test_5_1_regenerate_insights_respects_human_overrides_and_refreshes_draft_risks(self) -> None:
        """Task 5.1: Verify POST /api/v1/meetings/{id}/regenerate-insights incorporates human overrides into MoM & risks."""
        meeting_id = "mtg_regen_test"
        self.meeting_repo.create_meeting(
            MeetingCreate(
                meeting_id=meeting_id,
                project_id=self.project_id,
                title="Q3 Adjudication Session",
                status=MeetingStatus.PROCESSING_POST_MEETING,
            )
        )
        # Block 1: Human-overridden positive block
        self.meeting_repo.create_dialogue_block(
            meeting_id,
            DialogueBlockCreate(
                block_id="blk-01",
                sequence_index=0,
                text_scrubbed="The client compliance audit was approved with zero defects.",
                word_count=9,
                group_name="BUYER",
                sentiment_score=92.0,
                ai_initial_score=50.0,
                is_human_overridden=True,
                is_pinned=True,
            ),
        )
        # Block 2: Human-pinned friction block
        self.meeting_repo.create_dialogue_block(
            meeting_id,
            DialogueBlockCreate(
                block_id="blk-02",
                sequence_index=1,
                text_scrubbed="The vendor backend delivery is delayed by two weeks due to database issues.",
                word_count=13,
                group_name="VENDOR",
                sentiment_score=28.0,
                ai_initial_score=40.0,
                is_human_overridden=True,
                is_pinned=True,
            ),
        )

        resp = self.client.post(
            f"/api/v1/meetings/{meeting_id}/regenerate-insights",
            headers=self.adjudicator_headers,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        res_data = resp.json()
        self.assertEqual(res_data["status"], "insights_regenerated")
        self.assertIn("mom_summary", res_data)
        self.assertGreaterEqual(res_data["draft_risks_created"], 1)

        # Verify block scores and groups were not wiped
        blocks = self.meeting_repo.list_dialogue_blocks(meeting_id)
        blk_1 = next(b for b in blocks if b.block_id == "blk-01")
        self.assertEqual(blk_1.group_name, "BUYER")
        self.assertEqual(blk_1.sentiment_score, 92.0)
        self.assertTrue(blk_1.is_human_overridden)

        blk_2 = next(b for b in blocks if b.block_id == "blk-02")
        self.assertEqual(blk_2.group_name, "VENDOR")
        self.assertEqual(blk_2.sentiment_score, 28.0)
        self.assertTrue(blk_2.is_human_overridden)

        # Verify meeting was updated to PENDING_ADJUDICATION with group scores
        updated_meeting = self.meeting_repo.get_meeting(meeting_id)
        self.assertEqual(updated_meeting.status, MeetingStatus.PENDING_ADJUDICATION.value)
        self.assertIn("BUYER", updated_meeting.group_scores)
        self.assertIn("VENDOR", updated_meeting.group_scores)
        self.assertEqual(updated_meeting.group_scores["BUYER"]["pulse_score"], 92.0)
        self.assertEqual(updated_meeting.group_scores["VENDOR"]["pulse_score"], 28.0)


if __name__ == "__main__":
    unittest.main()

