import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from google.cloud import firestore
from google.cloud.firestore_v1.vector import Vector
import firebase_admin
from firebase_admin import auth, credentials

# Resolve service account credential path
CREDENTIALS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "service-account.json",
)

if not os.path.isfile(CREDENTIALS_PATH):
    alt_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "service-accounts.json",
    )
    if os.path.isfile(alt_path):
        CREDENTIALS_PATH = alt_path
    else:
        print(f"Error: Credentials file not found at {CREDENTIALS_PATH}")
        sys.exit(1)

with open(CREDENTIALS_PATH, "r", encoding="utf-8") as f:
    key_data = json.load(f)
    project_id = key_data.get("project_id", "prisk-ai")

print(f"Connecting to Cloud Firestore & Firebase Auth for project '{project_id}'...")
db = firestore.Client.from_service_account_json(CREDENTIALS_PATH, project=project_id)

cred = credentials.Certificate(CREDENTIALS_PATH)
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred, {"projectId": project_id})

# Helpers
def make_embedding(seed_val: float) -> Vector:
    """Generate deterministic normalized 768-dimensional float embedding."""
    raw = [math.sin(seed_val + i * 0.1) for i in range(768)]
    norm = math.sqrt(sum(x * x for x in raw)) or 1.0
    return Vector([round(x / norm, 6) for x in raw])

def make_embedding_list(seed_val: float) -> list[float]:
    raw = [math.sin(seed_val + i * 0.1) for i in range(768)]
    norm = math.sqrt(sum(x * x for x in raw)) or 1.0
    return [round(x / norm, 6) for x in raw]

now = datetime.now(timezone.utc)
now_iso = now.isoformat()

# ==============================================================================
# 1. USERS & FIREBASE AUTH CLAIMS
# ==============================================================================
users_data = [
    {
        "uid": "uid_superadmin",
        "email": "admin@enterprise.com",
        "password": "AdminPrisk2026!",
        "first_name": "Super",
        "last_name": "Administrator",
        "phone_number": "+14155550100",
        "role": "ADMIN",
        "assigned_project_ids": ["proj-alpha", "proj-beta"],
        "onboarding_status": "ACTIVE",
    },
    {
        "uid": "uid_executive_sarah",
        "email": "sarah.chen@enterprise.com",
        "password": "ExecutivePrisk2026!",
        "first_name": "Sarah",
        "last_name": "Chen",
        "phone_number": "+14155550101",
        "role": "EXECUTIVE",
        "assigned_project_ids": ["proj-alpha", "proj-beta"],
        "onboarding_status": "ACTIVE",
    },
    {
        "uid": "uid_adjudicator_marcus",
        "email": "marcus.vance@enterprise.com",
        "password": "AdjudicatorPrisk2026!",
        "first_name": "Marcus",
        "last_name": "Vance",
        "phone_number": "+14155550102",
        "role": "ADJUDICATOR",
        "assigned_project_ids": ["proj-alpha"],
        "onboarding_status": "ACTIVE",
    },
    {
        "uid": "uid_stakeholder_david",
        "email": "david.wright@clientcorp.com",
        "password": "StakeholderPrisk2026!",
        "first_name": "David",
        "last_name": "Wright",
        "phone_number": "+14155550103",
        "role": "EXTERNAL_STAKEHOLDER",
        "assigned_project_ids": ["proj-alpha"],
        "onboarding_status": "ACTIVE",
    },
]

print("\n--- Provisioning Users & Firebase Authentication ---")
for u in users_data:
    # 1a. Cloud Firestore user profile
    doc_data = {
        "uid": u["uid"],
        "email": u["email"],
        "first_name": u["first_name"],
        "last_name": u["last_name"],
        "phone_number": u["phone_number"],
        "role": u["role"],
        "auth_provider": "password",
        "assigned_project_ids": u["assigned_project_ids"],
        "onboarding_status": u["onboarding_status"],
        "created_at": (now - timedelta(days=30)).isoformat(),
        "last_login_at": now_iso,
    }
    db.collection("users").document(u["uid"]).set(doc_data, merge=True)

    # 1b. Firebase Auth user & Custom Claims
    try:
        auth_user = auth.get_user_by_email(u["email"])
        auth.update_user(
            auth_user.uid,
            password=u["password"],
            display_name=f"{u['first_name']} {u['last_name']}",
            email_verified=True,
        )
        target_auth_uid = auth_user.uid
    except Exception:
        auth_user = auth.create_user(
            uid=u["uid"],
            email=u["email"],
            password=u["password"],
            display_name=f"{u['first_name']} {u['last_name']}",
            email_verified=True,
        )
        target_auth_uid = auth_user.uid

    # Set custom claims
    auth.set_custom_user_claims(
        target_auth_uid,
        {
            "role": u["role"],
            "assigned_project_ids": u["assigned_project_ids"],
        },
    )
    print(f"  ✓ User {u['email']} [{u['role']}] with projects {u['assigned_project_ids']}")

# ==============================================================================
# 2. PROJECTS (proj-alpha and proj-beta)
# ==============================================================================
projects_data = [
    {
        "project_id": "proj-alpha",
        "name": "Project Alpha Core Oversight",
        "company_name": "Enterprise Global Corp",
        "description": "Core enterprise IT transformation, risk oversight, and multi-vendor delivery alignment.",
        "canonical_groups": ["BUYER", "INTERNAL", "VENDOR", "LEGAL", "SECURITY"],
        "alert_thresholds": {
            "pulse_drop_delta": 15.0,
            "minimum_pulse_score": 70.0,
            "escalation_enabled": True,
            "escalation_intervals_hours": [24, 48, 72],
        },
        "owner_uid": "uid_superadmin",
        "created_at": (now - timedelta(days=30)).isoformat(),
        "updated_at": now_iso,
    },
    {
        "project_id": "proj-beta",
        "name": "Fintech Cloud Migration & Escrow",
        "company_name": "Fintech Horizon Bank",
        "description": "Tier-1 multi-cloud banking infrastructure migration, regulatory escrow, and SOX/SOC-2 compliance.",
        "canonical_groups": ["EXECUTIVE", "ENGINEERING", "REGULATOR", "VENDOR"],
        "alert_thresholds": {
            "pulse_drop_delta": 12.0,
            "minimum_pulse_score": 75.0,
            "escalation_enabled": True,
            "escalation_intervals_hours": [12, 24, 48],
        },
        "owner_uid": "uid_superadmin",
        "created_at": (now - timedelta(days=20)).isoformat(),
        "updated_at": now_iso,
    },
]

print("\n--- Provisioning Projects ---")
for p in projects_data:
    db.collection("projects").document(p["project_id"]).set(p, merge=True)
    print(f"  ✓ Project: {p['project_id']} - {p['name']}")

# ==============================================================================
# 3. PROJECT INVITATIONS
# ==============================================================================
invitations_data = [
    {
        "invitation_id": "inv_alpha_01",
        "project_id": "proj-alpha",
        "project_name": "Project Alpha Core Oversight",
        "invitee_email": "elena.rostova@partnerconsulting.com",
        "invited_by_uid": "uid_superadmin",
        "status": "PENDING",
        "created_at": (now - timedelta(days=2)).isoformat(),
        "accepted_at": None,
    },
    {
        "invitation_id": "inv_beta_01",
        "project_id": "proj-beta",
        "project_name": "Fintech Cloud Migration & Escrow",
        "invitee_email": "audit.lead@fintechreg.gov",
        "invited_by_uid": "uid_superadmin",
        "status": "PENDING",
        "created_at": (now - timedelta(days=1)).isoformat(),
        "accepted_at": None,
    },
    {
        "invitation_id": "inv_alpha_sarah",
        "project_id": "proj-alpha",
        "project_name": "Project Alpha Core Oversight",
        "invitee_email": "sarah.chen@enterprise.com",
        "invited_by_uid": "uid_superadmin",
        "status": "ACCEPTED",
        "created_at": (now - timedelta(days=25)).isoformat(),
        "accepted_at": (now - timedelta(days=24)).isoformat(),
    },
]

print("\n--- Provisioning Project Invitations ---")
for inv in invitations_data:
    db.collection("project_invitations").document(inv["invitation_id"]).set(inv, merge=True)
    print(f"  ✓ Invitation: {inv['invitation_id']} ({inv['invitee_email']} -> {inv['project_id']} [{inv['status']}])")

# ==============================================================================
# 4. MEETINGS & SUBCOLLECTION DIALOGUE BLOCKS
# ==============================================================================
meetings_data = [
    # Project Alpha Meetings
    {
        "meeting_id": "mtg_alpha_baseline",
        "project_id": "proj-alpha",
        "title": "Baseline Architecture & Risk Review",
        "platform": "google_meet",
        "meeting_date": (now - timedelta(days=14)).isoformat(),
        "status": "COMMITTED",
        "pulse_score": 88.5,
        "group_scores": {
            "BUYER": {"pulse_score": 88.0, "block_count": 2, "top_liked_words": ["clarity", "milestone", "benchmarks"], "top_disliked_words": []},
            "INTERNAL": {"pulse_score": 89.0, "block_count": 2, "top_liked_words": ["architecture", "compliance", "uptime"], "top_disliked_words": []},
            "VENDOR": {"pulse_score": 87.0, "block_count": 1, "top_liked_words": ["pipeline", "kms", "custody"], "top_disliked_words": []},
        },
        "mom_summary": {
            "date_time": (now - timedelta(days=14)).isoformat(),
            "location": "Google Meet",
            "title": "Baseline Architecture & Risk Review",
            "agenda": ["Architecture Baseline", "DLP Scrubbing Policies", "SLA Targets"],
            "topics_of_discussion": ["WORM storage retention rules", "Latency budget under 200ms", "Production rollout schedule"],
            "summary": "Engineering confirmed cloud schemas and WORM retention compliance are active. Buyer approved baseline architecture with 99.99% uptime requirement.",
            "action_items": [
                {"action_id": "act-001", "description": "Configure Google Cloud KMS key rotation for sensitive audit logs", "owner_group": "INTERNAL", "due_date": (now - timedelta(days=7)).isoformat()},
                {"action_id": "act-002", "description": "Provide SLA sign-off matrix for executive review", "owner_group": "VENDOR", "due_date": (now - timedelta(days=5)).isoformat()},
            ],
            "recommended_mitigations": ["Maintain active canary monitoring for webhook ingestion."],
        },
        "participants": ["uid_superadmin", "uid_executive_sarah", "uid_stakeholder_david"],
        "created_at": (now - timedelta(days=14)).isoformat(),
        "dialogue_blocks": [
            {
                "block_id": "blk_alpha_101",
                "sequence_index": 1,
                "speaker_alias": "Super Admin",
                "display_speaker_label": "Super Administrator (Internal Lead)",
                "group_id": "INTERNAL",
                "group_name": "INTERNAL",
                "company_name": "Enterprise Global Corp",
                "text_scrubbed": "All cloud schemas and WORM retention compliance are active across both primary and failover storage nodes.",
                "word_count": 16,
                "dlp_redaction_flags": [],
                "sentiment_score": 92.0,
                "ai_initial_score": 92.0,
                "ai_confidence": 0.95,
                "rubric_scores": {"emotional_valence": 23.0, "delivery_alignment": 23.5, "relationship_trust": 23.0, "momentum_commitment": 22.5},
                "embedding_seed": 1.1,
                "is_split": False,
                "is_pinned": False,
                "is_human_overridden": False,
                "xai_attribution": {
                    "computed_at": (now - timedelta(days=14)).isoformat(),
                    "attributions": [
                        {"verbatim_phrase": "WORM retention compliance are active", "start_char": 22, "end_char": 57, "attribution_weight": 0.85, "rubric_dimension": "delivery_alignment", "rationale": "Direct affirmation of security regulatory compliance."}
                    ]
                }
            },
            {
                "block_id": "blk_alpha_102",
                "sequence_index": 2,
                "speaker_alias": "David Wright",
                "display_speaker_label": "David Wright (Client Stakeholder)",
                "group_id": "BUYER",
                "group_name": "BUYER",
                "company_name": "Client Corp",
                "text_scrubbed": "The latency benchmarks look solid, but we must guarantee 99.99% uptime in production before commercial sign-off.",
                "word_count": 17,
                "dlp_redaction_flags": [],
                "sentiment_score": 85.0,
                "ai_initial_score": 85.0,
                "ai_confidence": 0.92,
                "rubric_scores": {"emotional_valence": 20.0, "delivery_alignment": 22.0, "relationship_trust": 21.5, "momentum_commitment": 21.5},
                "embedding_seed": 1.2,
                "is_split": False,
                "is_pinned": False,
                "is_human_overridden": False,
                "xai_attribution": {
                    "computed_at": (now - timedelta(days=14)).isoformat(),
                    "attributions": [
                        {"verbatim_phrase": "latency benchmarks look solid", "start_char": 4, "end_char": 33, "attribution_weight": 0.78, "rubric_dimension": "relationship_trust", "rationale": "Constructive validation of baseline engineering progress."},
                        {"verbatim_phrase": "guarantee 99.99% uptime", "start_char": 48, "end_char": 71, "attribution_weight": 0.65, "rubric_dimension": "momentum_commitment", "rationale": "High SLA expectation setting conditional for sign-off."}
                    ]
                }
            },
            {
                "block_id": "blk_alpha_103",
                "sequence_index": 3,
                "speaker_alias": "Vendor Tech Lead",
                "display_speaker_label": "Vendor Tech Lead (Cloud Services)",
                "group_id": "VENDOR",
                "group_name": "VENDOR",
                "company_name": "Partner Cloud Solutions",
                "text_scrubbed": "Our deployment pipeline is fully integrated with Cloud KMS and HSM hardware key custody for envelope encryption.",
                "word_count": 17,
                "dlp_redaction_flags": [],
                "sentiment_score": 88.0,
                "ai_initial_score": 88.0,
                "ai_confidence": 0.94,
                "rubric_scores": {"emotional_valence": 21.0, "delivery_alignment": 23.0, "relationship_trust": 22.0, "momentum_commitment": 22.0},
                "embedding_seed": 1.3,
                "is_split": False,
                "is_pinned": False,
                "is_human_overridden": False,
                "xai_attribution": None
            }
        ]
    },
    {
        "meeting_id": "mtg_alpha_security",
        "project_id": "proj-alpha",
        "title": "Security Architecture & DLP Compliance Audit",
        "platform": "zoom",
        "meeting_date": (now - timedelta(days=7)).isoformat(),
        "status": "GOLDEN_RECORD",
        "pulse_score": 74.0,
        "group_scores": {
            "BUYER": {"pulse_score": 71.0, "block_count": 1, "top_liked_words": ["containment"], "top_disliked_words": ["audit", "incident"]},
            "INTERNAL": {"pulse_score": 78.0, "block_count": 2, "top_liked_words": ["transforms", "scrubbing"], "top_disliked_words": ["pii"]},
            "LEGAL": {"pulse_score": 73.0, "block_count": 1, "top_liked_words": ["controls"], "top_disliked_words": ["unredacted"]},
        },
        "mom_summary": {
            "date_time": (now - timedelta(days=7)).isoformat(),
            "location": "Zoom Security Room",
            "title": "Security Architecture & DLP Compliance Audit",
            "agenda": ["PII Detection in Logs", "DLP Regex Rules", "Golden Record Certification"],
            "topics_of_discussion": ["Scrubbing account identifiers before persistence", "Audit committee disclosures"],
            "summary": "Audit identified potential unredacted client account numbers in debug logs. Engineering verified immediate remediation via Google Cloud DLP de-identification transforms.",
            "action_items": [
                {"action_id": "act-010", "description": "Review and seal SOC 2 Type II audit report for compliance archive", "owner_group": "LEGAL", "due_date": (now - timedelta(days=2)).isoformat()}
            ],
            "recommended_mitigations": ["Enforce pre-commit git hooks scanning for high-entropy secrets and account numbers."],
        },
        "participants": ["uid_superadmin", "uid_adjudicator_marcus", "uid_stakeholder_david"],
        "created_at": (now - timedelta(days=7)).isoformat(),
        "dialogue_blocks": [
            {
                "block_id": "blk_alpha_201",
                "sequence_index": 1,
                "speaker_alias": "Elena Legal",
                "display_speaker_label": "Elena Vance (General Counsel)",
                "group_id": "LEGAL",
                "group_name": "LEGAL",
                "company_name": "Enterprise Global Corp",
                "text_scrubbed": "We detected unredacted [ACCOUNT_NUMBER_REDACTED] references in debug logs that must be scrubbed immediately under GDPR Article 32.",
                "word_count": 17,
                "dlp_redaction_flags": ["ACCOUNT_NUMBER", "GDPR_PII"],
                "sentiment_score": 58.0,
                "ai_initial_score": 58.0,
                "ai_confidence": 0.90,
                "rubric_scores": {"emotional_valence": 12.0, "delivery_alignment": 15.0, "relationship_trust": 16.0, "momentum_commitment": 15.0},
                "embedding_seed": 2.1,
                "is_split": False,
                "is_pinned": False,
                "is_human_overridden": False,
                "xai_attribution": {
                    "computed_at": (now - timedelta(days=7)).isoformat(),
                    "attributions": [
                        {"verbatim_phrase": "must be scrubbed immediately", "start_char": 64, "end_char": 92, "attribution_weight": 0.88, "rubric_dimension": "delivery_alignment", "rationale": "High urgency compliance directive."}
                    ]
                }
            },
            {
                "block_id": "blk_alpha_202",
                "sequence_index": 2,
                "speaker_alias": "Marcus Vance",
                "display_speaker_label": "Marcus Vance (Lead Adjudicator)",
                "group_id": "INTERNAL",
                "group_name": "INTERNAL",
                "company_name": "Enterprise Global Corp",
                "text_scrubbed": "We updated the Google Cloud DLP de-identification transforms so all sensitive account data is irreversibly hashed before reaching Cloud Firestore.",
                "word_count": 20,
                "dlp_redaction_flags": [],
                "sentiment_score": 82.0,
                "ai_initial_score": 75.0,
                "ai_confidence": 0.93,
                "rubric_scores": {"emotional_valence": 20.0, "delivery_alignment": 22.0, "relationship_trust": 21.0, "momentum_commitment": 19.0},
                "embedding_seed": 2.2,
                "is_split": False,
                "is_pinned": False,
                "is_human_overridden": True,
                "xai_attribution": {
                    "computed_at": (now - timedelta(days=7)).isoformat(),
                    "attributions": [
                        {"verbatim_phrase": "irreversibly hashed before reaching Cloud Firestore", "start_char": 87, "end_char": 139, "attribution_weight": 0.82, "rubric_dimension": "relationship_trust", "rationale": "Proactive security remediation restoring client confidence."}
                    ]
                }
            },
            {
                "block_id": "blk_alpha_203",
                "sequence_index": 3,
                "speaker_alias": "David Wright",
                "display_speaker_label": "David Wright (Client Stakeholder)",
                "group_id": "BUYER",
                "group_name": "BUYER",
                "company_name": "Client Corp",
                "text_scrubbed": "We appreciate the rapid containment, though our audit committee will review the final incident log and verified cryptographic hash.",
                "word_count": 19,
                "dlp_redaction_flags": [],
                "sentiment_score": 71.0,
                "ai_initial_score": 71.0,
                "ai_confidence": 0.88,
                "rubric_scores": {"emotional_valence": 16.5, "delivery_alignment": 18.0, "relationship_trust": 18.5, "momentum_commitment": 18.0},
                "embedding_seed": 2.3,
                "is_split": False,
                "is_pinned": False,
                "is_human_overridden": False,
                "xai_attribution": None
            }
        ]
    },
    {
        "meeting_id": "mtg_alpha_sprint",
        "project_id": "proj-alpha",
        "title": "Executive Steering & Vendor Delivery Sprint",
        "platform": "ms_teams",
        "meeting_date": (now - timedelta(days=2)).isoformat(),
        "status": "PENDING_ADJUDICATION",
        "pulse_score": 67.5,
        "group_scores": {
            "BUYER": {"pulse_score": 54.0, "block_count": 2, "top_liked_words": [], "top_disliked_words": ["delay", "slippage", "risk"]},
            "INTERNAL": {"pulse_score": 76.0, "block_count": 1, "top_liked_words": ["mitigation"], "top_disliked_words": ["slip"]},
            "VENDOR": {"pulse_score": 72.5, "block_count": 2, "top_liked_words": ["staffing", "engineers"], "top_disliked_words": []},
        },
        "mom_summary": {
            "date_time": (now - timedelta(days=2)).isoformat(),
            "location": "Microsoft Teams",
            "title": "Executive Steering & Vendor Delivery Sprint",
            "agenda": ["Milestone 2 Timeline Variance", "Buyer Risk Escalation", "Compensatory Staffing"],
            "topics_of_discussion": ["Two-week delivery slip due to backend API integration", "Vendor dedicating senior resources"],
            "summary": "Buyer voiced strong dissatisfaction regarding Milestone 2 schedule slippage. Vendor agreed to inject 3 additional senior engineers at no added cost.",
            "action_items": [
                {"action_id": "act-021", "description": "Revise sprint burndown chart with new engineer capacity", "owner_group": "VENDOR", "due_date": (now + timedelta(days=3)).isoformat()},
                {"action_id": "act-022", "description": "Deliver daily build verification report to Buyer PMO", "owner_group": "INTERNAL", "due_date": (now + timedelta(days=1)).isoformat()}
            ],
            "recommended_mitigations": ["Hold daily standup checkpoints until delivery cadence normalizes."],
        },
        "participants": ["uid_superadmin", "uid_executive_sarah", "uid_stakeholder_david", "uid_adjudicator_marcus"],
        "created_at": (now - timedelta(days=2)).isoformat(),
        "dialogue_blocks": [
            {
                "block_id": "blk_alpha_301",
                "sequence_index": 1,
                "speaker_alias": "Sarah Chen",
                "display_speaker_label": "Sarah Chen (VP Strategy)",
                "group_id": "INTERNAL",
                "group_name": "INTERNAL",
                "company_name": "Enterprise Global Corp",
                "text_scrubbed": "Phase 2 frontend delivery will slip by two weeks due to upstream API contract delays from the legacy core system.",
                "word_count": 20,
                "dlp_redaction_flags": [],
                "sentiment_score": 52.0,
                "ai_initial_score": 52.0,
                "ai_confidence": 0.91,
                "rubric_scores": {"emotional_valence": 11.0, "delivery_alignment": 12.0, "relationship_trust": 15.0, "momentum_commitment": 14.0},
                "embedding_seed": 3.1,
                "is_split": False,
                "is_pinned": True,
                "is_human_overridden": False,
                "xai_attribution": {
                    "computed_at": (now - timedelta(days=2)).isoformat(),
                    "attributions": [
                        {"verbatim_phrase": "delivery will slip by two weeks", "start_char": 17, "end_char": 47, "attribution_weight": 0.89, "rubric_dimension": "delivery_alignment", "rationale": "Clear delivery schedule delay indicator."}
                    ]
                }
            },
            {
                "block_id": "blk_alpha_302",
                "sequence_index": 2,
                "speaker_alias": "David Wright",
                "display_speaker_label": "David Wright (Client Stakeholder)",
                "group_id": "BUYER",
                "group_name": "BUYER",
                "company_name": "Client Corp",
                "text_scrubbed": "This delay puts our fourth-quarter board launch at serious risk. We need compensatory staffing to protect the critical path.",
                "word_count": 19,
                "dlp_redaction_flags": [],
                "sentiment_score": 42.0,
                "ai_initial_score": 42.0,
                "ai_confidence": 0.96,
                "rubric_scores": {"emotional_valence": 8.0, "delivery_alignment": 10.0, "relationship_trust": 11.0, "momentum_commitment": 13.0},
                "embedding_seed": 3.2,
                "is_split": False,
                "is_pinned": False,
                "is_human_overridden": False,
                "xai_attribution": {
                    "computed_at": (now - timedelta(days=2)).isoformat(),
                    "attributions": [
                        {"verbatim_phrase": "at serious risk", "start_char": 48, "end_char": 64, "attribution_weight": 0.95, "rubric_dimension": "emotional_valence", "rationale": "Severe frustration regarding commercial launch jeopardy."}
                    ]
                }
            },
            {
                "block_id": "blk_alpha_303",
                "sequence_index": 3,
                "speaker_alias": "Vendor PM",
                "display_speaker_label": "Vendor Engagement Manager",
                "group_id": "VENDOR",
                "group_name": "VENDOR",
                "company_name": "Partner Cloud Solutions",
                "text_scrubbed": "We will allocate three additional senior staff engineers starting Monday without any billing adjustments to recover lost days.",
                "word_count": 19,
                "dlp_redaction_flags": [],
                "sentiment_score": 78.0,
                "ai_initial_score": 78.0,
                "ai_confidence": 0.93,
                "rubric_scores": {"emotional_valence": 18.0, "delivery_alignment": 20.0, "relationship_trust": 20.0, "momentum_commitment": 20.0},
                "embedding_seed": 3.3,
                "is_split": True,
                "is_pinned": False,
                "is_human_overridden": False,
                "xai_attribution": {
                    "computed_at": (now - timedelta(days=2)).isoformat(),
                    "attributions": [
                        {"verbatim_phrase": "without any billing adjustments", "start_char": 73, "end_char": 104, "attribution_weight": 0.84, "rubric_dimension": "relationship_trust", "rationale": "Commercial accommodation restoring collaborative alignment."}
                    ]
                }
            }
        ]
    },
    {
        "meeting_id": "mtg_alpha_upcoming",
        "project_id": "proj-alpha",
        "title": "Quarterly Enterprise Milestone Sign-off",
        "platform": "google_meet",
        "meeting_date": (now + timedelta(days=1)).isoformat(),
        "status": "SCHEDULED",
        "pulse_score": None,
        "group_scores": {},
        "mom_summary": None,
        "participants": ["uid_superadmin", "uid_executive_sarah"],
        "created_at": now_iso,
        "dialogue_blocks": []
    },

    # Project Beta Meetings
    {
        "meeting_id": "mtg_beta_kickoff",
        "project_id": "proj-beta",
        "title": "Fintech Cloud Migration Kickoff",
        "platform": "zoom",
        "meeting_date": (now - timedelta(days=10)).isoformat(),
        "status": "COMMITTED",
        "pulse_score": 92.5,
        "group_scores": {
            "EXECUTIVE": {"pulse_score": 95.0, "block_count": 1, "top_liked_words": ["approved", "charter"], "top_disliked_words": []},
            "ENGINEERING": {"pulse_score": 91.0, "block_count": 1, "top_liked_words": ["failover", "multi-region"], "top_disliked_words": []},
            "REGULATOR": {"pulse_score": 91.5, "block_count": 1, "top_liked_words": ["compliance", "audit"], "top_disliked_words": []},
        },
        "mom_summary": {
            "date_time": (now - timedelta(days=10)).isoformat(),
            "location": "Zoom Executive Boardroom",
            "title": "Fintech Cloud Migration Kickoff",
            "agenda": ["Board Charter Ratification", "Multi-Cloud Topology", "Escrow Regulatory Framework"],
            "topics_of_discussion": ["Multi-region failover under 60 seconds", "SOX compliance audit gates"],
            "summary": "Board approved cloud migration charter. Engineering demonstrated sub-minute cross-region failover.",
            "action_items": [
                {"action_id": "act-b01", "description": "Deliver final network topology diagram to regulator", "owner_group": "ENGINEERING", "due_date": (now - timedelta(days=3)).isoformat()}
            ],
            "recommended_mitigations": ["Execute monthly tabletop disaster recovery drills."],
        },
        "participants": ["uid_superadmin", "uid_executive_sarah"],
        "created_at": (now - timedelta(days=10)).isoformat(),
        "dialogue_blocks": [
            {
                "block_id": "blk_beta_101",
                "sequence_index": 1,
                "speaker_alias": "Bank CTO",
                "display_speaker_label": "Bank CTO (Executive Sponsor)",
                "group_id": "EXECUTIVE",
                "group_name": "EXECUTIVE",
                "company_name": "Fintech Horizon Bank",
                "text_scrubbed": "The migration charter is formally approved by the board with zero objections and full budgetary commitment.",
                "word_count": 16,
                "dlp_redaction_flags": [],
                "sentiment_score": 96.0,
                "ai_initial_score": 96.0,
                "ai_confidence": 0.98,
                "rubric_scores": {"emotional_valence": 24.5, "delivery_alignment": 24.0, "relationship_trust": 24.0, "momentum_commitment": 23.5},
                "embedding_seed": 4.1,
                "is_split": False,
                "is_pinned": False,
                "is_human_overridden": False,
                "xai_attribution": {
                    "computed_at": (now - timedelta(days=10)).isoformat(),
                    "attributions": [
                        {"verbatim_phrase": "formally approved by the board", "start_char": 25, "end_char": 55, "attribution_weight": 0.95, "rubric_dimension": "momentum_commitment", "rationale": "Decisive executive sign-off and funding validation."}
                    ]
                }
            },
            {
                "block_id": "blk_beta_102",
                "sequence_index": 2,
                "speaker_alias": "Cloud Architect",
                "display_speaker_label": "Lead Infrastructure Architect",
                "group_id": "ENGINEERING",
                "group_name": "ENGINEERING",
                "company_name": "Fintech Horizon Bank",
                "text_scrubbed": "Multi-region active-active failover tests across primary and secondary data centers completed in 42 seconds.",
                "word_count": 15,
                "dlp_redaction_flags": [],
                "sentiment_score": 91.0,
                "ai_initial_score": 91.0,
                "ai_confidence": 0.94,
                "rubric_scores": {"emotional_valence": 22.0, "delivery_alignment": 23.5, "relationship_trust": 23.0, "momentum_commitment": 22.5},
                "embedding_seed": 4.2,
                "is_split": False,
                "is_pinned": False,
                "is_human_overridden": False,
                "xai_attribution": None
            }
        ]
    },
    {
        "meeting_id": "mtg_beta_escrow",
        "project_id": "proj-beta",
        "title": "Core Banking Data Escrow & SOX Compliance",
        "platform": "ms_teams",
        "meeting_date": (now - timedelta(days=3)).isoformat(),
        "status": "COMMITTED",
        "pulse_score": 81.0,
        "group_scores": {
            "REGULATOR": {"pulse_score": 78.0, "block_count": 1, "top_liked_words": ["verification"], "top_disliked_words": ["escrow"]},
            "ENGINEERING": {"pulse_score": 84.0, "block_count": 1, "top_liked_words": ["sha256", "worm"], "top_disliked_words": []},
        },
        "mom_summary": {
            "date_time": (now - timedelta(days=3)).isoformat(),
            "location": "Microsoft Teams Regulatory Room",
            "title": "Core Banking Data Escrow & SOX Compliance",
            "agenda": ["Cryptographic Escrow Deposit", "WORM Storage Verification"],
            "topics_of_discussion": ["SOX 404 audit validation", "Secondary notary sign-off"],
            "summary": "Regulatory reviewer confirmed SHA-256 seal meets escrow requirements pending secondary notary signature.",
            "action_items": [
                {"action_id": "act-b10", "description": "Export WORM sealed compliance package for escrow deposit", "owner_group": "ENGINEERING", "due_date": (now + timedelta(days=2)).isoformat()}
            ],
            "recommended_mitigations": ["Automate daily checksum validation across cloud buckets."],
        },
        "participants": ["uid_superadmin", "uid_executive_sarah"],
        "created_at": (now - timedelta(days=3)).isoformat(),
        "dialogue_blocks": [
            {
                "block_id": "blk_beta_201",
                "sequence_index": 1,
                "speaker_alias": "Regulatory Liaison",
                "display_speaker_label": "Regulatory Compliance Officer",
                "group_id": "REGULATOR",
                "group_name": "REGULATOR",
                "company_name": "Fintech Regulatory Authority",
                "text_scrubbed": "Escrow deposit verification requires secondary cryptographic notary sign-off before production cutover permission.",
                "word_count": 14,
                "dlp_redaction_flags": [],
                "sentiment_score": 78.0,
                "ai_initial_score": 78.0,
                "ai_confidence": 0.90,
                "rubric_scores": {"emotional_valence": 18.0, "delivery_alignment": 20.0, "relationship_trust": 20.0, "momentum_commitment": 20.0},
                "embedding_seed": 5.1,
                "is_split": False,
                "is_pinned": False,
                "is_human_overridden": False,
                "xai_attribution": None
            },
            {
                "block_id": "blk_beta_202",
                "sequence_index": 2,
                "speaker_alias": "Security Architect",
                "display_speaker_label": "Fintech Security Architect",
                "group_id": "ENGINEERING",
                "group_name": "ENGINEERING",
                "company_name": "Fintech Horizon Bank",
                "text_scrubbed": "The SHA-256 sealed WORM package is generated and ready for cryptographic notary signing.",
                "word_count": 14,
                "dlp_redaction_flags": [],
                "sentiment_score": 84.0,
                "ai_initial_score": 84.0,
                "ai_confidence": 0.95,
                "rubric_scores": {"emotional_valence": 20.0, "delivery_alignment": 22.0, "relationship_trust": 21.0, "momentum_commitment": 21.0},
                "embedding_seed": 5.2,
                "is_split": False,
                "is_pinned": False,
                "is_human_overridden": False,
                "xai_attribution": None
            }
        ]
    },
    {
        "meeting_id": "mtg_beta_dr_drill",
        "project_id": "proj-beta",
        "title": "Disaster Recovery Cutover Simulation",
        "platform": "google_meet",
        "meeting_date": now_iso,
        "status": "LIVE",
        "pulse_score": 77.5,
        "group_scores": {
            "ENGINEERING": {"pulse_score": 78.0, "block_count": 1, "top_liked_words": ["promotion"], "top_disliked_words": []},
            "VENDOR": {"pulse_score": 77.0, "block_count": 1, "top_liked_words": ["standby"], "top_disliked_words": []},
        },
        "mom_summary": None,
        "participants": ["uid_superadmin", "uid_executive_sarah"],
        "created_at": now_iso,
        "dialogue_blocks": [
            {
                "block_id": "blk_beta_301",
                "sequence_index": 1,
                "speaker_alias": "DR Lead",
                "display_speaker_label": "Disaster Recovery Lead",
                "group_id": "ENGINEERING",
                "group_name": "ENGINEERING",
                "company_name": "Fintech Horizon Bank",
                "text_scrubbed": "Standby database promotion initiated; synchronizing replica binlog offset before switching DNS endpoints.",
                "word_count": 14,
                "dlp_redaction_flags": [],
                "sentiment_score": 78.0,
                "ai_initial_score": 78.0,
                "ai_confidence": 0.92,
                "rubric_scores": {"emotional_valence": 19.0, "delivery_alignment": 20.0, "relationship_trust": 19.5, "momentum_commitment": 19.5},
                "embedding_seed": 6.1,
                "is_split": False,
                "is_pinned": False,
                "is_human_overridden": False,
                "xai_attribution": None
            }
        ]
    },
]

print("\n--- Provisioning Meetings & Dialogue Blocks ---")
for mtg in meetings_data:
    m_id = mtg["meeting_id"]
    m_doc = {
        "meeting_id": m_id,
        "project_id": mtg["project_id"],
        "title": mtg["title"],
        "platform": mtg["platform"],
        "meeting_date": mtg["meeting_date"],
        "status": mtg["status"],
        "pulse_score": mtg["pulse_score"],
        "group_scores": mtg["group_scores"],
        "mom_summary": mtg["mom_summary"],
        "participants": mtg["participants"],
        "created_at": mtg["created_at"],
        "updated_at": now_iso,
    }
    db.collection("meetings").document(m_id).set(m_doc, merge=True)
    print(f"  ✓ Meeting: {m_id} [{mtg['status']}] - {mtg['title']} ({mtg['project_id']})")

    # Seed subcollection dialogue_blocks
    blocks_coll = db.collection("meetings").document(m_id).collection("dialogue_blocks")
    for blk in mtg["dialogue_blocks"]:
        b_id = blk["block_id"]
        blk_doc = {
            "block_id": b_id,
            "sequence_index": blk["sequence_index"],
            "speaker_alias": blk["speaker_alias"],
            "display_speaker_label": blk["display_speaker_label"],
            "group_id": blk["group_id"],
            "group_name": blk["group_name"],
            "company_name": blk["company_name"],
            "text_scrubbed": blk["text_scrubbed"],
            "word_count": blk["word_count"],
            "dlp_redaction_flags": blk["dlp_redaction_flags"],
            "sentiment_score": blk["sentiment_score"],
            "ai_initial_score": blk["ai_initial_score"],
            "ai_confidence": blk["ai_confidence"],
            "rubric_scores": blk["rubric_scores"],
            "embedding": make_embedding(blk["embedding_seed"]),
            "is_split": blk["is_split"],
            "is_pinned": blk["is_pinned"],
            "is_human_overridden": blk["is_human_overridden"],
            "xai_attribution": blk["xai_attribution"],
        }
        blocks_coll.document(b_id).set(blk_doc, merge=True)
        print(f"    - Block: {b_id} ({blk['group_name']}: {blk['speaker_alias']})")

# Also normalize demo meetings so they don't break
for demo_id, demo_title in [
    ("meet-interactive-demo", "Interactive Voice Ingestion Demonstration"),
    ("meet-live-demo-1", "MeetStream Webhook Live Ingestion"),
]:
    db.collection("meetings").document(demo_id).set({
        "meeting_id": demo_id,
        "project_id": "proj-alpha",
        "title": demo_title,
        "platform": "google_meet",
        "meeting_date": (now - timedelta(hours=6)).isoformat(),
        "status": "PROCESSING_POST_MEETING",
        "pulse_score": 82.0,
        "group_scores": {
            "INTERNAL": {"pulse_score": 82.0, "block_count": 2, "top_liked_words": ["demo"], "top_disliked_words": []}
        },
        "created_at": (now - timedelta(hours=6)).isoformat(),
        "updated_at": now_iso,
    }, merge=True)

# ==============================================================================
# 5. SENTIMENT CALIBRATIONS & CORRECTED CONTEXTS (Few-Shot Exemplars)
# ==============================================================================
calibrations_data = [
    {
        "calibration_id": "cal_alpha_buyer_pos",
        "project_id": "proj-alpha",
        "group_name": "BUYER",
        "dialogue_text": "We are fully satisfied with the milestone deliverables and security controls.",
        "benchmark_score": 95.0,
        "rubric_breakdown": {"emotional_valence": 24.0, "delivery_alignment": 24.0, "relationship_trust": 24.0, "momentum_commitment": 23.0},
        "embedding_seed": 7.1,
        "adjudicator_uid": "uid_superadmin",
    },
    {
        "calibration_id": "cal_alpha_buyer_neg",
        "project_id": "proj-alpha",
        "group_name": "BUYER",
        "dialogue_text": "The recurring SLA breaches and missing audit trails are unacceptable for our procurement board.",
        "benchmark_score": 38.0,
        "rubric_breakdown": {"emotional_valence": 8.0, "delivery_alignment": 10.0, "relationship_trust": 10.0, "momentum_commitment": 10.0},
        "embedding_seed": 7.2,
        "adjudicator_uid": "uid_adjudicator_marcus",
    },
    {
        "calibration_id": "cal_alpha_internal_pos",
        "project_id": "proj-alpha",
        "group_name": "INTERNAL",
        "dialogue_text": "All cloud schemas and WORM retention compliance are active across clusters.",
        "benchmark_score": 90.0,
        "rubric_breakdown": {"emotional_valence": 22.0, "delivery_alignment": 23.0, "relationship_trust": 22.5, "momentum_commitment": 22.5},
        "embedding_seed": 7.3,
        "adjudicator_uid": "uid_superadmin",
    },
    {
        "calibration_id": "cal_alpha_vendor_mid",
        "project_id": "proj-alpha",
        "group_name": "VENDOR",
        "dialogue_text": "We are evaluating the architectural tradeoffs between Firestore vector search and Vertex AI Search.",
        "benchmark_score": 65.0,
        "rubric_breakdown": {"emotional_valence": 15.0, "delivery_alignment": 16.0, "relationship_trust": 17.0, "momentum_commitment": 17.0},
        "embedding_seed": 7.4,
        "adjudicator_uid": "uid_adjudicator_marcus",
    },
    {
        "calibration_id": "cal_beta_exec_pos",
        "project_id": "proj-beta",
        "group_name": "EXECUTIVE",
        "dialogue_text": "The executive committee is unanimous in funding the cloud expansion program across all divisions.",
        "benchmark_score": 96.0,
        "rubric_breakdown": {"emotional_valence": 24.5, "delivery_alignment": 24.0, "relationship_trust": 24.0, "momentum_commitment": 23.5},
        "embedding_seed": 7.5,
        "adjudicator_uid": "uid_superadmin",
    },
    {
        "calibration_id": "cal_beta_reg_caution",
        "project_id": "proj-beta",
        "group_name": "REGULATOR",
        "dialogue_text": "Data residency guarantees must be backed by legally binding third-party escrow covenants.",
        "benchmark_score": 55.0,
        "rubric_breakdown": {"emotional_valence": 12.0, "delivery_alignment": 14.0, "relationship_trust": 15.0, "momentum_commitment": 14.0},
        "embedding_seed": 7.6,
        "adjudicator_uid": "uid_superadmin",
    },
]

print("\n--- Provisioning Sentiment Calibrations ---")
for c in calibrations_data:
    cal_doc = {
        "calibration_id": c["calibration_id"],
        "project_id": c["project_id"],
        "group_name": c["group_name"],
        "dialogue_text": c["dialogue_text"],
        "benchmark_score": c["benchmark_score"],
        "rubric_breakdown": c["rubric_breakdown"],
        "embedding": make_embedding(c["embedding_seed"]),
        "adjudicator_uid": c["adjudicator_uid"],
        "created_at": (now - timedelta(days=12)).isoformat(),
    }
    db.collection("sentiment_calibrations").document(c["calibration_id"]).set(cal_doc, merge=True)
    print(f"  ✓ Calibration: {c['calibration_id']} ({c['group_name']} score={c['benchmark_score']})")

# Corrected contexts (Adjudicator overrides)
corrected_data = [
    {
        "correction_id": "cor_alpha_01",
        "project_id": "proj-alpha",
        "group_name": "BUYER",
        "scrubbed_text": "The vendor says everything is on schedule, but we have not seen a working staging environment yet.",
        "ai_initial_score": 62.0,
        "human_adjusted_score": 45.0,
        "rubric_breakdown": {"emotional_valence": 10.0, "delivery_alignment": 11.0, "relationship_trust": 12.0, "momentum_commitment": 12.0},
        "embedding_seed": 8.1,
        "adjudicator_uid": "uid_adjudicator_marcus",
    },
    {
        "correction_id": "cor_beta_01",
        "project_id": "proj-beta",
        "group_name": "REGULATOR",
        "scrubbed_text": "Regulator confirmed the automated cryptographic hash verification satisfies audit rule 17a-4.",
        "ai_initial_score": 70.0,
        "human_adjusted_score": 86.0,
        "rubric_breakdown": {"emotional_valence": 21.0, "delivery_alignment": 22.0, "relationship_trust": 22.0, "momentum_commitment": 21.0},
        "embedding_seed": 8.2,
        "adjudicator_uid": "uid_superadmin",
    },
]

print("\n--- Provisioning Corrected Contexts ---")
for ctx in corrected_data:
    ctx_doc = {
        "correction_id": ctx["correction_id"],
        "project_id": ctx["project_id"],
        "group_name": ctx["group_name"],
        "scrubbed_text": ctx["scrubbed_text"],
        "ai_initial_score": ctx["ai_initial_score"],
        "human_adjusted_score": ctx["human_adjusted_score"],
        "rubric_breakdown": ctx["rubric_breakdown"],
        "embedding": make_embedding(ctx["embedding_seed"]),
        "adjudicator_uid": ctx["adjudicator_uid"],
        "created_at": (now - timedelta(days=5)).isoformat(),
    }
    db.collection("corrected_contexts").document(ctx["correction_id"]).set(ctx_doc, merge=True)
    print(f"  ✓ Corrected Context: {ctx['correction_id']} (initial {ctx['ai_initial_score']} -> adjusted {ctx['human_adjusted_score']})")

# ==============================================================================
# 6. RISK REGISTER (5x5 Heatmap & SLA Escalation)
# ==============================================================================
risks_data = [
    # Project Alpha Risks
    {
        "risk_id": "RSK-ALPHA-001",
        "project_id": "proj-alpha",
        "meeting_id": "mtg_alpha_baseline",
        "company_name": "Enterprise Global Corp",
        "associated_groups": ["BUYER", "INTERNAL"],
        "title": "Third-Party Webhook Ingestion Latency",
        "description": "Ensure MeetStream webhook ingestion completes within 200ms budget to prevent queue starvation.",
        "category": "OPERATIONAL",
        "status": "OPEN",
        "impact": 3,
        "probability": 2,
        "severity_score": 6,
        "severity_band": "MEDIUM",
        "owner_uid": "uid_superadmin",
        "sla_escalation_tier": "48h",
        "mitigation_plan": {"strategy": "Active memory caching and async background task worker pooling."},
        "qualitative_commentary": [
            {
                "comment_id": "com-001",
                "author_uid": "uid_superadmin",
                "author_role": "ADMIN",
                "comment": "Webhook latency verified at 170ms p95, continuing to monitor during morning peaks.",
                "created_at": (now - timedelta(days=10)).isoformat(),
            }
        ],
        "created_at": (now - timedelta(days=14)).isoformat(),
        "updated_at": (now - timedelta(days=10)).isoformat(),
    },
    {
        "risk_id": "RSK-ALPHA-002",
        "project_id": "proj-alpha",
        "meeting_id": "mtg_alpha_security",
        "company_name": "Enterprise Global Corp",
        "associated_groups": ["BUYER", "LEGAL"],
        "title": "Cross-Border Data Residency Compliance Gap",
        "description": "Customer EU privacy terms require all meeting recordings and transcripts to reside exclusively in europe-west3.",
        "category": "COMPLIANCE",
        "status": "ESCALATED",
        "impact": 5,
        "probability": 3,
        "severity_score": 15,
        "severity_band": "HIGH",
        "owner_uid": "uid_executive_sarah",
        "sla_escalation_tier": "24h",
        "mitigation_plan": {"strategy": "Provision dual-region Cloud Storage buckets with Frankfurt residency replication."},
        "qualitative_commentary": [
            {
                "comment_id": "com-002",
                "author_uid": "uid_executive_sarah",
                "author_role": "EXECUTIVE",
                "comment": "Escalated to General Counsel and VP Infrastructure. 24h SLA response countdown initiated.",
                "created_at": (now - timedelta(days=1)).isoformat(),
            }
        ],
        "created_at": (now - timedelta(days=7)).isoformat(),
        "updated_at": (now - timedelta(days=1)).isoformat(),
    },
    {
        "risk_id": "RSK-ALPHA-003",
        "project_id": "proj-alpha",
        "meeting_id": "mtg_alpha_sprint",
        "company_name": "Enterprise Global Corp",
        "associated_groups": ["BUYER", "VENDOR"],
        "title": "Vendor Milestone Slippage on Phase 2 Delivery",
        "description": "Two-week schedule delay on frontend components could jeopardize fourth-quarter board rollout.",
        "category": "RELATIONSHIP",
        "status": "OPEN",
        "impact": 4,
        "probability": 4,
        "severity_score": 16,
        "severity_band": "HIGH",
        "owner_uid": "uid_adjudicator_marcus",
        "sla_escalation_tier": "24h",
        "mitigation_plan": {"strategy": "Vendor injected 3 senior staff engineers; bi-weekly progress burndown scheduled."},
        "qualitative_commentary": [
            {
                "comment_id": "com-003",
                "author_uid": "uid_adjudicator_marcus",
                "author_role": "ADJUDICATOR",
                "comment": "Buyer accepted revised recovery roadmap subject to daily progress demonstrations.",
                "created_at": (now - timedelta(days=1)).isoformat(),
            }
        ],
        "created_at": (now - timedelta(days=2)).isoformat(),
        "updated_at": (now - timedelta(days=1)).isoformat(),
    },
    {
        "risk_id": "RSK-ALPHA-004",
        "project_id": "proj-alpha",
        "meeting_id": "mtg_alpha_baseline",
        "company_name": "Enterprise Global Corp",
        "associated_groups": ["INTERNAL"],
        "title": "Escalating Cloud Compute Infrastructure Overrun",
        "description": "Unexpected GPU model inference usage exceeding quarterly cloud financial budget allocation by 18%.",
        "category": "FINANCIAL",
        "status": "MITIGATED",
        "impact": 4,
        "probability": 2,
        "severity_score": 8,
        "severity_band": "MEDIUM",
        "owner_uid": "uid_superadmin",
        "sla_escalation_tier": "48h",
        "mitigation_plan": {"strategy": "Committed-use discounts purchased and speculative batch caching enabled."},
        "qualitative_commentary": [
            {
                "comment_id": "com-004",
                "author_uid": "uid_superadmin",
                "author_role": "ADMIN",
                "comment": "Cost run-rate stabilized back within quarterly target.",
                "created_at": (now - timedelta(days=6)).isoformat(),
            }
        ],
        "created_at": (now - timedelta(days=14)).isoformat(),
        "updated_at": (now - timedelta(days=6)).isoformat(),
    },
    {
        "risk_id": "RSK-ALPHA-005",
        "project_id": "proj-alpha",
        "meeting_id": "mtg_alpha_security",
        "company_name": "Enterprise Global Corp",
        "associated_groups": ["INTERNAL", "SECURITY"],
        "title": "DLP Secret Redaction Rule Drift",
        "description": "New developer logging format bypassed standard credit card regex pattern in pre-production test suites.",
        "category": "OPERATIONAL",
        "status": "CLOSED",
        "impact": 3,
        "probability": 1,
        "severity_score": 3,
        "severity_band": "LOW",
        "owner_uid": "uid_superadmin",
        "sla_escalation_tier": "72h",
        "mitigation_plan": {"strategy": "Centralized Cloud DLP inspection template updated with unified surrogate hash rules."},
        "qualitative_commentary": [],
        "created_at": (now - timedelta(days=7)).isoformat(),
        "updated_at": (now - timedelta(days=4)).isoformat(),
    },
    {
        "risk_id": "RSK-ALPHA-006",
        "project_id": "proj-alpha",
        "meeting_id": "mtg_alpha_sprint",
        "company_name": "Enterprise Global Corp",
        "associated_groups": ["INTERNAL"],
        "title": "Potential Discontinuation of Legacy Data Feeds",
        "description": "Third-party market data provider announced deprecation of v1 SOAP endpoint in 60 days.",
        "category": "STRATEGIC",
        "status": "DRAFT_PENDING_ADJUDICATION",
        "impact": 4,
        "probability": 3,
        "severity_score": 12,
        "severity_band": "HIGH",
        "owner_uid": "uid_adjudicator_marcus",
        "sla_escalation_tier": "48h",
        "mitigation_plan": {"strategy": "Evaluating migration to GraphQL streaming feed."},
        "qualitative_commentary": [],
        "created_at": (now - timedelta(days=2)).isoformat(),
        "updated_at": (now - timedelta(days=2)).isoformat(),
    },

    # Project Beta Risks
    {
        "risk_id": "RSK-BETA-001",
        "project_id": "proj-beta",
        "meeting_id": "mtg_beta_kickoff",
        "company_name": "Fintech Horizon Bank",
        "associated_groups": ["ENGINEERING", "VENDOR"],
        "title": "Core Banking Cutover Rollback Window Exceeded",
        "description": "Database snapshot rollback during testing took 68 minutes, exceeding the regulatory 45-minute cutoff.",
        "category": "OPERATIONAL",
        "status": "OPEN",
        "impact": 5,
        "probability": 2,
        "severity_score": 10,
        "severity_band": "MEDIUM",
        "owner_uid": "uid_superadmin",
        "sla_escalation_tier": "48h",
        "mitigation_plan": {"strategy": "Parallelizing partition restoration with incremental write logs."},
        "qualitative_commentary": [],
        "created_at": (now - timedelta(days=10)).isoformat(),
        "updated_at": (now - timedelta(days=8)).isoformat(),
    },
    {
        "risk_id": "RSK-BETA-002",
        "project_id": "proj-beta",
        "meeting_id": "mtg_beta_escrow",
        "company_name": "Fintech Horizon Bank",
        "associated_groups": ["REGULATOR"],
        "title": "Regulatory Escrow Audit Evidence Incomplete",
        "description": "Missing cryptographic notary signatures on secondary source code escrow deposit container.",
        "category": "COMPLIANCE",
        "status": "ESCALATED",
        "impact": 5,
        "probability": 3,
        "severity_score": 15,
        "severity_band": "HIGH",
        "owner_uid": "uid_executive_sarah",
        "sla_escalation_tier": "24h",
        "mitigation_plan": {"strategy": "Coordinating emergency notary appointment with certified escrow agent."},
        "qualitative_commentary": [
            {
                "comment_id": "com-b02",
                "author_uid": "uid_executive_sarah",
                "author_role": "EXECUTIVE",
                "comment": "Escalated for immediate sign-off. Compliance package CMP-BETA-001 re-sealed.",
                "created_at": (now - timedelta(days=1)).isoformat(),
            }
        ],
        "created_at": (now - timedelta(days=3)).isoformat(),
        "updated_at": (now - timedelta(days=1)).isoformat(),
    },
    {
        "risk_id": "RSK-BETA-003",
        "project_id": "proj-beta",
        "meeting_id": "mtg_beta_escrow",
        "company_name": "Fintech Horizon Bank",
        "associated_groups": ["ENGINEERING"],
        "title": "Third-Party HSM Key Custody Latency",
        "description": "Cloud KMS HSM signing operation latency spikes observed during batch settlement window.",
        "category": "FINANCIAL",
        "status": "MITIGATED",
        "impact": 3,
        "probability": 2,
        "severity_score": 6,
        "severity_band": "MEDIUM",
        "owner_uid": "uid_superadmin",
        "sla_escalation_tier": "48h",
        "mitigation_plan": {"strategy": "Switched to local enveloped DEK caching with 1-hour expiration."},
        "qualitative_commentary": [],
        "created_at": (now - timedelta(days=3)).isoformat(),
        "updated_at": (now - timedelta(days=2)).isoformat(),
    },
    {
        "risk_id": "RSK-BETA-004",
        "project_id": "proj-beta",
        "meeting_id": "mtg_beta_dr_drill",
        "company_name": "Fintech Horizon Bank",
        "associated_groups": ["ENGINEERING"],
        "title": "Multi-Cloud Interconnect Bandwidth Saturation",
        "description": "Peak DR synchronization data stream utilized 87% of dedicated 10Gbps interconnect link.",
        "category": "STRATEGIC",
        "status": "OPEN",
        "impact": 4,
        "probability": 3,
        "severity_score": 12,
        "severity_band": "HIGH",
        "owner_uid": "uid_superadmin",
        "sla_escalation_tier": "48h",
        "mitigation_plan": {"strategy": "Ordering redundant 10Gbps cross-connect with burstable transit capacity."},
        "qualitative_commentary": [],
        "created_at": now_iso,
        "updated_at": now_iso,
    },
]

print("\n--- Provisioning Risk Register ---")
for r in risks_data:
    r_id = r["risk_id"]
    r_doc = {
        "risk_id": r_id,
        "project_id": r["project_id"],
        "meeting_id": r["meeting_id"],
        "company_name": r["company_name"],
        "associated_groups": r["associated_groups"],
        "title": r["title"],
        "description": r["description"],
        "category": r["category"],
        "status": r["status"],
        "impact": r["impact"],
        "probability": r["probability"],
        "severity_score": r["severity_score"],
        "severity_band": r["severity_band"],
        "owner_uid": r["owner_uid"],
        "sla_escalation_tier": r["sla_escalation_tier"],
        "mitigation_plan": r["mitigation_plan"],
        "qualitative_commentary": r["qualitative_commentary"],
        "escalation_config": {
            "enabled": True,
            "sla_started_at": r["created_at"] if r["status"] in ("OPEN", "ESCALATED") else None,
            "last_escalated_tier_hours": 24 if r["status"] == "ESCALATED" else 0,
            "manager_uids": ["uid_superadmin", "uid_executive_sarah"],
            "custom_recipients": [],
        },
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    }
    db.collection("risk_register").document(r_id).set(r_doc, merge=True)
    print(f"  ✓ Risk: {r_id} [{r['category']}] ({r['status']} score={r['severity_score']}) -> {r['project_id']}")

# ==============================================================================
# 7. COMPLIANCE PACKAGES (WORM Storage & Cryptographic Verification)
# ==============================================================================
compliance_packages_data = [
    # Project Alpha
    {
        "package_id": "CMP-ALPHA-001",
        "version_id": "v1.0.0",
        "project_id": "proj-alpha",
        "company_name": "Enterprise Global Corp",
        "framework": "ISO_31000",
        "target_frameworks": ["ISO_31000", "SOC_2"],
        "format": "PDF",
        "sha256_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "gcs_uri": f"gs://prisk-compliance-packages-{project_id}/proj-alpha/CMP-ALPHA-001.pdf",
        "size_bytes": 1048576,
        "status": "SEALED_WORM",
        "generated_by_uid": "uid_superadmin",
        "generated_at": (now - timedelta(days=13)).isoformat(),
        "created_at": (now - timedelta(days=13)).isoformat(),
        "zero_verbatim_quotes_verified": True,
        "sections": {
            "header_and_metadata": {"title": "ISO 31000 Enterprise Risk Assessment", "project": "Project Alpha Core Oversight"},
            "framework_control_mapping_table": {"controls_evaluated": 24, "controls_passing": 24},
            "sanitized_risk_register": {"risks_included": 4},
            "mitigation_lifecycle_audit_summary": {"mitigated_count": 1, "open_count": 3},
            "privacy_and_data_governance_attestation": {"dlp_scrubbed": True, "worm_sealed": True},
        },
    },
    {
        "package_id": "CMP-ALPHA-002",
        "version_id": "v1.1.0",
        "project_id": "proj-alpha",
        "company_name": "Enterprise Global Corp",
        "framework": "SOC_2",
        "target_frameworks": ["SOC_2", "ISO_31000"],
        "format": "CSV",
        "sha256_hash": "a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0",
        "gcs_uri": f"gs://prisk-compliance-packages-{project_id}/proj-alpha/CMP-ALPHA-002.csv",
        "size_bytes": 256000,
        "status": "COMPLETED",
        "generated_by_uid": "uid_adjudicator_marcus",
        "generated_at": (now - timedelta(days=6)).isoformat(),
        "created_at": (now - timedelta(days=6)).isoformat(),
        "zero_verbatim_quotes_verified": True,
        "sections": {
            "header_and_metadata": {"title": "SOC 2 Type II Confidentiality Audit Export"},
            "framework_control_mapping_table": {"trust_service_criteria": "CC6.1, CC6.6, CC7.2"},
        },
    },
    {
        "package_id": "CMP-ALPHA-003",
        "version_id": "v1.0.0",
        "project_id": "proj-alpha",
        "company_name": "Enterprise Global Corp",
        "framework": "GDPR",
        "target_frameworks": ["GDPR", "ISO_31000"],
        "format": "JSON",
        "sha256_hash": "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210",
        "gcs_uri": f"gs://prisk-compliance-packages-{project_id}/proj-alpha/CMP-ALPHA-003.json",
        "size_bytes": 512000,
        "status": "PENDING",
        "generated_by_uid": "uid_superadmin",
        "generated_at": (now - timedelta(hours=12)).isoformat(),
        "created_at": (now - timedelta(hours=12)).isoformat(),
        "zero_verbatim_quotes_verified": True,
        "sections": None,
    },

    # Project Beta
    {
        "package_id": "CMP-BETA-001",
        "version_id": "v1.0.0",
        "project_id": "proj-beta",
        "company_name": "Fintech Horizon Bank",
        "framework": "SOC_2",
        "target_frameworks": ["SOC_2", "ISO_31000", "COSO"],
        "format": "PDF",
        "sha256_hash": "112233445566778899aabbccddeeff00112233445566778899aabbccddeeff00",
        "gcs_uri": f"gs://prisk-compliance-packages-{project_id}/proj-beta/CMP-BETA-001.pdf",
        "size_bytes": 2097152,
        "status": "SEALED_WORM",
        "generated_by_uid": "uid_executive_sarah",
        "generated_at": (now - timedelta(days=2)).isoformat(),
        "created_at": (now - timedelta(days=2)).isoformat(),
        "zero_verbatim_quotes_verified": True,
        "sections": {
            "header_and_metadata": {"title": "Banking Cloud Escrow & Regulatory Certification", "project": "Fintech Cloud Migration & Escrow"},
            "framework_control_mapping_table": {"controls_evaluated": 36, "controls_passing": 36},
            "sanitized_risk_register": {"risks_included": 4},
            "privacy_and_data_governance_attestation": {"dlp_scrubbed": True, "worm_sealed": True, "fips_140_2_validated": True},
        },
    },
    {
        "package_id": "CMP-BETA-002",
        "version_id": "v1.0.0",
        "project_id": "proj-beta",
        "company_name": "Fintech Horizon Bank",
        "framework": "ISO_31000",
        "target_frameworks": ["ISO_31000"],
        "format": "PDF",
        "sha256_hash": "aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899",
        "gcs_uri": f"gs://prisk-compliance-packages-{project_id}/proj-beta/CMP-BETA-002.pdf",
        "size_bytes": 1572864,
        "status": "COMPLETED",
        "generated_by_uid": "uid_superadmin",
        "generated_at": (now - timedelta(days=8)).isoformat(),
        "created_at": (now - timedelta(days=8)).isoformat(),
        "zero_verbatim_quotes_verified": True,
        "sections": {
            "header_and_metadata": {"title": "ISO 31000 Cloud Risk Assessment Baseline"},
        },
    },
]

print("\n--- Provisioning Compliance Packages ---")
for pkg in compliance_packages_data:
    p_id = pkg["package_id"]
    db.collection("compliance_packages").document(p_id).set(pkg, merge=True)
    print(f"  ✓ Package: {p_id} [{pkg['status']}] ({pkg['framework']} {pkg['format']}) -> {pkg['project_id']}")

# ==============================================================================
# 8. AUDIT LEDGER (Tamper-evident system activity log)
# ==============================================================================
audit_events_data = [
    {
        "event_id": f"audit_init_{int((now - timedelta(days=30)).timestamp() * 1000)}",
        "event_type": "SYSTEM_INITIALIZED",
        "actor_uid": "uid_superadmin",
        "actor_role": "ADMIN",
        "action_type": "SYSTEM_INITIALIZED",
        "entity_type": "SYSTEM",
        "target_id": project_id,
        "metadata": {"system_version": "2.4.0", "cloud_provider": "google_cloud"},
        "timestamp": (now - timedelta(days=30)).isoformat(),
    },
    {
        "event_id": f"audit_proj_alpha_{int((now - timedelta(days=30)).timestamp() * 1000)}",
        "event_type": "PROJECT_CREATED",
        "actor_uid": "uid_superadmin",
        "actor_role": "ADMIN",
        "action_type": "SYSTEM_INITIALIZED",
        "entity_type": "PROJECT",
        "target_id": "proj-alpha",
        "metadata": {"name": "Project Alpha Core Oversight", "company": "Enterprise Global Corp"},
        "timestamp": (now - timedelta(days=30)).isoformat(),
    },
    {
        "event_id": f"audit_proj_beta_{int((now - timedelta(days=20)).timestamp() * 1000)}",
        "event_type": "PROJECT_CREATED",
        "actor_uid": "uid_superadmin",
        "actor_role": "ADMIN",
        "action_type": "SYSTEM_INITIALIZED",
        "entity_type": "PROJECT",
        "target_id": "proj-beta",
        "metadata": {"name": "Fintech Cloud Migration & Escrow", "company": "Fintech Horizon Bank"},
        "timestamp": (now - timedelta(days=20)).isoformat(),
    },
    {
        "event_id": f"audit_golden_record_{int((now - timedelta(days=7)).timestamp() * 1000)}",
        "event_type": "GOLDEN_RECORD_COMMIT",
        "actor_uid": "uid_adjudicator_marcus",
        "actor_role": "ADJUDICATOR",
        "action_type": "GOLDEN_RECORD_COMMIT",
        "entity_type": "MEETING",
        "target_id": "mtg_alpha_security",
        "metadata": {"reason": "Security review completed; all DLP redactions validated."},
        "timestamp": (now - timedelta(days=7)).isoformat(),
    },
    {
        "event_id": f"audit_override_{int((now - timedelta(days=7)).timestamp() * 1000)}",
        "event_type": "SLIDER_OVERRIDE",
        "actor_uid": "uid_adjudicator_marcus",
        "actor_role": "ADJUDICATOR",
        "action_type": "SLIDER_OVERRIDE",
        "entity_type": "DIALOGUE_BLOCK",
        "target_id": "blk_alpha_202",
        "metadata": {"previous_score": 75.0, "new_score": 82.0, "dimension": "delivery_alignment"},
        "timestamp": (now - timedelta(days=7)).isoformat(),
    },
    {
        "event_id": f"audit_split_{int((now - timedelta(days=2)).timestamp() * 1000)}",
        "event_type": "BUBBLE_SPLIT",
        "actor_uid": "uid_superadmin",
        "actor_role": "ADMIN",
        "action_type": "BUBBLE_SPLIT",
        "entity_type": "DIALOGUE_BLOCK",
        "target_id": "blk_alpha_303",
        "metadata": {"split_point_char": 45},
        "timestamp": (now - timedelta(days=2)).isoformat(),
    },
    {
        "event_id": f"audit_risk_escalated_{int((now - timedelta(days=1)).timestamp() * 1000)}",
        "event_type": "RISK_OVERRIDE",
        "actor_uid": "uid_executive_sarah",
        "actor_role": "EXECUTIVE",
        "action_type": "RISK_OVERRIDE",
        "entity_type": "RISK",
        "target_id": "RSK-ALPHA-002",
        "metadata": {"status_transition": "OPEN -> ESCALATED", "sla_tier": "24h"},
        "timestamp": (now - timedelta(days=1)).isoformat(),
    },
    {
        "event_id": f"audit_compliance_seal_{int((now - timedelta(days=2)).timestamp() * 1000)}",
        "event_type": "COMPLIANCE_PACKAGE_EXPORTED",
        "actor_uid": "uid_executive_sarah",
        "actor_role": "EXECUTIVE",
        "action_type": "COMPLIANCE_PACKAGE_EXPORTED",
        "entity_type": "COMPLIANCE_PACKAGE",
        "target_id": "CMP-BETA-001",
        "metadata": {"worm_hash": "112233445566778899aabbccddeeff00112233445566778899aabbccddeeff00"},
        "timestamp": (now - timedelta(days=2)).isoformat(),
    },
]

print("\n--- Provisioning Audit Ledger ---")
for evt in audit_events_data:
    e_id = evt["event_id"]
    db.collection("audit_ledger").document(e_id).set(evt, merge=True)
    print(f"  ✓ Audit Log: {e_id} [{evt['event_type']}] on {evt['target_id']}")

# ==============================================================================
# 9. EMAIL NOTIFICATIONS
# ==============================================================================
notifications_data = [
    {
        "notification_id": "notif_sla_escalation_alpha",
        "type": "SLA_ESCALATION",
        "from": f"no-reply@{project_id}.firebaseapp.com",
        "to": "sarah.chen@enterprise.com",
        "subject": "[CRITICAL SLA ALERT] Risk RSK-ALPHA-002 Escalated to 24h Tier",
        "body": "Cross-Border Data Residency Compliance Gap (RSK-ALPHA-002) has been escalated to Tier-1 24h SLA. Executive action required.",
        "sent_at": (now - timedelta(days=1)).isoformat(),
    },
    {
        "notification_id": "notif_weekly_digest_alpha",
        "type": "WEEKLY_DIGEST",
        "from": f"no-reply@{project_id}.firebaseapp.com",
        "to": "admin@enterprise.com",
        "subject": "Prisk AI Weekly Executive Pulse Report - Project Alpha",
        "body": "Overall Pulse score: 76.5 (-12.0 variance). 1 escalated risk, 2 open risks, 1 golden record committed.",
        "sent_at": (now - timedelta(days=2)).isoformat(),
    },
    {
        "notification_id": "notif_invitation_beta",
        "type": "PROJECT_INVITATION",
        "from": f"no-reply@{project_id}.firebaseapp.com",
        "to": "audit.lead@fintechreg.gov",
        "subject": "Invitation to Fintech Cloud Migration & Escrow Workspace",
        "body": "You have been invited by Super Administrator to review regulatory compliance packages on Prisk AI.",
        "sent_at": (now - timedelta(days=1)).isoformat(),
    },
    {
        "notification_id": "notif_worm_sealed_beta",
        "type": "COMPLIANCE_ALERT",
        "from": f"no-reply@{project_id}.firebaseapp.com",
        "to": "admin@enterprise.com",
        "subject": "WORM Artifact Sealed: CMP-BETA-001 (SOC 2 Type II / ISO 31000)",
        "body": "Package CMP-BETA-001 has been cryptographically sealed and written to WORM retention storage.",
        "sent_at": (now - timedelta(days=2)).isoformat(),
    },
]

print("\n--- Provisioning Email Notifications ---")
for notif in notifications_data:
    n_id = notif["notification_id"]
    db.collection("email_notifications").document(n_id).set(notif, merge=True)
    print(f"  ✓ Notification: {n_id} ({notif['type']} -> {notif['to']})")

# ==============================================================================
# VERIFICATION SUMMARY
# ==============================================================================
existing_collections = sorted([c.id for c in db.collections()])
print(f"\n" + "=" * 65)
print(f"🎉 SEED COMPLETE: Live Cloud Firestore Collections ({len(existing_collections)}):")
for idx, col in enumerate(existing_collections, 1):
    count = len(list(db.collection(col).stream()))
    print(f"  {idx:2d}. {col:25} ({count} documents)")
print("=" * 65)
