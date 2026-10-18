import hashlib
import json
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure backend package is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.bigquery import (
    AUDIT_LEDGER_SINK_SCHEMA,
    BigQueryAnalyticsClient,
    GOLDEN_DIALOGUE_RECORDS_SCHEMA,
)
from app.core.config import get_settings
from app.core.database import InMemoryFirestoreClient
from app.core.security import UserRole
from app.core.storage import ComplianceStorageClient
from app.repositories.audit_repository import AuditRepository
from app.repositories.compliance_repository import ComplianceRepository
from app.repositories.meeting_repository import MeetingRepository
from app.repositories.risk_repository import RiskRepository
from app.repositories.sentiment_repository import SentimentRepository
from app.schemas.audit import AuditLedgerEntryCreate
from app.schemas.compliance import (
    ComplianceFormat,
    ComplianceFramework,
    CompliancePackageCreate,
    CompliancePackageStatus,
)
from app.schemas.meeting import (
    CanonicalGroup,
    DialogueBlockCreate,
    MeetingCreate,
    MeetingStatus,
    RubricBreakdown,
)
from app.schemas.risk import (
    EscalationTier,
    RiskCategory,
    RiskRegisterCreate,
    RiskRegisterUpdate,
    RiskStatus,
)
from app.schemas.sentiment import SentimentCalibrationCreate
from app.schemas.user import AdminUserProvisionRequest, UserProfileResponse


class TestCloudInfrastructureAndSchemas(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = get_settings()
        self.settings.use_in_memory_firestore = True
        self.settings.use_mock_firebase_auth = True
        self.db = InMemoryFirestoreClient()
        self.meeting_repo = MeetingRepository(db=self.db)
        self.risk_repo = RiskRepository(db=self.db)
        self.sentiment_repo = SentimentRepository(db=self.db)
        self.compliance_repo = ComplianceRepository(db=self.db)
        self.audit_repo = AuditRepository(db=self.db)

    def test_admin_user_crud_and_schema_validation(self) -> None:
        """Verify Admin user provisioning request and profile schema."""
        req = AdminUserProvisionRequest(
            email="secops@enterprise.com",
            first_name="Security",
            last_name="Operations",
            phone_number="081299998888",
            country_code="ID",
            role=UserRole.ADMIN,
            assigned_project_ids=["proj-alpha", "proj-beta"],
        )
        self.assertEqual(req.phone_number, "+6281299998888")
        self.assertEqual(req.role, UserRole.ADMIN)

        profile = UserProfileResponse(
            uid="uid_secops_01",
            email=req.email,
            first_name=req.first_name,
            last_name=req.last_name,
            phone_number=req.phone_number,
            role=req.role,
            auth_provider="password",
            assigned_project_ids=req.assigned_project_ids,
            onboarding_status="ACTIVE",
            created_at=datetime.now(timezone.utc).isoformat(),
            last_login_at=datetime.now(timezone.utc).isoformat(),
        )
        self.db.collection("users").document(profile.uid).set(profile.model_dump())
        fetched = self.db.collection("users").document(profile.uid).get()
        self.assertTrue(fetched.exists)
        self.assertEqual(fetched.to_dict()["role"], "ADMIN")

    def test_meeting_and_dialogue_blocks_with_768_dim_vector(self) -> None:
        """Verify meeting and subcollection dialogue blocks with 768-dim embeddings."""
        meeting = MeetingCreate(
            meeting_id="mtg_2026_q4",
            project_id="proj_compliance",
            title="Q4 Architecture & Security Sign-off",
            platform="google_meet",
            status=MeetingStatus.SCHEDULED,
            participants=["uid_secops_01", "uid_adj_01"],
        )
        created_meeting = self.meeting_repo.create_meeting(meeting)
        self.assertEqual(created_meeting.meeting_id, "mtg_2026_q4")

        # 768-dim vector embedding
        dummy_embedding = [0.01 * (i % 10) for i in range(768)]
        block = DialogueBlockCreate(
            block_id="blk_0001",
            sequence_index=1,
            speaker_alias="Lead Architect",
            group_id=CanonicalGroup.INTERNAL.value,
            group_name="Core Platform Engineering",
            text_scrubbed="All audit logs must be cryptographically sealed prior to WORM storage.",
            word_count=10,
            dlp_redaction_flags=[],
            sentiment_score=82.5,
            rubric_scores=RubricBreakdown(
                emotional_valence=20.0,
                delivery_alignment=22.5,
                relationship_trust=20.0,
                momentum_commitment=20.0,
            ),
            embedding=dummy_embedding,
        )
        created_block = self.meeting_repo.create_dialogue_block("mtg_2026_q4", block)
        self.assertEqual(created_block.block_id, "blk_0001")
        self.assertEqual(len(created_block.embedding), 768)

        # Retrieve block
        retrieved_block = self.meeting_repo.get_dialogue_block("mtg_2026_q4", "blk_0001")
        self.assertIsNotNone(retrieved_block)
        self.assertEqual(retrieved_block.group_id, "INTERNAL")

        # Invalid vector dimension raises ValueError
        with self.assertRaises(ValueError):
            DialogueBlockCreate(
                block_id="blk_bad",
                sequence_index=2,
                text_scrubbed="Invalid embedding",
                embedding=[0.1, 0.2, 0.3],  # Not 768 dimensions
            )

    def test_sentiment_calibrations_and_few_shot_retrieval(self) -> None:
        """Verify sentiment calibration schema and nearest neighbor ranking."""
        vec1 = [1.0 if i < 100 else 0.0 for i in range(768)]
        vec2 = [0.0 if i < 100 else 1.0 for i in range(768)]

        cal1 = SentimentCalibrationCreate(
            calibration_id="cal_high_trust",
            project_id="proj_compliance",
            dialogue_text="We have completed the SOC 2 audit with zero findings.",
            benchmark_score=95.0,
            rubric_breakdown={"relationship_trust": 24.0, "delivery_alignment": 25.0},
            embedding=vec1,
        )
        cal2 = SentimentCalibrationCreate(
            calibration_id="cal_low_trust",
            project_id="proj_compliance",
            dialogue_text="Milestones are delayed and no documentation was shared.",
            benchmark_score=20.0,
            rubric_breakdown={"relationship_trust": 5.0, "delivery_alignment": 5.0},
            embedding=vec2,
        )
        self.sentiment_repo.create_calibration(cal1)
        self.sentiment_repo.create_calibration(cal2)

        # Query vector close to vec1
        query_vec = [0.9 if i < 100 else 0.05 for i in range(768)]
        nearest = self.sentiment_repo.find_nearest_exemplars(query_vec, limit=1)
        self.assertEqual(len(nearest), 1)
        self.assertEqual(nearest[0].calibration_id, "cal_high_trust")

    def test_risk_register_coso_matrix_and_sla_tiers(self) -> None:
        """Verify 5x5 COSO matrix computation and SLA tier calculation."""
        # Critical risk: Impact 5 * Probability 4 = 20 -> Tier 24h
        risk_high = RiskRegisterCreate(
            risk_id="RSK-2026-0001",
            project_id="proj_compliance",
            title="WORM Retention Bypass Vulnerability",
            description="Compliance bucket write policy must prevent overwrite.",
            category=RiskCategory.COMPLIANCE,
            impact=5,
            probability=4,
        )
        self.assertEqual(risk_high.severity_score, 20)
        self.assertEqual(risk_high.sla_escalation_tier, EscalationTier.TIER_24H.value)
        self.risk_repo.create_risk(risk_high)

        # Low risk: Impact 2 * Probability 2 = 4 -> Tier 72h
        risk_low = RiskRegisterCreate(
            risk_id="RSK-2026-0002",
            project_id="proj_compliance",
            title="Minor Dashboard UI Alignment",
            description="Color contrast on badge needs adjustment.",
            category=RiskCategory.OPERATIONAL,
            impact=2,
            probability=2,
        )
        self.assertEqual(risk_low.severity_score, 4)
        self.assertEqual(risk_low.sla_escalation_tier, EscalationTier.TIER_72H.value)
        self.risk_repo.create_risk(risk_low)

        # Update risk severity
        updated = self.risk_repo.update_risk(
            "RSK-2026-0002",
            RiskRegisterUpdate(impact=4, probability=3),  # 4 * 3 = 12 -> 48h tier
        )
        self.assertEqual(updated.severity_score, 12)
        self.assertEqual(updated.sla_escalation_tier, EscalationTier.TIER_48H.value)

    def test_compliance_packages_and_immutable_audit_ledger(self) -> None:
        """Verify compliance package WORM metadata and immutable audit logging."""
        raw_pdf_bytes = b"%PDF-1.4 Mock Compliance Package Content"
        sha256 = hashlib.sha256(raw_pdf_bytes).hexdigest()

        pkg = CompliancePackageCreate(
            package_id="CMP-2026-0001",
            project_id="proj_compliance",
            target_frameworks=[ComplianceFramework.ISO_31000, ComplianceFramework.SOC_2],
            format=ComplianceFormat.PDF,
            sha256_hash=sha256,
            gcs_uri="gs://prisk-compliance-packages-prisk-ai/proj_compliance/CMP-2026-0001.pdf",
            status=CompliancePackageStatus.SEALED_WORM,
            generated_by_uid="uid_secops_01",
        )
        created_pkg = self.compliance_repo.create_package(pkg)
        self.assertEqual(created_pkg.status, "SEALED_WORM")
        self.assertEqual(created_pkg.sha256_hash, sha256)

        # Log to audit ledger
        event = self.audit_repo.log(
            event_type="COMPLIANCE_PACKAGE_EXPORTED",
            actor_uid="uid_secops_01",
            target_id="CMP-2026-0001",
            actor_role="ADMIN",
            action_type="COMPLIANCE_PACKAGE_EXPORTED",
            entity_type="COMPLIANCE_PACKAGE",
            sha256_hash=sha256,
            metadata={"frameworks": ["ISO_31000", "SOC_2"], "format": "PDF"},
        )
        self.assertEqual(event.event_type, "COMPLIANCE_PACKAGE_EXPORTED")
        events = self.audit_repo.list_events(target_id="CMP-2026-0001")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].sha256_hash, sha256)

    def test_gcs_compliance_storage_client_mock_upload(self) -> None:
        """Verify GCS compliance storage client SHA-256 calculation and payload wrapping."""
        storage_client = ComplianceStorageClient()
        mock_gcs = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_gcs.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        storage_client._client = mock_gcs

        sample_bytes = b"Sealed WORM Evidence Report"
        expected_sha = hashlib.sha256(sample_bytes).hexdigest()
        result = storage_client.upload_compliance_package(
            package_id="CMP-TEST-99",
            project_id="proj_compliance",
            content=sample_bytes,
            file_extension="pdf",
        )
        self.assertEqual(result["sha256_hash"], expected_sha)
        self.assertEqual(result["status"], "SEALED_WORM")
        mock_blob.upload_from_string.assert_called_once()

    def test_bigquery_analytics_schema_definitions_and_streaming(self) -> None:
        """Verify BigQuery schemas and streaming record formatting."""
        # Verify schema field types
        field_names = [f.name for f in GOLDEN_DIALOGUE_RECORDS_SCHEMA]
        self.assertIn("meeting_id", field_names)
        self.assertIn("project_id", field_names)
        self.assertIn("meeting_date", field_names)
        self.assertIn("text_scrubbed", field_names)
        self.assertIn("sentiment_score", field_names)
        self.assertIn("committed_at", field_names)

        audit_fields = [f.name for f in AUDIT_LEDGER_SINK_SCHEMA]
        self.assertIn("event_id", audit_fields)
        self.assertIn("event_type", audit_fields)
        self.assertIn("actor_uid", audit_fields)
        self.assertIn("sha256_hash", audit_fields)

        # Verify streaming call
        bq_client = BigQueryAnalyticsClient()
        mock_bq = MagicMock()
        mock_bq.insert_rows_json.return_value = []
        bq_client._client = mock_bq

        row = {
            "meeting_id": "mtg_2026_q4",
            "project_id": "proj_compliance",
            "meeting_date": "2026-10-18",
            "block_id": "blk_0001",
            "text_scrubbed": "Scrubbed dialogue record.",
            "word_count": 3,
            "sentiment_score": 88.0,
            "is_human_overridden": False,
            "committed_at": "2026-10-18T18:00:00Z",
        }
        streamed = bq_client.stream_golden_dialogue_records([row])
        self.assertEqual(len(streamed), 1)
        mock_bq.insert_rows_json.assert_called_once()


if __name__ == "__main__":
    unittest.main()
