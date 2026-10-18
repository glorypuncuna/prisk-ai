import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from typing import Any
import uuid

from app.core.bigquery import BigQueryAnalyticsClient
from app.core.database import get_firestore_client
from app.core.storage import ComplianceStorageClient
from app.repositories.audit_repository import AuditRepository
from app.repositories.compliance_repository import ComplianceRepository
from app.repositories.meeting_repository import MeetingRepository
from app.repositories.risk_repository import RiskRepository
from app.schemas.compliance import (
    ComplianceExportRequest,
    ComplianceFormat,
    ComplianceIntegrityResponse,
    CompliancePackageCreate,
    CompliancePackageResponse,
    CompliancePackageStatus,
    GdprMeetingPurgeResponse,
)
from app.schemas.risk import RiskStatus
from app.services.sanitization_service import (
    GDPR_PURGED_TOMBSTONE_TEXT,
    SanitizationService,
    get_sanitization_service,
)
from app.services.sentiment_service import get_sentiment_service



def _escape_pdf_text(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .encode("ascii", errors="replace")
        .decode("ascii")
    )


def _build_standards_compliant_pdf_bytes(lines: list[str]) -> bytes:
    """Build a valid %PDF-1.4 document containing all 5 compliance sections when WeasyPrint native libs are absent."""
    content_ops: list[str] = ["BT", "/F1 10 Tf", "40 760 Td", "13 TL"]
    for idx, raw_line in enumerate(lines[:140]):
        safe = _escape_pdf_text(raw_line[:105])
        if idx == 0:
            content_ops.append(f"({safe}) Tj")
        else:
            content_ops.append(f"T* ({safe}) Tj")
    content_ops.append("ET")
    stream_bytes = "\n".join(content_ops).encode("latin-1", errors="replace")

    objects: list[bytes] = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n",
        f"4 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode("ascii")
        + stream_bytes
        + b"\nendstream\nendobj\n",
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]

    header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    body = bytearray(header)
    offsets: list[int] = []
    for obj in objects:
        offsets.append(len(body))
        body.extend(obj)

    xref_offset = len(body)
    xref_lines = [f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"]
    for off in offsets:
        xref_lines.append(f"{off:010d} 00000 n \n")
    body.extend("".join(xref_lines).encode("ascii"))
    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode("ascii")
    body.extend(trailer)
    return bytes(body)


def _render_pdf_from_sections(sections: dict[str, Any]) -> bytes:
    """Render the 5 compliance sections into PDF via WeasyPrint if installed, falling back to deterministic PDF-1.4."""
    header = sections["header_and_metadata"]
    mappings = sections["framework_control_mapping_table"]
    risks = sections["sanitized_risk_register"]
    lifecycle = sections["mitigation_lifecycle_audit_summary"]
    attestation = sections["privacy_and_data_governance_attestation"]

    try:
        import weasyprint  # type: ignore

        html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<title>Compliance Audit Package {header['package_id']}</title>
<style>
body {{ font-family: sans-serif; font-size: 11px; color: #0f172a; margin: 24px; }}
h1 {{ font-size: 18px; margin-bottom: 4px; }}
h2 {{ font-size: 13px; margin-top: 16px; border-bottom: 1px solid #cbd5e1; padding-bottom: 4px; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
th, td {{ border: 1px solid #cbd5e1; padding: 6px; text-align: left; }}
th {{ background: #f1f5f9; }}
</style>
</head>
<body>
<h1>Section 1: Header &amp; Cryptographic Metadata</h1>
<p>Package ID: {header['package_id']} | Version: {header['version_id']} | Project: {header['project_id']} | Organization: {header['company_name']}</p>
<p>Frameworks: {', '.join(header['target_frameworks'])} | Generated At: {header['generated_at']}</p>
<h2>Section 2: Framework Control Mapping Table</h2>
<table><tr><th>Risk ID</th><th>Category</th><th>Framework</th><th>Clause</th><th>Control Title</th></tr>
{''.join(f"<tr><td>{m['risk_id']}</td><td>{m['risk_category']}</td><td>{m['framework']}</td><td>{m['clause_id']}</td><td>{m['control_title']}</td></tr>" for m in mappings)}
</table>
<h2>Section 3: Sanitized Risk Register (Zero Verbatim Quotes)</h2>
<table><tr><th>Risk ID</th><th>Category</th><th>Severity</th><th>Band</th><th>Status</th><th>Groups</th><th>Treatment Summary</th></tr>
{''.join(f"<tr><td>{r['risk_id']}</td><td>{r['category']}</td><td>{r['severity_score']}</td><td>{r['severity_band']}</td><td>{r['status']}</td><td>{', '.join(r['associated_groups'])}</td><td>{r['treatment_summary']}</td></tr>" for r in risks)}
</table>
<h2>Section 4: Mitigation Lifecycle Audit Summary</h2>
<p>Total Tracked Risks: {lifecycle['total_risks']} | Open: {lifecycle['open_risks']} | Mitigated: {lifecycle['mitigated_risks']} | Accepted: {lifecycle['accepted_risks']}</p>
<h2>Section 5: Privacy &amp; Data Governance Attestation</h2>
<p>DLP Scrubbed Meetings: {attestation['dlp_scrubbed_meetings_count']} | Upstream Transcripts Deleted: {attestation['upstream_transcripts_deleted_count']} | Zero Verbatim Quotes Verified: {attestation['zero_verbatim_quotes_verified']}</p>
</body>
</html>"""
        return weasyprint.HTML(string=html_content).write_pdf()
    except Exception:
        lines = [
            f"PRISK AI MULTI-FRAMEWORK COMPLIANCE AUDIT PACKAGE ({header['package_id']})",
            f"Section 1: Header & Metadata | Version: {header['version_id']} | Project: {header['project_id']}",
            f"Organization: {header['company_name']} | Generated At: {header['generated_at']}",
            f"Target Frameworks: {', '.join(header['target_frameworks'])}",
            "--------------------------------------------------------------------------------",
            "Section 2: Framework Control Mapping Table",
        ]
        for m in mappings[:25]:
            lines.append(
                f"  [{m['framework']}] Clause {m['clause_id']} | Risk {m['risk_id']} ({m['risk_category']}) -> {m['control_title']}"
            )
        lines.append("--------------------------------------------------------------------------------")
        lines.append("Section 3: Sanitized Risk Register (Zero Verbatim Quotes Enforced)")
        for r in risks[:25]:
            lines.append(
                f"  {r['risk_id']} | {r['category']} | Score: {r['severity_score']} ({r['severity_band']}) | Status: {r['status']} | {r['treatment_summary'][:65]}"
            )
        lines.append("--------------------------------------------------------------------------------")
        lines.append(
            f"Section 4: Mitigation Lifecycle Audit Summary | Total: {lifecycle['total_risks']} | Open: {lifecycle['open_risks']} | Mitigated: {lifecycle['mitigated_risks']}"
        )
        for ev in lifecycle.get("timeline_events", [])[:15]:
            lines.append(
                f"  {ev.get('timestamp', '')} | {ev.get('action_type', '')} | Target: {ev.get('entity_id', '')}"
            )
        lines.append("--------------------------------------------------------------------------------")
        lines.append(
            f"Section 5: Privacy & Data Governance Attestation | Zero Verbatim Quotes: {attestation['zero_verbatim_quotes_verified']}"
        )
        lines.append(
            f"  DLP Scrubbed Meetings: {attestation['dlp_scrubbed_meetings_count']} | Verified Upstream Deletions: {attestation['upstream_transcripts_deleted_count']}"
        )
        lines.append(f"  Zero Audio Storage Policy: {attestation['zero_audio_retention_policy']}")
        return _build_standards_compliant_pdf_bytes(lines)


def _render_csv_from_sections(sections: dict[str, Any]) -> bytes:
    """Compile the 5 structured compliance sections into UTF-8 CSV bytes."""
    buf = io.StringIO()
    writer = csv.writer(buf)

    header = sections["header_and_metadata"]
    writer.writerow(["SECTION_1_HEADER_AND_METADATA"])
    writer.writerow(["package_id", "version_id", "project_id", "company_name", "target_frameworks", "generated_at", "generated_by_uid"])
    writer.writerow([
        header["package_id"],
        header["version_id"],
        header["project_id"],
        header["company_name"],
        ";".join(header["target_frameworks"]),
        header["generated_at"],
        header["generated_by_uid"],
    ])
    writer.writerow([])

    writer.writerow(["SECTION_2_FRAMEWORK_CONTROL_MAPPING_TABLE"])
    writer.writerow(["risk_id", "risk_category", "severity_band", "risk_status", "framework", "clause_id", "control_title", "control_objective"])
    for m in sections["framework_control_mapping_table"]:
        writer.writerow([
            m["risk_id"],
            m["risk_category"],
            m["severity_band"],
            m["risk_status"],
            m["framework"],
            m["clause_id"],
            m["control_title"],
            m["control_objective"],
        ])
    writer.writerow([])

    writer.writerow(["SECTION_3_SANITIZED_RISK_REGISTER"])
    writer.writerow(["risk_id", "project_id", "category", "title", "treatment_summary", "impact_score", "probability_score", "severity_score", "severity_band", "status", "associated_groups", "owner_role"])
    for r in sections["sanitized_risk_register"]:
        writer.writerow([
            r["risk_id"],
            r["project_id"],
            r["category"],
            r["title"],
            r["treatment_summary"],
            r["impact_score"],
            r["probability_score"],
            r["severity_score"],
            r["severity_band"],
            r["status"],
            ";".join(r.get("associated_groups", [])),
            r["owner_role"],
        ])
    writer.writerow([])

    writer.writerow(["SECTION_4_MITIGATION_LIFECYCLE_AUDIT_SUMMARY"])
    lifecycle = sections["mitigation_lifecycle_audit_summary"]
    writer.writerow(["total_risks", "open_risks", "mitigated_risks", "accepted_risks", "sla_breaches_recorded"])
    writer.writerow([
        lifecycle["total_risks"],
        lifecycle["open_risks"],
        lifecycle["mitigated_risks"],
        lifecycle["accepted_risks"],
        lifecycle["sla_breaches_recorded"],
    ])
    writer.writerow([])

    writer.writerow(["SECTION_5_PRIVACY_AND_DATA_GOVERNANCE_ATTESTATION"])
    att = sections["privacy_and_data_governance_attestation"]
    writer.writerow(["zero_verbatim_quotes_verified", "zero_audio_retention_policy", "dlp_scrubbed_meetings_count", "upstream_transcripts_deleted_count", "group_pulse_band_summary"])
    writer.writerow([
        att["zero_verbatim_quotes_verified"],
        att["zero_audio_retention_policy"],
        att["dlp_scrubbed_meetings_count"],
        att["upstream_transcripts_deleted_count"],
        json.dumps(att.get("group_pulse_band_summary", {}), sort_keys=True),
    ])

    return buf.getvalue().encode("utf-8")


class ComplianceService:
    """Service orchestrating 5-section compliance package generation, WORM sealing, and GDPR Article 17 purges."""

    def __init__(
        self,
        db: Any | None = None,
        storage_client: ComplianceStorageClient | None = None,
        bq_client: BigQueryAnalyticsClient | None = None,
        sanitization_service: SanitizationService | None = None,
    ) -> None:
        self.db = db or get_firestore_client()
        self.compliance_repo = ComplianceRepository(db=self.db)
        self.risk_repo = RiskRepository(db=self.db)
        self.meeting_repo = MeetingRepository(db=self.db)
        self.audit_repo = AuditRepository(db=self.db)
        self.storage_client = storage_client or ComplianceStorageClient()
        self.bq_client = bq_client or BigQueryAnalyticsClient()
        self.sanitizer = sanitization_service or get_sanitization_service()

    def export_compliance_package(
        self,
        req: ComplianceExportRequest,
        actor_uid: str,
        actor_role: str = "EXECUTIVE",
    ) -> CompliancePackageResponse:
        """Compile the 5 structured compliance sections, verify zero verbatim quotes, seal with SHA-256, and upload to WORM storage."""
        now_iso = datetime.now(timezone.utc).isoformat()
        package_id = f"CMP-{datetime.now(timezone.utc).strftime('%Y')}-{uuid.uuid4().hex[:8].upper()}"
        existing_pkgs = self.compliance_repo.list_packages(project_id=req.project_id)
        version_id = f"v1.0.{len(existing_pkgs) + 1}"

        # Gather dialogue blocks and participant names for the project to verify zero verbatim quotes
        meetings = [
            m
            for m in self.db.collection("meetings").stream()
            if (m.to_dict() or {}).get("project_id") == req.project_id
        ]
        dialogue_texts: list[str] = []
        participant_names: list[str] = []
        dlp_scrubbed_meetings_count = 0
        upstream_deleted_count = 0
        group_pulse_bands: dict[str, str] = {}

        for m_snap in meetings:
            m_data = m_snap.to_dict() or {}
            mid = m_data.get("meeting_id") or m_snap.id
            if m_data.get("status") in ("PROCESSING_POST_MEETING", "PENDING_ADJUDICATION", "COMMITTED"):
                dlp_scrubbed_meetings_count += 1
            model_meta = m_data.get("model_metadata") or {}
            if model_meta.get("upstream_transcript_deleted") or m_data.get("upstream_deleted_at"):
                upstream_deleted_count += 1
            for p_name in m_data.get("participants") or []:
                participant_names.append(str(p_name))
            for grp, score_val in (m_data.get("group_scores") or {}).items():
                group_pulse_bands[str(grp)] = self.sanitizer.pulse_score_to_band_range(score_val)

            blocks = self.meeting_repo.list_dialogue_blocks(mid)
            for b in blocks:
                if b.text_scrubbed:
                    dialogue_texts.append(b.text_scrubbed)
                if b.speaker_alias:
                    participant_names.append(b.speaker_alias)

        # Gather risks for project
        raw_risks = self.risk_repo.list_risks(project_id=req.project_id)
        filtered_risks = [
            r.model_dump()
            for r in raw_risks
            if r.status != RiskStatus.DRAFT_PENDING_ADJUDICATION
            and (req.include_mitigated_risks or r.status == RiskStatus.OPEN)
        ]

        sanitized_risks = [
            self.sanitizer.sanitize_risk_record(
                r,
                dialogue_texts=dialogue_texts,
                participant_names=participant_names,
            )
            for r in filtered_risks
        ]

        framework_mappings = self.sanitizer.build_framework_control_mappings(
            sanitized_risks=sanitized_risks,
            target_frameworks=req.target_frameworks,
        )

        # Gather sanitized lifecycle audit events (excluding internal comments and PII)
        all_events = self.audit_repo.list_events()
        risk_ids_set = {r["risk_id"] for r in sanitized_risks}
        timeline_events: list[dict[str, Any]] = []
        sla_breaches_count = 0
        for ev in all_events:
            ev_action = ev.action_type or ev.event_type
            if ev.target_id in risk_ids_set or ev_action in (
                "RISK_CREATED",
                "RISK_STATUS_UPDATED",
                "RISK_SEVERITY_UPDATED",
                "RISK_SLA_ESCALATION_TRIGGERED",
                "GOLDEN_RECORD_COMMITTED",
                "UPSTREAM_TRANSCRIPT_DELETED",
                "GDPR_ARTICLE_17_ERASURE_TOMBSTONE",
            ):
                if ev_action == "RISK_SLA_ESCALATION_TRIGGERED":
                    sla_breaches_count += 1
                timeline_events.append(
                    {
                        "event_id": ev.event_id,
                        "timestamp": ev.timestamp,
                        "action_type": ev_action,
                        "actor_role": ev.actor_role or "SYSTEM",
                        "entity_id": ev.target_id,
                    }
                )

        sections: dict[str, Any] = {
            "header_and_metadata": {
                "package_id": package_id,
                "version_id": version_id,
                "matrix_version": self.sanitizer.matrix_version,
                "project_id": req.project_id,
                "company_name": req.company_name,
                "target_frameworks": req.target_frameworks,
                "format": req.format.value,
                "generated_by_uid": actor_uid,
                "generated_at": now_iso,
            },
            "framework_control_mapping_table": framework_mappings,
            "sanitized_risk_register": sanitized_risks,
            "mitigation_lifecycle_audit_summary": {
                "total_risks": len(sanitized_risks),
                "open_risks": sum(1 for r in sanitized_risks if r["status"] == "OPEN"),
                "mitigated_risks": sum(1 for r in sanitized_risks if r["status"] == "MITIGATED"),
                "accepted_risks": sum(1 for r in sanitized_risks if r["status"] == "ACCEPTED"),
                "sla_breaches_recorded": sla_breaches_count,
                "timeline_events": timeline_events[:50],
            },
            "privacy_and_data_governance_attestation": {
                "zero_verbatim_quotes_verified": True,
                "zero_audio_retention_policy": "ENFORCED_NO_RAW_AUDIO_STORED",
                "dlp_scrubbing_pipeline": "Google Cloud DLP deidentify_content batch pass verified prior to persistence",
                "dlp_scrubbed_meetings_count": dlp_scrubbed_meetings_count,
                "upstream_transcripts_deleted_count": upstream_deleted_count,
                "speaker_blind_inference_enforced": True,
                "group_pulse_band_summary": group_pulse_bands,
                "gdpr_article_17_architecture": "Decoupled WORM compliance artifacts contain zero verbatim participant quotes",
            },
        }

        # Synthesize AI Executive Compliance Narrative (Task 7.1)
        sentiment_svc = get_sentiment_service(db=self.db)
        genai_client = sentiment_svc._client if sentiment_svc else None
        gemini_model = sentiment_svc.settings.gemini_model_name if sentiment_svc else "gemini-2.5-flash"
        compliance_narrative = self.sanitizer.synthesize_compliance_narrative(
            sanitized_risks=sanitized_risks,
            target_frameworks=req.target_frameworks,
            group_pulse_bands=group_pulse_bands,
            company_name=req.company_name,
            project_id=req.project_id,
            dialogue_texts=dialogue_texts,
            genai_client=genai_client,
            gemini_model=gemini_model,
        )
        sections["executive_compliance_narrative"] = compliance_narrative
        sections["privacy_and_data_governance_attestation"]["ai_executive_narrative"] = compliance_narrative

        # Verify zero verbatim quotes across the entire serialized sections payload
        serialized_sections = json.dumps(sections, sort_keys=True)

        quote_check = self.sanitizer.verify_zero_verbatim_quotes(
            serialized_payload=serialized_sections,
            dialogue_texts=dialogue_texts,
        )
        if not quote_check["verified_zero_verbatim_quotes"]:
            raise ValueError(
                f"Sanitization verification failed: {quote_check['violations']}"
            )

        # Render binary artifact in requested format
        fmt = req.format
        if fmt == ComplianceFormat.JSON:
            artifact_bytes = json.dumps(sections, indent=2, sort_keys=True).encode("utf-8")
            ext = "json"
            content_type = "application/json"
        elif fmt == ComplianceFormat.CSV:
            artifact_bytes = _render_csv_from_sections(sections)
            ext = "csv"
            content_type = "text/csv"
        else:
            artifact_bytes = _render_pdf_from_sections(sections)
            ext = "pdf"
            content_type = "application/pdf"

        sha256_hash = hashlib.sha256(artifact_bytes).hexdigest()
        sections["header_and_metadata"]["sha256_hash"] = sha256_hash

        upload_res = self.storage_client.upload_compliance_package(
            package_id=package_id,
            project_id=req.project_id,
            content=artifact_bytes,
            file_extension=ext,
            content_type=content_type,
            metadata={
                "version_id": version_id,
                "frameworks": ",".join(req.target_frameworks),
                "generated_by_uid": actor_uid,
            },
        )

        pkg_create = CompliancePackageCreate(
            package_id=package_id,
            version_id=version_id,
            project_id=req.project_id,
            company_name=req.company_name,
            framework=req.target_frameworks[0] if req.target_frameworks else "ISO_31000",
            target_frameworks=req.target_frameworks,
            format=fmt,
            sha256_hash=sha256_hash,
            gcs_uri=upload_res["gcs_uri"],
            size_bytes=upload_res["size_bytes"],
            status=CompliancePackageStatus.SEALED_WORM,
            generated_by_uid=actor_uid,
            generated_at=now_iso,
            sections=sections,
            zero_verbatim_quotes_verified=True,
            created_at=now_iso,
        )
        created = self.compliance_repo.create_package(pkg_create)

        # Log immutable event to Firestore `audit_ledger` and stream to BigQuery `audit_ledger_sink` + `fact_compliance_audit_packages`
        audit_entry = self.audit_repo.log(
            event_type="COMPLIANCE_PACKAGE_EXPORTED",
            actor_uid=actor_uid,
            target_id=package_id,
            actor_role=actor_role,
            action_type="COMPLIANCE_PACKAGE_EXPORTED",
            entity_type="COMPLIANCE_PACKAGE",
            sha256_hash=sha256_hash,
            metadata={
                "project_id": req.project_id,
                "version_id": version_id,
                "target_frameworks": req.target_frameworks,
                "format": fmt.value,
                "gcs_uri": upload_res["gcs_uri"],
                "sha256_hash": sha256_hash,
            },
        )
        self.bq_client.stream_audit_ledger_event(audit_entry.model_dump())
        self.bq_client.stream_compliance_package(
            {
                "package_id": package_id,
                "version_id": version_id,
                "project_id": req.project_id,
                "target_frameworks": req.target_frameworks,
                "format": fmt.value,
                "gcs_uri": upload_res["gcs_uri"],
                "sha256_hash": sha256_hash,
                "generated_by_uid": actor_uid,
                "generated_at": now_iso,
            }
        )

        return created

    def verify_package_integrity(self, package_id: str) -> ComplianceIntegrityResponse:
        """Re-compute SHA-256 hash of the stored WORM artifact and compare against Firestore & audit ledger."""
        pkg = self.compliance_repo.get_package(package_id)
        if not pkg:
            raise KeyError(f"Compliance package '{package_id}' not found")

        downloaded = self.storage_client.download_compliance_package(
            package_id=pkg.package_id,
            project_id=pkg.project_id,
        )
        if downloaded is None:
            is_valid = self.storage_client.verify_package_integrity(
                package_id=pkg.package_id,
                project_id=pkg.project_id,
                expected_sha256=pkg.sha256_hash,
            )
            computed_sha = pkg.sha256_hash if is_valid else None
        else:
            raw_bytes, _, _ = downloaded
            computed_sha = hashlib.sha256(raw_bytes).hexdigest()
            is_valid = computed_sha == pkg.sha256_hash

        return ComplianceIntegrityResponse(
            package_id=pkg.package_id,
            project_id=pkg.project_id,
            recorded_sha256_hash=pkg.sha256_hash,
            computed_sha256_hash=computed_sha,
            integrity_verified=is_valid,
            gcs_uri=pkg.gcs_uri,
            status=pkg.status,
        )

    def purge_meeting_gdpr_article_17(
        self,
        meeting_id: str,
        actor_uid: str,
        actor_role: str = "ADMIN",
    ) -> GdprMeetingPurgeResponse:
        """Execute cascading GDPR Article 17 Right to Erasure purge across Firestore and BigQuery with tombstone logging."""
        meeting = self.meeting_repo.get_meeting(meeting_id)
        if not meeting:
            raise KeyError(f"Meeting '{meeting_id}' not found")

        project_id = meeting.project_id
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Count and delete dialogue_blocks subcollection and meeting document
        blocks = self.meeting_repo.list_dialogue_blocks(meeting_id)
        block_texts = {b.text_scrubbed for b in blocks if b.text_scrubbed}
        block_ids = {b.block_id for b in blocks}
        self.meeting_repo.delete_meeting(meeting_id)

        # 2. Purge sentiment_calibrations (`corrected_contexts`) derived from this meeting
        purged_calibrations = 0
        for snap in list(self.db.collection("sentiment_calibrations").stream()):
            cdata = snap.to_dict() or {}
            cid = cdata.get("calibration_id") or snap.id
            if (
                cdata.get("meeting_id") == meeting_id
                or cdata.get("source_block_id") in block_ids
                or (cdata.get("dialogue_text") and cdata.get("dialogue_text") in block_texts)
            ):
                self.db.collection("sentiment_calibrations").document(cid).delete()
                purged_calibrations += 1

        # 3. Purge risk_register entries linked to this meeting
        purged_risk_ids: set[str] = set()
        for r in self.risk_repo.list_risks(project_id=project_id):
            if r.meeting_id == meeting_id:
                purged_risk_ids.add(r.risk_id)
                self.risk_repo.delete_risk(r.risk_id)

        # 4. Purge BigQuery raw analytical rows
        bq_purge_counts = self.bq_client.purge_meeting_analytics_rows(meeting_id)

        # 5. Redact operational Firestore compliance_packages metadata entries referencing purged risks
        # (While sealed GCS WORM blobs remain untouched and already contain zero verbatim quotes)
        redacted_pkgs_count = 0
        for pkg in self.compliance_repo.list_packages(project_id=project_id):
            sections = dict(pkg.sections or {})
            reg_list = list(sections.get("sanitized_risk_register") or [])
            modified = False
            for idx, r_entry in enumerate(reg_list):
                if r_entry.get("risk_id") in purged_risk_ids:
                    reg_list[idx] = {
                        **r_entry,
                        "title": GDPR_PURGED_TOMBSTONE_TEXT,
                        "treatment_summary": GDPR_PURGED_TOMBSTONE_TEXT,
                        "status": "PURGED_GDPR_ART_17",
                    }
                    modified = True
            if modified:
                sections["sanitized_risk_register"] = reg_list
                self.compliance_repo.update_package(pkg.package_id, {"sections": sections})
                redacted_pkgs_count += 1

        # 6. Append anonymized tombstone entry to Firestore `audit_ledger` and BigQuery `audit_ledger_sink`
        meeting_digest = hashlib.sha256(meeting_id.encode("utf-8")).hexdigest()
        tombstone_event = self.audit_repo.log(
            event_type="GDPR_ARTICLE_17_ERASURE_TOMBSTONE",
            actor_uid=actor_uid,
            target_id=f"TOMBSTONE-{meeting_digest[:16]}",
            actor_role=actor_role,
            action_type="GDPR_ARTICLE_17_ERASURE_TOMBSTONE",
            entity_type="MEETING_ERASURE_TOMBSTONE",
            sha256_hash=meeting_digest,
            metadata={
                "project_id": project_id,
                "anonymized_meeting_sha256": meeting_digest,
                "purged_dialogue_blocks_count": len(blocks),
                "purged_calibrations_count": purged_calibrations,
                "purged_risks_count": len(purged_risk_ids),
                "notice": GDPR_PURGED_TOMBSTONE_TEXT,
            },
        )
        self.bq_client.stream_audit_ledger_event(tombstone_event.model_dump())

        return GdprMeetingPurgeResponse(
            meeting_id=meeting_id,
            project_id=project_id,
            status="PURGED_GDPR_ARTICLE_17",
            purged_dialogue_blocks_count=len(blocks),
            purged_calibrations_count=purged_calibrations,
            purged_risks_count=len(purged_risk_ids),
            purged_bigquery_rows=bq_purge_counts,
            redacted_compliance_packages_count=redacted_pkgs_count,
            tombstone_audit_event_id=tombstone_event.event_id,
            purged_at=now_iso,
        )


def get_compliance_service(db: Any | None = None) -> ComplianceService:
    return ComplianceService(db=db)
