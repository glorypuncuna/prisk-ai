import os
from pathlib import Path
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.database import get_firestore_client
from app.core.enums import UserRole
from app.core.firebase import initialize_firebase_app, set_firebase_custom_user_claims
from app.core.storage import ComplianceStorageClient


def seed_development_data() -> None:
    """Seed a default MANAGER account (`manager@enterprise.com`) and `proj-alpha` for local dev testing."""
    settings = get_settings()
    if settings.environment != "development" or not settings.use_in_memory_firestore:
        return

    db = get_firestore_client()
    now_iso = datetime.now(timezone.utc).isoformat()
    admin_uid = "uid_admin_enterprise_com"
    admin_ref = db.collection("users").document(admin_uid)
    if not admin_ref.get().exists:
        admin_ref.set(
            {
                "uid": admin_uid,
                "email": "admin@enterprise.com",
                "first_name": "Super",
                "last_name": "Administrator",
                "phone_number": "+6281100000001",
                "role": UserRole.ADMIN.value,
                "auth_provider": "password",
                "assigned_project_ids": ["proj-alpha", "proj-beta"],
                "onboarding_status": "ACTIVE",
                "created_at": now_iso,
                "last_login_at": now_iso,
            }
        )
        set_firebase_custom_user_claims(admin_uid, {"role": UserRole.ADMIN.value, "assigned_project_ids": ["proj-alpha", "proj-beta"]})

    manager_uid = "uid_manager_enterprise_com"
    mgr_ref = db.collection("users").document(manager_uid)
    if not mgr_ref.get().exists:
        mgr_ref.set(
            {
                "uid": manager_uid,
                "email": "manager@enterprise.com",
                "first_name": "Enterprise",
                "last_name": "Manager",
                "phone_number": "+6281100001111",
                "role": UserRole.MANAGER.value,
                "auth_provider": "password",
                "assigned_project_ids": ["proj-alpha", "proj-beta"],
                "onboarding_status": "ACTIVE",
                "created_at": now_iso,
                "last_login_at": now_iso,
            }
        )
        set_firebase_custom_user_claims(manager_uid, {"role": UserRole.MANAGER.value, "assigned_project_ids": ["proj-alpha", "proj-beta"]})

    executive_uid = "uid_executive_enterprise_com"
    exec_ref = db.collection("users").document(executive_uid)
    if not exec_ref.get().exists:
        exec_ref.set(
            {
                "uid": executive_uid,
                "email": "executive@enterprise.com",
                "first_name": "Chief",
                "last_name": "Executive",
                "phone_number": "+6281199990000",
                "role": UserRole.EXECUTIVE.value,
                "auth_provider": "password",
                "assigned_project_ids": ["proj-alpha", "proj-beta"],
                "onboarding_status": "ACTIVE",
                "created_at": now_iso,
                "last_login_at": now_iso,
            }
        )
        set_firebase_custom_user_claims(executive_uid, {"role": UserRole.EXECUTIVE.value, "assigned_project_ids": ["proj-alpha", "proj-beta"]})

    proj_ref = db.collection("projects").document("proj-alpha")
    if not proj_ref.get().exists:
        proj_ref.set(
            {
                "project_id": "proj-alpha",
                "name": "Project Alpha: Core Enterprise Risk",
                "description": "Default enterprise project workspace for local testing",
                "canonical_groups": [
                    "Client Legal & Compliance",
                    "Client Executive Sponsor",
                    "Client Engineering",
                    "Internal Delivery Team",
                ],
                "owner_uid": manager_uid,
                "created_at": now_iso,
            }
        )

    adj_mtg_id = "mtg_alpha_adjudication"
    adj_mtg_ref = db.collection("meetings").document(adj_mtg_id)
    if not adj_mtg_ref.get().exists:
        adj_mtg_ref.set(
            {
                "meeting_id": adj_mtg_id,
                "project_id": "proj-alpha",
                "title": "Q4 Scope & Compliance Gate Review",
                "platform": "google_meet",
                "meeting_date": now_iso,
                "status": "PENDING_ADJUDICATION",
                "pulse_score": 56.0,
                "group_scores": {
                    "Client Legal & Compliance": {
                        "pulse_score": 38.0,
                        "block_count": 2,
                        "top_liked_words": ["audit", "clarity"],
                        "top_disliked_words": ["delayed", "blocked", "liability"],
                    },
                    "Internal Delivery Team": {
                        "pulse_score": 74.0,
                        "block_count": 1,
                        "top_liked_words": ["confirmed", "resolved", "milestone"],
                        "top_disliked_words": [],
                    },
                },
                "mom_summary": {
                    "date_time": now_iso,
                    "location": "Google Meet",
                    "title": "Q4 Scope & Compliance Gate Review",
                    "agenda": ["UAT Compliance Sign-off", "Audit Log Delivery Schedule"],
                    "topics_of_discussion": ["DLP verification", "UAT deployment blockers"],
                    "summary": "Client Legal flagged audit log delays blocking UAT sign-off; Internal Delivery committed to Friday remediation.",
                    "action_items": [
                        {
                            "action_id": "act-01",
                            "description": "Deliver revised audit log schema to Client Legal",
                            "owner_group": "Internal Delivery Team",
                            "due_date": "2026-10-25",
                        }
                    ],
                    "recommended_mitigations": [
                        "Schedule joint verification review before UAT deployment."
                    ],
                },
                "participants": ["ms_spk_01", "ms_spk_02"],
                "ephemeral_speaker_map": {
                    "ms_spk_01": "Client Legal & Compliance",
                    "ms_spk_02": "Internal Delivery Team",
                },
                "created_at": now_iso,
            }
        )
        blocks_col = adj_mtg_ref.collection("dialogue_blocks")
        blocks_col.document("blk-0001").set(
            {
                "block_id": "blk-0001",
                "sequence_index": 0,
                "start_time_sec": 12.0,
                "end_time_sec": 28.5,
                "speaker_alias": "Sarah Jenkins (Chief Counsel)",
                "display_speaker_label": "Sarah Jenkins (Chief Counsel)",
                "ephemeral_speaker_account_id": "ms_spk_01",
                "group_id": "Client Legal & Compliance",
                "group_name": "Client Legal & Compliance",
                "company_name": "Acme Financial Corp",
                "text_scrubbed": (
                    "We cannot sign off on the UAT deployment if the audit logs are delayed again. "
                    "Reach my office at [PHONE_NUMBER] or [EMAIL_ADDRESS] if we need an emergency review."
                ),
                "word_count": 28,
                "dlp_redaction_flags": ["PHONE_NUMBER", "EMAIL_ADDRESS"],
                "sentiment_score": 36.0,
                "ai_initial_score": 36.0,
                "ai_confidence": 0.91,
                "rubric_scores": {
                    "emotional_valence": 8,
                    "delivery_alignment": 7,
                    "relationship_trust": 10,
                    "momentum_commitment": 11,
                },
                "is_split": False,
                "is_pinned": False,
                "is_human_overridden": False,
            }
        )
        blocks_col.document("blk-0002").set(
            {
                "block_id": "blk-0002",
                "sequence_index": 1,
                "start_time_sec": 30.0,
                "end_time_sec": 44.0,
                "speaker_alias": "David Kim (Delivery Lead)",
                "display_speaker_label": "David Kim (Delivery Lead)",
                "ephemeral_speaker_account_id": "ms_spk_02",
                "group_id": "Internal Delivery Team",
                "group_name": "Internal Delivery Team",
                "company_name": "Acme Financial Corp",
                "text_scrubbed": (
                    "Confirmed, our engineering team resolved the pipeline bottleneck and completed "
                    "the encryption verification milestone for account [BANK_ACCOUNT]."
                ),
                "word_count": 18,
                "dlp_redaction_flags": ["BANK_ACCOUNT"],
                "sentiment_score": 74.0,
                "ai_initial_score": 74.0,
                "ai_confidence": 0.89,
                "rubric_scores": {
                    "emotional_valence": 18,
                    "delivery_alignment": 19,
                    "relationship_trust": 18,
                    "momentum_commitment": 19,
                },
                "is_split": False,
                "is_pinned": False,
                "is_human_overridden": False,
            }
        )
        blocks_col.document("blk-0003").set(
            {
                "block_id": "blk-0003",
                "sequence_index": 2,
                "start_time_sec": 45.5,
                "end_time_sec": 59.0,
                "speaker_alias": "Sarah Jenkins (Chief Counsel)",
                "display_speaker_label": "Sarah Jenkins (Chief Counsel)",
                "ephemeral_speaker_account_id": "ms_spk_01",
                "group_id": "Client Legal & Compliance",
                "group_name": "Client Legal & Compliance",
                "company_name": "Acme Financial Corp",
                "text_scrubbed": (
                    "If the Friday deadline slips, we will freeze production cutover. "
                    "However, the updated security documentation looks aligned with our contract."
                ),
                "word_count": 20,
                "dlp_redaction_flags": [],
                "sentiment_score": 41.0,
                "ai_initial_score": 41.0,
                "ai_confidence": 0.87,
                "rubric_scores": {
                    "emotional_valence": 10,
                    "delivery_alignment": 9,
                    "relationship_trust": 11,
                    "momentum_commitment": 11,
                },
                "is_split": False,
                "is_pinned": False,
                "is_human_overridden": False,
            }
        )
        db.collection("risk_register").document("RSK-ALPHA-01").set(
            {
                "risk_id": "RSK-ALPHA-01",
                "project_id": "proj-alpha",
                "meeting_id": adj_mtg_id,
                "company_name": "Acme Financial Corp",
                "associated_groups": ["Client Legal & Compliance"],
                "title": "UAT Sign-off Blocked by Audit Log Delays",
                "description": "Client Legal stated UAT deployment sign-off will be withheld if audit log delivery slips past Friday.",
                "category": "COMPLIANCE",
                "status": "DRAFT_PENDING_ADJUDICATION",
                "impact": 5,
                "probability": 4,
                "severity_score": 20,
                "severity_band": "CRITICAL",
                "owner_uid": manager_uid,
                "sla_escalation_tier": "24h",
                "mitigation_plan": {
                    "strategy": "Deliver interim audit schema documentation and run joint verification session."
                },
                "escalation_config": {
                    "enabled": True,
                    "sla_started_at": now_iso,
                    "last_escalated_tier_hours": 0,
                },
                "qualitative_commentary": [],
                "created_at": now_iso,
                "updated_at": now_iso,
            }
        )
        db.collection("risk_register").document("RSK-ALPHA-02").set(
            {
                "risk_id": "RSK-ALPHA-02",
                "project_id": "proj-alpha",
                "meeting_id": adj_mtg_id,
                "company_name": "Acme Financial Corp",
                "associated_groups": ["Internal Delivery Team", "Client Engineering"],
                "title": "Encryption Key Rotation Pipeline Latency",
                "description": "Throughput bottleneck during automated KMS key rotation under peak transaction load.",
                "category": "OPERATIONAL",
                "status": "OPEN",
                "impact": 4,
                "probability": 4,
                "severity_score": 16,
                "severity_band": "HIGH",
                "owner_uid": manager_uid,
                "sla_escalation_tier": "24h",
                "mitigation_plan": {
                    "strategy": "Provision dedicated key rotation worker pool and pre-warm KMS session cache."
                },
                "escalation_config": {
                    "enabled": True,
                    "sla_started_at": now_iso,
                    "last_escalated_tier_hours": 0,
                },
                "qualitative_commentary": [
                    {
                        "comment_id": "cmt-seed-01",
                        "author_uid": manager_uid,
                        "author_role": "MANAGER",
                        "comment": "Assigned engineering lead to benchmark KMS batch concurrency.",
                        "created_at": now_iso,
                    }
                ],
                "created_at": now_iso,
                "updated_at": now_iso,
            }
        )

    pkg_id = "PKG-ALPHA-01"
    pkg_ref = db.collection("compliance_packages").document(pkg_id)
    if not pkg_ref.get().exists:
        sample_pdf_bytes = (
            b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
            b"xref\n0 4\n0000000000 65535 f \ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n120\n%%EOF"
        )
        storage_client = ComplianceStorageClient()
        upload_meta = storage_client.upload_compliance_package(
            package_id=pkg_id,
            project_id="proj-alpha",
            content=sample_pdf_bytes,
            file_extension="pdf",
            content_type="application/pdf",
        )
        pkg_ref.set(
            {
                "package_id": pkg_id,
                "project_id": "proj-alpha",
                "company_name": "Acme Financial Corp",
                "framework": "ISO_31000",
                "target_frameworks": ["ISO_31000", "COSO", "SOC_2", "GDPR"],
                "format": "PDF",
                "sha256_hash": upload_meta["sha256_hash"],
                "gcs_uri": upload_meta["gcs_uri"],
                "status": "SEALED_WORM",
                "generated_by_uid": manager_uid,
                "generated_at": now_iso,
                "sections": {
                    "executive_summary": "Quarterly enterprise risk compliance audit archive.",
                    "risk_inventory": [{"risk_id": "RSK-ALPHA-01", "severity": 20}],
                },
                "created_at": now_iso,
            }
        )

    # --------------------------------------------------------------------------
    # Seed Project Horizon (Fintech Cloud Migration & Escrow)
    # --------------------------------------------------------------------------
    proj_horizon_ref = db.collection("projects").document("proj-horizon")
    if not proj_horizon_ref.get().exists:
        proj_horizon_ref.set(
            {
                "project_id": "proj-horizon",
                "name": "Fintech Cloud Migration & Escrow",
                "company_name": "Fintech Horizon Bank",
                "description": "Tier-1 multi-cloud banking infrastructure migration and SOX/SOC-2 compliance",
                "canonical_groups": [
                    "EXECUTIVE",
                    "ENGINEERING",
                    "REGULATOR",
                    "VENDOR",
                ],
                "alert_thresholds": {
                    "pulse_drop_delta": 12.0,
                    "minimum_pulse_score": 75.0,
                    "escalation_enabled": True,
                    "escalation_intervals_hours": [12, 24, 48],
                },
                "owner_uid": manager_uid,
                "created_at": now_iso,
            }
        )

    horizon_mtg_id = "mtg_horizon_kickoff"
    horizon_mtg_ref = db.collection("meetings").document(horizon_mtg_id)
    if not horizon_mtg_ref.get().exists:
        horizon_mtg_ref.set(
            {
                "meeting_id": horizon_mtg_id,
                "project_id": "proj-horizon",
                "title": "Fintech Cloud Migration Kickoff",
                "platform": "zoom",
                "meeting_date": now_iso,
                "status": "COMMITTED",
                "pulse_score": 92.5,
                "group_scores": {
                    "EXECUTIVE": {
                        "pulse_score": 95.0,
                        "block_count": 1,
                        "top_liked_words": ["approved", "charter"],
                        "top_disliked_words": [],
                    },
                    "ENGINEERING": {
                        "pulse_score": 91.0,
                        "block_count": 1,
                        "top_liked_words": ["failover", "multi-region"],
                        "top_disliked_words": [],
                    },
                },
                "mom_summary": {
                    "date_time": now_iso,
                    "location": "Zoom Boardroom",
                    "title": "Fintech Cloud Migration Kickoff",
                    "agenda": ["Board Charter Ratification", "Escrow Regulatory Setup"],
                    "topics_of_discussion": ["Multi-region failover tests", "SOX 404 audit compliance"],
                    "summary": "Charter approved by board. Sub-minute cross-region failover demonstrated.",
                    "action_items": [
                        {
                            "action_id": "act-b01",
                            "description": "Deliver final network topology diagram to regulator",
                            "owner_group": "ENGINEERING",
                            "due_date": "2026-10-30",
                        }
                    ],
                    "recommended_mitigations": ["Execute monthly tabletop disaster recovery drills."],
                },
                "participants": [admin_uid, manager_uid],
                "created_at": now_iso,
            }
        )
        horizon_blocks_col = horizon_mtg_ref.collection("dialogue_blocks")
        horizon_blocks_col.document("blk-horizon-01").set(
            {
                "block_id": "blk-horizon-01",
                "sequence_index": 0,
                "start_time_sec": 10.0,
                "end_time_sec": 25.0,
                "speaker_alias": "Bank CTO",
                "display_speaker_label": "Bank CTO (Executive Sponsor)",
                "group_id": "EXECUTIVE",
                "group_name": "EXECUTIVE",
                "company_name": "Fintech Horizon Bank",
                "text_scrubbed": "The migration charter is formally approved by the board with zero objections.",
                "word_count": 12,
                "dlp_redaction_flags": [],
                "sentiment_score": 95.0,
                "ai_initial_score": 95.0,
                "ai_confidence": 0.96,
                "rubric_scores": {
                    "emotional_valence": 24,
                    "delivery_alignment": 24,
                    "relationship_trust": 24,
                    "momentum_commitment": 23,
                },
                "is_split": False,
                "is_pinned": False,
                "is_human_overridden": False,
            }
        )

    db.collection("risk_register").document("RSK-HORIZON-01").set(
        {
            "risk_id": "RSK-HORIZON-01",
            "project_id": "proj-horizon",
            "meeting_id": horizon_mtg_id,
            "company_name": "Fintech Horizon Bank",
            "associated_groups": ["ENGINEERING", "REGULATOR"],
            "title": "Core Banking Cutover Rollback Window Exceeded",
            "description": "Database snapshot rollback during testing took 68 minutes, exceeding the regulatory 45-minute cutoff.",
            "category": "OPERATIONAL",
            "status": "OPEN",
            "impact": 5,
            "probability": 2,
            "severity_score": 10,
            "severity_band": "MEDIUM",
            "owner_uid": manager_uid,
            "sla_escalation_tier": "48h",
            "mitigation_plan": {
                "strategy": "Parallelizing partition restoration with incremental write logs."
            },
            "escalation_config": {
                "enabled": True,
                "sla_started_at": now_iso,
                "last_escalated_tier_hours": 0,
            },
            "qualitative_commentary": [],
            "created_at": now_iso,
            "updated_at": now_iso,
        }
    )

    pkg_horizon_id = "PKG-HORIZON-01"
    pkg_horizon_ref = db.collection("compliance_packages").document(pkg_horizon_id)
    if not pkg_horizon_ref.get().exists:
        pkg_horizon_ref.set(
            {
                "package_id": pkg_horizon_id,
                "project_id": "proj-horizon",
                "company_name": "Fintech Horizon Bank",
                "framework": "SOC_2",
                "target_frameworks": ["SOC_2", "ISO_31000", "COSO"],
                "format": "PDF",
                "sha256_hash": "112233445566778899aabbccddeeff00112233445566778899aabbccddeeff00",
                "gcs_uri": f"gs://prisk-compliance-packages-prisk-ai/proj-horizon/{pkg_horizon_id}.pdf",
                "status": "SEALED_WORM",
                "generated_by_uid": manager_uid,
                "generated_at": now_iso,
                "sections": {
                    "executive_summary": "Banking Cloud Escrow & Regulatory Certification.",
                },
                "created_at": now_iso,
            }
        )


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialize Firebase Admin SDK and seed local dev data on startup."""
    initialize_firebase_app()
    seed_development_data()
    yield


def create_app() -> FastAPI:
    """Create and configure the pRiskAI FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_v1_router, prefix=settings.api_v1_prefix)
    from app.api.v1.webhooks import router as webhooks_router
    from app.api.v1.risks import internal_jobs_router

    app.include_router(webhooks_router)
    app.include_router(internal_jobs_router)

    @app.get("/health", tags=["Health"])
    async def health_check() -> dict[str, str]:
        return {"status": "ok", "service": "priskai-backend"}

    @app.get("/healthz", tags=["Health"])
    async def healthz_check() -> dict[str, str]:
        return {
            "status": "healthy",
            "service": "priskai-app",
            "environment": settings.environment,
        }

    # Static assets and SPA routing fallback
    frontend_dist_dir = os.environ.get(
        "FRONTEND_DIST_DIR",
        str(Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"),
    )
    if not os.path.isdir(frontend_dist_dir):
        if os.path.isdir("/app/frontend/dist"):
            frontend_dist_dir = "/app/frontend/dist"
        elif os.path.isdir("frontend/dist"):
            frontend_dist_dir = os.path.abspath("frontend/dist")

    if os.path.isdir(frontend_dist_dir):
        assets_dir = os.path.join(frontend_dist_dir, "assets")
        if os.path.isdir(assets_dir):
            app.mount("/assets", StaticFiles(directory=assets_dir), name="static-assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str) -> Response:
            # Prevent catching API/job/webhook routes if they 404
            if (
                full_path.startswith("api/")
                or full_path.startswith("internal/")
                or full_path.startswith("webhooks/")
            ):
                return JSONResponse(status_code=404, content={"detail": f"Route /{full_path} not found"})

            file_path = os.path.join(frontend_dist_dir, full_path)
            if full_path and os.path.isfile(file_path):
                return FileResponse(file_path)

            index_file = os.path.join(frontend_dist_dir, "index.html")
            if os.path.isfile(index_file):
                return FileResponse(index_file)

            return JSONResponse(status_code=404, content={"detail": f"Path /{full_path} not found"})

    return app


app = create_app()


