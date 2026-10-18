from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import math
import os
import re
import uuid
from typing import Any

from app.core.config import get_settings
from app.repositories.meeting_repository import MeetingRepository
from app.repositories.risk_repository import RiskRepository
from app.repositories.sentiment_repository import SentimentRepository
from app.schemas.meeting import (
    ActionItem,
    DialogueBlockResponse,
    GroupPulseMetric,
    MeetingStatus,
    MoMSummary,
)
from app.schemas.project import (
    DEFAULT_CANONICAL_GROUPS,
    ProjectAISuggestGroupsResponse,
    ProjectAlertThresholds,
)
from app.schemas.risk import RiskCategory, RiskRegisterCreate, RiskStatus
from app.schemas.sentiment import (
    ActionItemResult,
    AiPulseCommentary,
    BlockExplainResponse,
    BlockInferenceResult,
    DraftRiskResult,
    ExplainRationaleResponse,
    GroupKeywordsResult,
    PostMeetingAnalysisResponse,
    PulseTrendPoint,
    PulseTrendsAggregate,
    PulseTrendsResponse,
    RubricScoresSchema,
    SentimentCalibrationResponse,
    SpanAttribution,
    SpeakerBlindBlockInput,
    ValidatedSpanAttribution,
)
from app.schemas.user import AdminGovernanceDigestResponse

logger = logging.getLogger(__name__)

try:
    from google import genai  # type: ignore[import-not-found]
    from google.genai import types as genai_types  # type: ignore[import-not-found]
except ImportError:
    genai = None  # type: ignore[assignment]
    genai_types = None  # type: ignore[assignment]


_POSITIVE_CUES = {
    "approved",
    "great",
    "satisfied",
    "completed",
    "progress",
    "aligned",
    "success",
    "clear",
    "ready",
    "confirmed",
    "on-track",
    "resolved",
    "thanks",
    "excellent",
}

_NEGATIVE_CUES = {
    "delayed",
    "delay",
    "blocked",
    "blocker",
    "cannot",
    "issue",
    "risk",
    "concern",
    "dispute",
    "slip",
    "overrun",
    "liability",
    "unapproved",
    "failed",
    "freeze",
    "breach",
    "audit",
    "withheld",
}


def strip_speaker_identity(
    blocks: list[DialogueBlockResponse | dict[str, Any]]
) -> list[SpeakerBlindBlockInput]:
    """Strip speaker_alias, display_speaker_label, and ephemeral_speaker_account_id before LLM submission."""
    sanitized: list[SpeakerBlindBlockInput] = []
    for idx, b in enumerate(blocks):
        if isinstance(b, DialogueBlockResponse):
            block_id = b.block_id
            seq = b.sequence_index
            text = b.text_scrubbed
        else:
            block_id = str(b.get("block_id", f"blk-{idx + 1:04d}"))
            seq = int(b.get("sequence_index", idx))
            text = str(b.get("text_scrubbed") or b.get("scrubbed_text") or b.get("text", ""))
        sanitized.append(
            SpeakerBlindBlockInput(
                block_id=block_id,
                sequence_index=seq,
                scrubbed_text=text,
            )
        )
    return sanitized


def verify_and_locate_substrings(
    scrubbed_text: str, raw_attributions: list[SpanAttribution]
) -> list[ValidatedSpanAttribution]:
    """Verify each phrase exists in scrubbed_text and compute exact start_char and end_char indices."""
    validated: list[ValidatedSpanAttribution] = []
    if not scrubbed_text:
        return validated

    lower_text = scrubbed_text.lower()
    valid_dimensions = {
        "emotional_valence",
        "delivery_alignment",
        "relationship_trust",
        "momentum_commitment",
    }

    for attr in raw_attributions:
        phrase = attr.verbatim_phrase.strip()
        if not phrase:
            continue

        start_idx = scrubbed_text.find(phrase)
        matched_phrase = phrase

        if start_idx == -1:
            # Case-insensitive exact length match
            lower_idx = lower_text.find(phrase.lower())
            if lower_idx != -1:
                start_idx = lower_idx
                matched_phrase = scrubbed_text[lower_idx : lower_idx + len(phrase)]
            else:
                # Whitespace-normalized regex match against original text
                tokens = [re.escape(tok) for tok in phrase.split() if tok]
                if tokens:
                    pattern = r"\s+".join(tokens)
                    match = re.search(pattern, scrubbed_text, flags=re.IGNORECASE)
                    if match:
                        start_idx = match.start()
                        matched_phrase = scrubbed_text[match.start() : match.end()]

        if start_idx == -1:
            continue

        end_idx = start_idx + len(matched_phrase)
        # Double-check exact substring invariant
        if scrubbed_text[start_idx:end_idx] != matched_phrase:
            continue

        dim = (
            attr.rubric_dimension
            if attr.rubric_dimension in valid_dimensions
            else "delivery_alignment"
        )
        weight = max(-1.0, min(1.0, float(attr.attribution_weight)))

        validated.append(
            ValidatedSpanAttribution(
                verbatim_phrase=matched_phrase,
                start_char=start_idx,
                end_char=end_idx,
                attribution_weight=round(weight, 2),
                rubric_dimension=dim,
                rationale=attr.rationale,
            )
        )

    return validated


class SentimentService:
    """Service for Vertex AI Gemini speaker-blind rubric scoring, text-embedding-004 vectors, and on-demand XAI."""

    def __init__(
        self,
        db: Any | None = None,
        genai_client: Any | None = None,
    ) -> None:
        self.settings = get_settings()
        self.db = db
        self.sentiment_repo = SentimentRepository(db=db)
        self.meeting_repo = MeetingRepository(db=db)
        self.risk_repo = RiskRepository(db=db)
        self._client = genai_client

        if (
            self._client is None
            and not self.settings.use_in_memory_firestore
            and genai is not None
        ):
            self._client = self._init_genai_client()

    def _init_genai_client(self) -> Any | None:
        if genai is None:
            return None
        try:
            if self.settings.google_api_key:
                return genai.Client(api_key=self.settings.google_api_key)
            cred_path = (
                self.settings.google_application_credentials
                or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            )
            if cred_path and os.path.isfile(cred_path):
                os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", cred_path)
            return genai.Client(
                vertexai=True,
                project=self.settings.gcp_project_id,
                location=self.settings.vertex_ai_location,
            )
        except Exception as e:
            logger.warning(f"Vertex AI GenAI client initialization skipped: {e}")
            return None

    def generate_embedding(self, text: str) -> list[float]:
        """Generate a 768-dimensional embedding vector via Vertex AI text-embedding-004 or deterministic fallback."""
        clean_text = (text or "").strip() or "empty"
        if self._client is not None and genai_types is not None:
            try:
                response = self._client.models.embed_content(
                    model=self.settings.embedding_model_name,
                    contents=[clean_text],
                    config=genai_types.EmbedContentConfig(
                        task_type="RETRIEVAL_DOCUMENT",
                        output_dimensionality=768,
                    ),
                )
                if response.embeddings and len(response.embeddings) > 0:
                    values = list(response.embeddings[0].values)
                    if len(values) == 768:
                        return values
            except Exception as e:
                logger.warning(
                    f"Falling back to deterministic local 768-dim embedding due to API error: {e}"
                )

        return self._deterministic_embedding(clean_text)

    @staticmethod
    def _deterministic_embedding(text: str) -> list[float]:
        """Produce a normalized 768-dimensional float vector deterministically from text tokens."""
        vec = [0.0] * 768
        words = re.findall(r"[a-z0-9]+", text.lower())
        if not words:
            words = ["neutral"]
        for word in words:
            digest = hashlib.sha256(word.encode("utf-8")).digest()
            for i in range(32):
                idx = (digest[i] + i * 24) % 768
                sign = 1.0 if (digest[(i + 7) % 32] % 2 == 0) else -1.0
                vec[idx] += sign * (1.0 + (digest[i] / 255.0))
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            return [1.0 / math.sqrt(768)] * 768
        return [round(v / norm, 6) for v in vec]

    def retrieve_few_shot_exemplars(
        self,
        project_id: str,
        context_text: str,
        group_name: str | None = None,
        limit: int = 5,
    ) -> list[SentimentCalibrationResponse]:
        """Retrieve top-5 semantically similar overrides using 768-dim vector search; returns [] on cold start."""
        query_vector = self.generate_embedding(context_text)
        return self.sentiment_repo.find_nearest_exemplars(
            query_vector=query_vector,
            limit=limit,
            project_id=project_id,
            group_name=group_name,
        )

    def build_speaker_blind_prompt(
        self,
        blocks: list[SpeakerBlindBlockInput],
        canonical_groups: list[str],
        few_shot_exemplars: list[SentimentCalibrationResponse],
    ) -> str:
        """Build speaker-blind prompt with either Few-Shot calibration anchors or Zero-Shot cold-start instructions."""
        groups_str = ", ".join(canonical_groups) if canonical_groups else "BUYER, VENDOR, INTERNAL"
        blocks_json = json.dumps([b.model_dump() for b in blocks], indent=2)

        if few_shot_exemplars:
            exemplar_lines = []
            for idx, ex in enumerate(few_shot_exemplars[:5], start=1):
                exemplar_lines.append(
                    f"Exemplar {idx}: Text={json.dumps(ex.dialogue_text)} | "
                    f"CalibratedScore={ex.benchmark_score} | "
                    f"Rubric={json.dumps(ex.rubric_breakdown)}"
                )
            calibration_section = (
                "FEW-SHOT CALIBRATION ANCHORS (Top-K Human Adjudicator Overrides for this Project):\n"
                + "\n".join(exemplar_lines)
            )
        else:
            calibration_section = (
                "ZERO-SHOT COLD START MODE: No historical human overrides exist for this project. "
                "Apply baseline 4-dimension additive rubric instructions strictly."
            )

        return (
            "You are an enterprise risk and relationship sentiment analyst.\n"
            "CRITICAL PRIVACY RULE: Speaker identities have been stripped. Score strictly what was said.\n"
            f"Allowed Canonical Groups: [{groups_str}]\n\n"
            "4-Dimension Additive Rubric (0-25 integers each, summing to 0-100 pulse_score):\n"
            "- emotional_valence (0=hostile/frustrated, 12=neutral, 25=enthusiastic/praising)\n"
            "- delivery_alignment (0=blocker/dispute, 12=routine status, 25=milestone approval)\n"
            "- relationship_trust (0=blame/audit threat, 12=neutral professional, 25=high trust)\n"
            "- momentum_commitment (0=stalling/freeze, 12=standard follow-up, 25=proactive commitment)\n\n"
            f"{calibration_section}\n\n"
            f"SPEAKER-BLIND DIALOGUE BLOCKS:\n{blocks_json}\n"
        )

    def analyze_meeting_blocks(
        self,
        project_id: str,
        blocks: list[DialogueBlockResponse | dict[str, Any]],
        canonical_groups: list[str] | None = None,
    ) -> tuple[PostMeetingAnalysisResponse, dict[str, Any]]:
        """Execute speaker-blind structured rubric scoring with Few-Shot vector retrieval or Zero-Shot fallback."""
        allowed_groups = canonical_groups or ["BUYER", "VENDOR", "INTERNAL"]
        blind_blocks = strip_speaker_identity(blocks)
        concatenated_text = " ".join(b.scrubbed_text for b in blind_blocks)

        exemplars = self.retrieve_few_shot_exemplars(
            project_id=project_id,
            context_text=concatenated_text,
            limit=5,
        )
        inference_mode = "FEW_SHOT" if exemplars else "ZERO_SHOT"
        prompt = self.build_speaker_blind_prompt(
            blocks=blind_blocks,
            canonical_groups=allowed_groups,
            few_shot_exemplars=exemplars,
        )

        metadata: dict[str, Any] = {
            "model_version": self.settings.gemini_model_name,
            "embedding_model": self.settings.embedding_model_name,
            "inference_mode": inference_mode,
            "few_shot_count": len(exemplars),
            "few_shot_ids": [e.calibration_id for e in exemplars],
            "speaker_blind": True,
        }

        if self._client is not None and genai_types is not None:
            try:
                response = self._client.models.generate_content(
                    model=self.settings.gemini_model_name,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=PostMeetingAnalysisResponse,
                        temperature=0.1,
                    ),
                )
                if getattr(response, "parsed", None) is not None and isinstance(
                    response.parsed, PostMeetingAnalysisResponse
                ):
                    return response.parsed, metadata
                if getattr(response, "text", None):
                    parsed = PostMeetingAnalysisResponse.model_validate_json(
                        response.text
                    )
                    return parsed, metadata
            except Exception as e:
                logger.warning(
                    f"Gemini structured inference fell back to deterministic scorer: {e}"
                )

        return (
            self._deterministic_meeting_analysis(
                blind_blocks, allowed_groups, exemplars
            ),
            metadata,
        )

    def _deterministic_meeting_analysis(
        self,
        blind_blocks: list[SpeakerBlindBlockInput],
        allowed_groups: list[str],
        exemplars: list[SentimentCalibrationResponse],
    ) -> PostMeetingAnalysisResponse:
        """Deterministic speaker-blind rubric scorer for local dev and automated test verification."""
        block_results: list[BlockInferenceResult] = []
        all_liked: list[str] = []
        all_disliked: list[str] = []
        draft_risks: list[DraftRiskResult] = []
        action_items: list[ActionItemResult] = []

        # Calculate calibration shift if few-shot exemplars are present
        calibration_bias = 0.0
        if exemplars:
            avg_bench = sum(e.benchmark_score for e in exemplars) / len(exemplars)
            calibration_bias = (avg_bench - 50.0) * 0.15

        for idx, b in enumerate(blind_blocks):
            words = re.findall(r"[a-zA-Z]+", b.scrubbed_text.lower())
            pos_hits = [w for w in words if w in _POSITIVE_CUES]
            neg_hits = [w for w in words if w in _NEGATIVE_CUES]

            all_liked.extend(pos_hits)
            all_disliked.extend(neg_hits)

            delta = (len(pos_hits) * 4) - (len(neg_hits) * 5) + int(round(calibration_bias / 4.0))
            ev = max(0, min(25, 13 + delta))
            da = max(0, min(25, 13 + delta))
            rt = max(0, min(25, 12 + delta))
            mc = max(0, min(25, 12 + delta))

            rubric = RubricScoresSchema(
                emotional_valence=ev,
                delivery_alignment=da,
                relationship_trust=rt,
                momentum_commitment=mc,
            )
            group_choice = allowed_groups[idx % len(allowed_groups)]
            block_results.append(
                BlockInferenceResult(
                    block_id=b.block_id,
                    suggested_group_name=group_choice,
                    rubric_breakdown=rubric,
                    pulse_score=rubric.total_score(),
                    confidence=0.91 if exemplars else 0.85,
                )
            )

            if neg_hits and len(draft_risks) < 3:
                draft_risks.append(
                    DraftRiskResult(
                        title=f"Delivery & Alignment Concern ({b.block_id})",
                        contextual_description=b.scrubbed_text[:180],
                        associated_groups=[group_choice],
                        category="COMPLIANCE" if "audit" in neg_hits else "OPERATIONAL",
                        impact_score=4,
                        probability_score=4 if len(neg_hits) > 1 else 3,
                        recommended_mitigation="Schedule immediate cross-group alignment review.",
                    )
                )

            if any(k in words for k in ("deliver", "send", "schedule", "review", "update")):
                action_items.append(
                    ActionItemResult(
                        description=f"Follow up on: {b.scrubbed_text[:90]}",
                        owner_group=group_choice,
                        due_date=None,
                    )
                )

        default_liked = ["alignment", "milestone", "clarity", "progress", "delivery"]
        default_disliked = ["delay", "blocker", "ambiguity", "overrun", "escalation"]
        liked_top = list(dict.fromkeys(all_liked + default_liked))[:5]
        disliked_top = list(dict.fromkeys(all_disliked + default_disliked))[:5]

        group_keywords = [
            GroupKeywordsResult(
                group_name=grp,
                top_liked_words=liked_top,
                top_disliked_words=disliked_top,
            )
            for grp in allowed_groups
        ]

        return PostMeetingAnalysisResponse(
            inferred_company_name="Acme Enterprise Corp",
            agenda=["Milestone & Deliverable Review", "Risk & Compliance Alignment"],
            topics_of_discussion=["Project timeline", "Deliverable sign-off"],
            summary="Speaker-blind baseline analysis completed across dialogue blocks.",
            action_items=action_items[:5],
            recommended_mitigations=[
                "Review flagged low-sentiment dialogue blocks during HITL adjudication."
            ],
            block_results=block_results,
            group_keywords=group_keywords,
            draft_risks=draft_risks,
        )

    def run_post_meeting_scoring_pipeline(
        self,
        meeting_id: str,
        project_id: str,
    ) -> dict[str, Any]:
        """Run end-to-end post-meeting baseline scoring, update blocks, create draft risks, and transition to PENDING_ADJUDICATION."""
        blocks = self.meeting_repo.list_dialogue_blocks(meeting_id)
        if not blocks:
            return {"status": "no_blocks", "meeting_id": meeting_id}

        # Check project canonical groups if available
        canonical_groups = ["BUYER", "VENDOR", "INTERNAL"]
        if self.db is not None:
            proj_doc = self.db.collection("projects").document(project_id).get()
            if proj_doc.exists:
                proj_data = proj_doc.to_dict() or {}
                if proj_data.get("canonical_groups"):
                    canonical_groups = list(proj_data["canonical_groups"])

        analysis, model_meta = self.analyze_meeting_blocks(
            project_id=project_id,
            blocks=blocks,
            canonical_groups=canonical_groups,
        )

        result_by_block = {r.block_id: r for r in analysis.block_results}
        keywords_by_group = {k.group_name: k for k in analysis.group_keywords}

        group_weighted_sums: dict[str, float] = {}
        group_weights: dict[str, int] = {}
        group_counts: dict[str, int] = {}

        for block in blocks:
            res = result_by_block.get(block.block_id)
            if not res:
                continue
            emb = self.generate_embedding(block.text_scrubbed)
            rubric_dict = res.rubric_breakdown.model_dump()
            score = float(res.pulse_score)
            grp = res.suggested_group_name

            self.meeting_repo.update_dialogue_block(
                meeting_id=meeting_id,
                block_id=block.block_id,
                updates={
                    "group_id": grp,
                    "group_name": grp,
                    "company_name": analysis.inferred_company_name,
                    "optional_participant_name": None,
                    "sentiment_score": score,
                    "ai_initial_score": score,
                    "ai_confidence": res.confidence,
                    "rubric_scores": rubric_dict,
                    "embedding": emb,
                },
            )

            w = max(1, block.word_count or len(block.text_scrubbed.split()))
            group_weighted_sums[grp] = group_weighted_sums.get(grp, 0.0) + (score * w)
            group_weights[grp] = group_weights.get(grp, 0) + w
            group_counts[grp] = group_counts.get(grp, 0) + 1

        group_scores: dict[str, Any] = {}
        for grp, weighted_sum in group_weighted_sums.items():
            total_w = max(1, group_weights.get(grp, 1))
            grp_score = round(weighted_sum / total_w, 1)
            kw = keywords_by_group.get(grp)
            group_scores[grp] = GroupPulseMetric(
                pulse_score=grp_score,
                block_count=group_counts.get(grp, 1),
                top_liked_words=kw.top_liked_words if kw else [],
                top_disliked_words=kw.top_disliked_words if kw else [],
            ).model_dump()

        overall_pulse = (
            round(
                sum(g["pulse_score"] for g in group_scores.values()) / len(group_scores),
                1,
            )
            if group_scores
            else 50.0
        )

        mom_summary = MoMSummary(
            date_time=datetime.now(timezone.utc).isoformat(),
            location="Google Meet",
            title=f"Meeting {meeting_id}",
            agenda=analysis.agenda,
            topics_of_discussion=analysis.topics_of_discussion,
            summary=analysis.summary,
            action_items=[
                ActionItem(
                    action_id=f"act-{i + 1:02d}",
                    description=item.description,
                    owner_group=item.owner_group,
                    due_date=item.due_date,
                )
                for i, item in enumerate(analysis.action_items)
            ],
            recommended_mitigations=analysis.recommended_mitigations,
        ).model_dump()

        for idx, dr in enumerate(analysis.draft_risks):
            cat_str = dr.category.upper()
            cat = (
                RiskCategory(cat_str)
                if cat_str in RiskCategory.__members__
                else RiskCategory.OPERATIONAL
            )
            risk_id = f"RSK-{meeting_id[-6:].upper()}-{idx + 1:02d}"
            self.risk_repo.create_risk(
                RiskRegisterCreate(
                    risk_id=risk_id,
                    project_id=project_id,
                    meeting_id=meeting_id,
                    company_name=analysis.inferred_company_name,
                    associated_groups=dr.associated_groups,
                    title=dr.title,
                    description=dr.contextual_description,
                    category=cat,
                    status=RiskStatus.DRAFT_PENDING_ADJUDICATION,
                    impact=dr.impact_score,
                    probability=dr.probability_score,
                    mitigation_plan={"strategy": dr.recommended_mitigation},
                )
            )

        existing_meeting = self.meeting_repo.get_meeting(meeting_id)
        existing_meta = (
            dict(existing_meeting.model_metadata)
            if existing_meeting and isinstance(existing_meeting.model_metadata, dict)
            else {}
        )
        existing_meta.update(model_meta)

        self.meeting_repo.update_meeting(
            meeting_id=meeting_id,
            updates={
                "status": MeetingStatus.PENDING_ADJUDICATION.value,
                "pulse_score": overall_pulse,
                "group_scores": group_scores,
                "mom_summary": mom_summary,
                "model_metadata": existing_meta,
            },
        )

        return {
            "status": MeetingStatus.PENDING_ADJUDICATION.value,
            "pulse_score": overall_pulse,
            "group_scores": group_scores,
            "inference_mode": model_meta["inference_mode"],
            "few_shot_count": model_meta["few_shot_count"],
        }

    def explain_dialogue_block(
        self,
        meeting_id: str,
        block: DialogueBlockResponse,
    ) -> BlockExplainResponse:
        """Generate on-demand Explainable AI (XAI) rubric breakdown with server-side verbatim substring offset validation."""
        scrubbed_text = block.text_scrubbed or ""
        existing_rubric = block.rubric_scores

        if isinstance(existing_rubric, dict):
            rubric = RubricScoresSchema(
                emotional_valence=int(round(existing_rubric.get("emotional_valence", 12))),
                delivery_alignment=int(round(existing_rubric.get("delivery_alignment", 12))),
                relationship_trust=int(round(existing_rubric.get("relationship_trust", 13))),
                momentum_commitment=int(round(existing_rubric.get("momentum_commitment", 13))),
            )
        elif hasattr(existing_rubric, "emotional_valence"):
            rubric = RubricScoresSchema(
                emotional_valence=int(round(existing_rubric.emotional_valence)),
                delivery_alignment=int(round(existing_rubric.delivery_alignment)),
                relationship_trust=int(round(existing_rubric.relationship_trust)),
                momentum_commitment=int(round(existing_rubric.momentum_commitment)),
            )
        else:
            blind_res, _ = self.analyze_meeting_blocks(
                project_id="proj-default",
                blocks=[block],
            )
            rubric = (
                blind_res.block_results[0].rubric_breakdown
                if blind_res.block_results
                else RubricScoresSchema()
            )

        raw_attributions: list[SpanAttribution] = []

        if self._client is not None and genai_types is not None and scrubbed_text:
            prompt = (
                "You are an Explainable AI (XAI) rubric attribution analyzer.\n"
                "CRITICAL PRIVACY RULE: Speaker identity is omitted. Analyze strictly the text below.\n"
                "Extract 3 to 5 EXACT character-for-character verbatim substrings from `scrubbed_text` "
                "that justify the 4-dimension rubric scores.\n\n"
                f"Block ID: {block.block_id}\n"
                f"Scrubbed Text: {json.dumps(scrubbed_text)}\n"
                f"Current Rubric Breakdown: {rubric.model_dump_json()}\n"
            )
            try:
                response = self._client.models.generate_content(
                    model=self.settings.gemini_model_name,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=ExplainRationaleResponse,
                        temperature=0.0,
                    ),
                )
                parsed_resp: ExplainRationaleResponse | None = None
                if getattr(response, "parsed", None) is not None and isinstance(
                    response.parsed, ExplainRationaleResponse
                ):
                    parsed_resp = response.parsed
                elif getattr(response, "text", None):
                    parsed_resp = ExplainRationaleResponse.model_validate_json(
                        response.text
                    )
                if parsed_resp:
                    rubric = parsed_resp.rubric_breakdown
                    raw_attributions = parsed_resp.attributions
            except Exception as e:
                logger.warning(f"Gemini on-demand XAI fell back to local extractor: {e}")

        validated_spans = verify_and_locate_substrings(scrubbed_text, raw_attributions)

        if not validated_spans and scrubbed_text:
            fallback_spans = self._extract_deterministic_verbatim_spans(
                scrubbed_text, rubric
            )
            validated_spans = verify_and_locate_substrings(
                scrubbed_text, fallback_spans
            )

        pulse_score = (
            block.sentiment_score
            if block.sentiment_score is not None
            else float(rubric.total_score())
        )
        computed_at = datetime.now(timezone.utc).isoformat()

        explain_response = BlockExplainResponse(
            meeting_id=meeting_id,
            block_id=block.block_id,
            scrubbed_text=scrubbed_text,
            pulse_score=pulse_score,
            rubric_breakdown=rubric,
            attributions=validated_spans,
            computed_at=computed_at,
        )

        # Persist verified XAI attribution on the dialogue block
        self.meeting_repo.update_dialogue_block(
            meeting_id=meeting_id,
            block_id=block.block_id,
            updates={
                "rubric_scores": rubric.model_dump(),
                "sentiment_score": pulse_score,
                "xai_attribution": {
                    "computed_at": computed_at,
                    "attributions": [a.model_dump() for a in validated_spans],
                },
            },
        )

        return explain_response

    @staticmethod
    def _extract_deterministic_verbatim_spans(
        scrubbed_text: str, rubric: RubricScoresSchema
    ) -> list[SpanAttribution]:
        """Extract exact verbatim phrases from scrubbed_text for deterministic XAI fallback."""
        clauses = [
            c.strip()
            for c in re.split(r"[.!?;,]+", scrubbed_text)
            if c and c.strip()
        ]
        if not clauses:
            clauses = [scrubbed_text.strip()]

        dimensions = [
            "delivery_alignment",
            "relationship_trust",
            "emotional_valence",
            "momentum_commitment",
        ]
        spans: list[SpanAttribution] = []

        for idx, clause in enumerate(clauses[:4]):
            words = re.findall(r"[a-zA-Z]+", clause.lower())
            has_neg = any(w in _NEGATIVE_CUES for w in words)
            has_pos = any(w in _POSITIVE_CUES for w in words)

            if has_neg:
                weight = -0.82
                rationale = "Indicates delivery or compliance concern impacting alignment."
            elif has_pos:
                weight = 0.78
                rationale = "Demonstrates constructive alignment and forward commitment."
            else:
                weight = 0.15 if rubric.total_score() >= 50 else -0.25
                rationale = "Reflects baseline operational context in the discussion."

            spans.append(
                SpanAttribution(
                    verbatim_phrase=clause,
                    attribution_weight=weight,
                    rubric_dimension=dimensions[idx % len(dimensions)],
                    rationale=rationale,
                )
            )

        # If fewer than 3 clauses exist and the text has multiple words, add word-window spans
        if len(spans) < 3:
            words_with_matches = list(re.finditer(r"\S+", scrubbed_text))
            if len(words_with_matches) >= 4:
                mid = len(words_with_matches) // 2
                sub_start = words_with_matches[0].start()
                sub_end = words_with_matches[min(mid, len(words_with_matches) - 1)].end()
                phrase_1 = scrubbed_text[sub_start:sub_end]
                if all(s.verbatim_phrase != phrase_1 for s in spans):
                    spans.append(
                        SpanAttribution(
                            verbatim_phrase=phrase_1,
                            attribution_weight=0.25 if rubric.total_score() >= 50 else -0.35,
                            rubric_dimension="emotional_valence",
                            rationale="Opening phrasing sets the emotional valence of the block.",
                        )
                    )
                sub2_start = words_with_matches[mid].start()
                sub2_end = words_with_matches[-1].end()
                phrase_2 = scrubbed_text[sub2_start:sub2_end]
                if all(s.verbatim_phrase != phrase_2 for s in spans):
                    spans.append(
                        SpanAttribution(
                            verbatim_phrase=phrase_2,
                            attribution_weight=0.30 if rubric.total_score() >= 50 else -0.40,
                            rubric_dimension="momentum_commitment",
                            rationale="Closing segment establishes next-step commitment level.",
                        )
                    )

        return spans[:5]

    def suggest_project_governance(
        self,
        project_id: str,
        name: str = "",
        company_name: str = "",
        description: str = "",
    ) -> ProjectAISuggestGroupsResponse:
        """Suggest canonical stakeholder groups, risk categories, and pulse thresholds using Gemini 2.5 Flash or deterministic domain analysis."""
        clean_name = (name or project_id).strip()
        clean_company = (company_name or "").strip()
        clean_desc = (description or "").strip()
        combined_text = f"{clean_name} {clean_company} {clean_desc}".lower()

        if self._client is not None and genai_types is not None:
            try:
                prompt = (
                    "You are an enterprise governance architect for pRiskAI. "
                    "Analyze the project metadata below and recommend 4 to 6 canonical stakeholder groups "
                    "for speaker-to-group pulse tracking, 3 to 5 risk categories, and alert thresholds.\n\n"
                    f"Project ID: {project_id}\n"
                    f"Project Name: {clean_name}\n"
                    f"Client / Organization: {clean_company or 'Enterprise Client'}\n"
                    f"Description: {clean_desc or 'Cross-functional enterprise delivery initiative.'}\n\n"
                    "Return JSON with keys: suggested_canonical_groups (list of strings), "
                    "suggested_risk_categories (list of strings), "
                    "pulse_drop_delta (int 5..50), minimum_pulse_score (int 10..80), "
                    "and rationale (concise explanation without em dashes)."
                )
                response = self._client.models.generate_content(
                    model=self.settings.gemini_model_name,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.2,
                    ),
                )
                raw_json = json.loads(response.text or "{}")
                groups = [
                    str(g).strip()
                    for g in raw_json.get("suggested_canonical_groups", [])
                    if str(g).strip()
                ][:8]
                if len(groups) >= 2:
                    risk_cats = [
                        str(r).strip()
                        for r in raw_json.get("suggested_risk_categories", [])
                        if str(r).strip()
                    ] or ["STAKEHOLDER_ALIGNMENT", "DELIVERY_TIMELINE", "SCOPE_CREEP"]
                    drop_delta = max(5, min(50, int(raw_json.get("pulse_drop_delta", 15))))
                    min_score = max(10, min(80, int(raw_json.get("minimum_pulse_score", 42))))
                    rationale = str(
                        raw_json.get(
                            "rationale",
                            f"Structured stakeholder taxonomy tailored for {clean_name}.",
                        )
                    ).replace("—", ",")
                    return ProjectAISuggestGroupsResponse(
                        project_id=project_id,
                        suggested_canonical_groups=groups,
                        suggested_risk_categories=risk_cats,
                        recommended_alert_thresholds=ProjectAlertThresholds(
                            pulse_drop_delta=drop_delta,
                            minimum_pulse_score=min_score,
                            escalation_enabled=True,
                            escalation_intervals_hours=[24, 48, 72],
                        ),
                        rationale=rationale,
                        inference_mode="VERTEX_GEMINI",
                        model_version=self.settings.gemini_model_name,
                    )
            except Exception as exc:
                logger.warning(
                    f"Falling back to deterministic project governance suggestion for {project_id}: {exc}"
                )

        # Deterministic domain-aware fallback when no external AI API is configured
        if any(
            kw in combined_text
            for kw in ("bank", "fin", "payment", "treasury", "audit", "capital", "ledger", "tax")
        ):
            groups = [
                "Client Executive Sponsor",
                "Chief Risk & Compliance Office",
                "Treasury & Finance Operations",
                "Security & Audit Governance",
                "Internal Delivery Team",
            ]
            risk_categories = [
                "REGULATORY_COMPLIANCE",
                "FINANCIAL_OVERRUN",
                "SECURITY_GOVERNANCE",
                "DELIVERY_TIMELINE",
            ]
            thresholds = ProjectAlertThresholds(
                pulse_drop_delta=12,
                minimum_pulse_score=48,
                escalation_enabled=True,
                escalation_intervals_hours=[24, 48, 72],
            )
            domain_label = "financial and regulatory compliance"
        elif any(
            kw in combined_text
            for kw in ("health", "clinical", "medical", "hipaa", "patient", "pharma", "hospital")
        ):
            groups = [
                "Client Executive Sponsor",
                "Clinical Privacy & HIPAA Officer",
                "Healthcare IT & EHR Integration",
                "Quality Assurance Lead",
                "Internal Delivery Team",
            ]
            risk_categories = [
                "HIPAA_PRIVACY_COMPLIANCE",
                "CLINICAL_WORKFLOW_DISRUPTION",
                "DATA_INTEGRATION_RISK",
                "STAKEHOLDER_ALIGNMENT",
            ]
            thresholds = ProjectAlertThresholds(
                pulse_drop_delta=10,
                minimum_pulse_score=50,
                escalation_enabled=True,
                escalation_intervals_hours=[24, 48, 72],
            )
            domain_label = "healthcare and clinical data privacy"
        elif any(
            kw in combined_text
            for kw in (
                "cloud",
                "infra",
                "migration",
                "platform",
                "security",
                "data",
                "ai",
                "cyber",
                "engineering",
            )
        ):
            groups = [
                "Client Executive Sponsor",
                "Enterprise Architecture & Platform",
                "Information Security & DLP",
                "Client Product Engineering",
                "Internal Delivery Team",
            ]
            risk_categories = [
                "TECHNICAL_DEBT_MIGRATION",
                "SECURITY_DLP_EXPOSURE",
                "SCOPE_CREEP",
                "DELIVERY_VELOCITY",
            ]
            thresholds = ProjectAlertThresholds(
                pulse_drop_delta=14,
                minimum_pulse_score=44,
                escalation_enabled=True,
                escalation_intervals_hours=[24, 48, 72],
            )
            domain_label = "cloud infrastructure and security engineering"
        elif any(
            kw in combined_text
            for kw in ("legal", "contract", "procurement", "vendor", "counsel", "policy")
        ):
            groups = [
                "Client Executive Sponsor",
                "Client Legal & General Counsel",
                "Vendor Procurement & Commercials",
                "Compliance & Audit Lead",
                "Internal Delivery Team",
            ]
            risk_categories = [
                "CONTRACTUAL_LIABILITY",
                "COMMERCIAL_DISPUTE",
                "REGULATORY_COMPLIANCE",
                "STAKEHOLDER_CHURN",
            ]
            thresholds = ProjectAlertThresholds(
                pulse_drop_delta=12,
                minimum_pulse_score=46,
                escalation_enabled=True,
                escalation_intervals_hours=[24, 48, 72],
            )
            domain_label = "legal, procurement, and commercial governance"
        else:
            groups = [
                "Client Executive Sponsor",
                "Client Legal & Compliance",
                "Client Product & Engineering",
                "Operations & Change Management",
                "Internal Delivery Team",
            ]
            risk_categories = [
                "STAKEHOLDER_ALIGNMENT",
                "SCOPE_CREEP",
                "TIMELINE_SLIPPAGE",
                "COMMERCIAL_RISK",
            ]
            thresholds = ProjectAlertThresholds(
                pulse_drop_delta=15,
                minimum_pulse_score=42,
                escalation_enabled=True,
                escalation_intervals_hours=[24, 48, 72],
            )
            domain_label = "enterprise program delivery"

        org_clause = f" for {clean_company}" if clean_company else ""
        rationale = (
            f"Calibrated {len(groups)} canonical stakeholder groups and {len(risk_categories)} risk categories "
            f"around {domain_label} requirements in '{clean_name}'{org_clause}. "
            f"Recommended a {thresholds.pulse_drop_delta}-point pulse drop trigger and a minimum group health floor "
            f"of {thresholds.minimum_pulse_score} to catch relationship friction early."
        )

        return ProjectAISuggestGroupsResponse(
            project_id=project_id,
            suggested_canonical_groups=groups,
            suggested_risk_categories=risk_categories,
            recommended_alert_thresholds=thresholds,
            rationale=rationale,
            inference_mode="DETERMINISTIC_FALLBACK",
            model_version=self.settings.gemini_model_name,
        )

    def generate_admin_governance_digest(
        self,
        users: list[dict[str, Any]],
        projects: list[dict[str, Any]],
        pending_invitations: list[dict[str, Any]],
    ) -> AdminGovernanceDigestResponse:
        """Synthesize an AI governance digest across users, quarantined accounts, projects, and invitations."""
        now_iso = datetime.now(timezone.utc).isoformat()
        total_users = len(users)
        active_users_count = 0
        quarantined_users_count = 0
        role_distribution: dict[str, int] = {
            "ADMIN": 0,
            "EXECUTIVE": 0,
            "MANAGER": 0,
            "ADJUDICATOR": 0,
            "EXTERNAL_STAKEHOLDER": 0,
        }
        assigned_project_set: set[str] = set()

        for u in users:
            role_val = str(u.get("role", "EXTERNAL_STAKEHOLDER"))
            role_distribution[role_val] = role_distribution.get(role_val, 0) + 1
            user_projects = list(u.get("assigned_project_ids", []))
            for pid in user_projects:
                assigned_project_set.add(str(pid))

            status_val = str(u.get("onboarding_status", ""))
            if status_val == "ACTIVE" or (
                role_val != "EXTERNAL_STAKEHOLDER" or len(user_projects) > 0
            ):
                active_users_count += 1
            else:
                quarantined_users_count += 1

        invited_project_set = {
            str(inv.get("project_id", ""))
            for inv in pending_invitations
            if inv.get("project_id")
        }

        total_projects = len(projects)
        unassigned_projects_count = 0
        for p in projects:
            pid = str(p.get("project_id", ""))
            if pid and pid not in assigned_project_set and pid not in invited_project_set:
                unassigned_projects_count += 1

        pending_invitations_count = len(pending_invitations)

        if self._client is not None and genai_types is not None:
            try:
                prompt = (
                    "You are a security and RBAC governance analyst for pRiskAI. "
                    "Summarize the current identity and workspace posture based on these exact metrics:\n"
                    f"- Total Users: {total_users} (Active: {active_users_count}, Quarantined: {quarantined_users_count})\n"
                    f"- Role Distribution: {json.dumps(role_distribution)}\n"
                    f"- Total Projects: {total_projects} (Unassigned Projects: {unassigned_projects_count})\n"
                    f"- Pending Project Invitations: {pending_invitations_count}\n\n"
                    "Return JSON with keys: executive_summary (string, no em dashes), "
                    "key_findings (list of 3 strings), and recommended_actions (list of 3 strings)."
                )
                response = self._client.models.generate_content(
                    model=self.settings.gemini_model_name,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.2,
                    ),
                )
                raw_json = json.loads(response.text or "{}")
                exec_summary = str(raw_json.get("executive_summary", "")).strip().replace("—", ",")
                findings = [
                    str(f).strip().replace("—", ",")
                    for f in raw_json.get("key_findings", [])
                    if str(f).strip()
                ]
                actions = [
                    str(a).strip().replace("—", ",")
                    for a in raw_json.get("recommended_actions", [])
                    if str(a).strip()
                ]
                if exec_summary and findings and actions:
                    return AdminGovernanceDigestResponse(
                        generated_at=now_iso,
                        inference_mode="VERTEX_GEMINI",
                        model_version=self.settings.gemini_model_name,
                        total_users=total_users,
                        active_users_count=active_users_count,
                        quarantined_users_count=quarantined_users_count,
                        total_projects=total_projects,
                        unassigned_projects_count=unassigned_projects_count,
                        pending_invitations_count=pending_invitations_count,
                        role_distribution=role_distribution,
                        executive_summary=exec_summary,
                        key_findings=findings[:4],
                        recommended_actions=actions[:4],
                    )
            except Exception as exc:
                logger.warning(f"Falling back to deterministic admin governance digest: {exc}")

        # Deterministic fallback when no external AI API is configured
        key_findings: list[str] = [
            f"{active_users_count} of {total_users} registered accounts are active across {total_projects} configured project workspaces.",
        ]
        recommended_actions: list[str] = []

        if quarantined_users_count > 0:
            key_findings.append(
                f"{quarantined_users_count} External Stakeholder account(s) remain in QUARANTINED_PENDING_INVITATION state with zero project access."
            )
            recommended_actions.append(
                "Review quarantined External Stakeholder accounts and dispatch project invitations or de-provision stale registrations."
            )
        else:
            key_findings.append(
                "Zero accounts are stuck in quarantine; all External Stakeholders have verified project assignments."
            )

        if unassigned_projects_count > 0:
            key_findings.append(
                f"{unassigned_projects_count} project workspace(s) currently have no assigned stakeholders or pending invitations."
            )
            recommended_actions.append(
                "Assign at least one Project Manager or Stakeholder to unstaffed project workspaces to enable pulse tracking."
            )

        if pending_invitations_count > 0:
            key_findings.append(
                f"{pending_invitations_count} project invitation(s) are awaiting stakeholder acceptance."
            )
            recommended_actions.append(
                "Follow up with invitees holding pending project invitations so their custom claims synchronize before upcoming meetings."
            )

        if role_distribution.get("ADJUDICATOR", 0) == 0:
            recommended_actions.append(
                "Provision or elevate at least one ADJUDICATOR account to maintain Human-in-the-Loop (HITL) transcript verification throughput."
            )

        if not recommended_actions:
            recommended_actions.append(
                "Maintain regular weekly audits of role assignments and verify canonical stakeholder group taxonomies on new projects."
            )

        executive_summary = (
            f"Identity governance check evaluated {total_users} user account(s) and {total_projects} project workspace(s). "
            f"{active_users_count} account(s) hold active workspace access, {quarantined_users_count} account(s) are quarantined "
            f"pending project invitation, and {pending_invitations_count} invitation(s) await acceptance."
        )

        return AdminGovernanceDigestResponse(
            generated_at=now_iso,
            inference_mode="DETERMINISTIC_FALLBACK",
            model_version=self.settings.gemini_model_name,
            total_users=total_users,
            active_users_count=active_users_count,
            quarantined_users_count=quarantined_users_count,
            total_projects=total_projects,
            unassigned_projects_count=unassigned_projects_count,
            pending_invitations_count=pending_invitations_count,
            role_distribution=role_distribution,
            executive_summary=executive_summary,
            key_findings=key_findings,
            recommended_actions=recommended_actions,
        )

    def synthesize_pulse_trends(
        self,
        meetings: list[Any],
        time_window: str = "30D",
        start_date: str | None = None,
        end_date: str | None = None,
        project_ids: list[str] | None = None,
        now: datetime | None = None,
    ) -> PulseTrendsResponse:
        """Synthesize longitudinal meeting pulse trajectories across 7D, 30D, QTD, or Custom windows with Gemini 2.5 Flash commentary."""
        ref_now = now or datetime.now(timezone.utc)
        tw = (time_window or "30D").strip().upper()
        if tw not in ("7D", "30D", "QTD", "CUSTOM"):
            tw = "30D"

        if tw == "7D":
            start_dt = ref_now - timedelta(days=7)
            end_dt = ref_now
        elif tw == "30D":
            start_dt = ref_now - timedelta(days=30)
            end_dt = ref_now
        elif tw == "QTD":
            q_month = ((ref_now.month - 1) // 3) * 3 + 1
            start_dt = datetime(ref_now.year, q_month, 1, tzinfo=timezone.utc)
            end_dt = ref_now
        else:  # CUSTOM
            start_dt = ref_now - timedelta(days=30)
            if start_date:
                try:
                    s_parsed = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                    if s_parsed.tzinfo is None:
                        s_parsed = s_parsed.replace(tzinfo=timezone.utc)
                    start_dt = s_parsed
                except Exception:
                    pass
            end_dt = ref_now
            if end_date:
                try:
                    e_parsed = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                    if e_parsed.tzinfo is None:
                        e_parsed = e_parsed.replace(tzinfo=timezone.utc)
                    end_dt = e_parsed
                except Exception:
                    pass

        start_iso = start_dt.isoformat()
        end_iso = end_dt.isoformat()

        # Filter meetings matching window
        filtered_meetings = []
        for m in meetings:
            m_date_str = getattr(m, "meeting_date", None) or (
                m.get("meeting_date") if isinstance(m, dict) else None
            )
            if not m_date_str:
                filtered_meetings.append(m)
                continue
            try:
                m_dt = datetime.fromisoformat(str(m_date_str).replace("Z", "+00:00"))
                if m_dt.tzinfo is None:
                    m_dt = m_dt.replace(tzinfo=timezone.utc)
                if start_dt <= m_dt <= end_dt:
                    filtered_meetings.append(m)
            except Exception:
                filtered_meetings.append(m)

        # Build trajectory points
        trajectory_points: list[PulseTrendPoint] = []
        for m in filtered_meetings:
            m_dict = (
                m.model_dump()
                if hasattr(m, "model_dump")
                else (m if isinstance(m, dict) else {})
            )
            m_id = str(m_dict.get("meeting_id") or "mtg")
            p_id = str(m_dict.get("project_id") or "proj-alpha")
            title = str(m_dict.get("title") or f"Meeting {m_id}")
            m_date = str(m_dict.get("meeting_date") or start_iso)
            pulse = float(m_dict.get("pulse_score") or 50.0)
            grp_scores = dict(m_dict.get("group_scores") or {})
            stat = str(m_dict.get("status") or "PROCESSING_POST_MEETING")

            trajectory_points.append(
                PulseTrendPoint(
                    meeting_id=m_id,
                    project_id=p_id,
                    title=title,
                    meeting_date=m_date,
                    pulse_score=round(pulse, 1),
                    group_scores=grp_scores,
                    status=stat,
                )
            )

        trajectory_points.sort(key=lambda p: p.meeting_date)

        # Aggregate metrics
        total = len(trajectory_points)
        if total > 0:
            avg_pulse = round(
                sum(p.pulse_score for p in trajectory_points) / total, 1
            )
            pulse_change = round(
                trajectory_points[-1].pulse_score - trajectory_points[0].pulse_score, 1
            )
            lowest_pt = min(trajectory_points, key=lambda p: p.pulse_score)
            highest_pt = max(trajectory_points, key=lambda p: p.pulse_score)
            lowest_m = {
                "meeting_id": lowest_pt.meeting_id,
                "title": lowest_pt.title,
                "meeting_date": lowest_pt.meeting_date,
                "pulse_score": lowest_pt.pulse_score,
            }
            highest_m = {
                "meeting_id": highest_pt.meeting_id,
                "title": highest_pt.title,
                "meeting_date": highest_pt.meeting_date,
                "pulse_score": highest_pt.pulse_score,
            }

            grp_sums: dict[str, float] = {}
            grp_counts: dict[str, int] = {}
            for p in trajectory_points:
                for grp, val in p.group_scores.items():
                    sc = (
                        val.get("pulse_score")
                        if isinstance(val, dict)
                        else (getattr(val, "pulse_score", None) if val else None)
                    )
                    if isinstance(sc, (int, float)):
                        grp_sums[grp] = grp_sums.get(grp, 0.0) + float(sc)
                        grp_counts[grp] = grp_counts.get(grp, 0) + 1
            grp_averages = {
                grp: round(grp_sums[grp] / max(1, grp_counts[grp]), 1)
                for grp in grp_sums
            }
        else:
            avg_pulse = 50.0
            pulse_change = 0.0
            lowest_m = None
            highest_m = None
            grp_averages = {}

        aggregates = PulseTrendsAggregate(
            total_meetings=total,
            average_pulse=avg_pulse,
            pulse_change=pulse_change,
            lowest_pulse_meeting=lowest_m,
            highest_pulse_meeting=highest_m,
            group_averages=grp_averages,
        )

        commentary = self._synthesize_ai_pulse_commentary(
            time_window=tw,
            start_date=start_iso,
            end_date=end_iso,
            trajectory_points=trajectory_points,
            aggregates=aggregates,
        )

        pids = list(set(project_ids or [p.project_id for p in trajectory_points]))
        if not pids and trajectory_points:
            pids = ["proj-alpha"]

        return PulseTrendsResponse(
            time_window=tw,
            start_date=start_iso,
            end_date=end_iso,
            project_ids=pids,
            trajectory_points=trajectory_points,
            ai_commentary=commentary,
            aggregate_metrics=aggregates,
        )

    def _synthesize_ai_pulse_commentary(
        self,
        time_window: str,
        start_date: str,
        end_date: str,
        trajectory_points: list[PulseTrendPoint],
        aggregates: PulseTrendsAggregate,
    ) -> AiPulseCommentary:
        """Call Vertex AI Gemini 2.5 Flash Structured Outputs or fallback to deterministic synthesis."""
        if self._client is not None and genai_types is not None and trajectory_points:
            prompt = (
                f"You are Vertex AI Gemini synthesizing a longitudinal pulse trends executive commentary for project stakeholders.\n"
                f"Window: {time_window} ({start_date[:10]} to {end_date[:10]})\n"
                f"Total Meetings: {aggregates.total_meetings}\n"
                f"Average Pulse: {aggregates.average_pulse}\n"
                f"Pulse Shift (Net): {aggregates.pulse_change:+.1f} points\n"
                f"Trajectory Points:\n"
                + "\n".join(
                    f"- {p.meeting_date[:10]}: '{p.title}' (Pulse {p.pulse_score}) | Groups: {p.group_scores}"
                    for p in trajectory_points
                )
                + "\n\nProvide an executive headline, 2-sentence trajectory summary, list key drivers of shifts, summarize trends per canonical group, flag any risk warnings (if pulse drops <40 or swings >15), and list 2 actionable interventions."
            )
            try:
                response = self._client.models.generate_content(
                    model=self.settings.gemini_model_name,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=AiPulseCommentary,
                        temperature=0.2,
                    ),
                )
                if getattr(response, "parsed", None) and isinstance(
                    response.parsed, AiPulseCommentary
                ):
                    return response.parsed
                if getattr(response, "text", None):
                    return AiPulseCommentary.model_validate_json(response.text)
            except Exception as e:
                logger.warning(
                    f"Gemini longitudinal pulse commentary fell back to deterministic generator: {e}"
                )

        return self._deterministic_pulse_commentary(
            time_window=time_window,
            start_date=start_date,
            end_date=end_date,
            trajectory_points=trajectory_points,
            aggregates=aggregates,
        )

    def _deterministic_pulse_commentary(
        self,
        time_window: str,
        start_date: str,
        end_date: str,
        trajectory_points: list[PulseTrendPoint],
        aggregates: PulseTrendsAggregate,
    ) -> AiPulseCommentary:
        """Deterministic commentary generator for local testing and offline execution."""
        total = aggregates.total_meetings
        avg_pulse = aggregates.average_pulse
        delta = aggregates.pulse_change

        if total == 0:
            return AiPulseCommentary(
                headline=f"No Meeting Activity Recorded in {time_window} Window",
                trajectory_summary=f"No verified sessions found between {start_date[:10]} and {end_date[:10]}. Schedule or ingest meetings to establish baseline pulse trajectory.",
                key_drivers_of_shifts=["No recorded dialogue blocks in current time horizon."],
                group_trends={},
                risk_warning=None,
                recommended_interventions=[
                    "Dispatch MeetStream bot to upcoming project checkpoints.",
                    "Verify canonical group taxonomies in Project Governance.",
                ],
            )

        if delta >= 6.0:
            headline = f"Cross-Group Alignment Strengthening (+{delta:.1f} pts) Across {time_window} Horizon"
        elif delta <= -6.0:
            headline = f"Sentiment Friction Detected ({delta:.1f} pts Shift) Across {time_window} Horizon"
        else:
            headline = f"Stable Cross-Group Alignment (Average {avg_pulse:.1f}) in {time_window} Window"

        summary = (
            f"Over the {time_window} evaluation period ({start_date[:10]} to {end_date[:10]}), {total} meeting session(s) "
            f"averaged a pulse score of {avg_pulse:.1f}. Sentiment trajectory moved from {trajectory_points[0].pulse_score:.1f} "
            f"to {trajectory_points[-1].pulse_score:.1f} ({delta:+.1f} net change)."
        )

        drivers: list[str] = []
        if aggregates.lowest_pulse_meeting:
            low = aggregates.lowest_pulse_meeting
            drivers.append(
                f"Lowest session pulse ({low['pulse_score']:.1f}) recorded in '{low['title']}' on {str(low['meeting_date'])[:10]}."
            )
        if aggregates.highest_pulse_meeting:
            high = aggregates.highest_pulse_meeting
            drivers.append(
                f"Peak alignment ({high['pulse_score']:.1f}) achieved during '{high['title']}' on {str(high['meeting_date'])[:10]}."
            )
        if delta < 0:
            drivers.append("Milestone deliverable ambiguity and cross-vendor dependencies created sentiment headwinds.")
        else:
            drivers.append("Resolution of open architectural blockers and schedule clarity restored stakeholder trust.")

        group_trends: dict[str, str] = {}
        for grp, g_avg in aggregates.group_averages.items():
            if g_avg >= 70.0:
                group_trends[grp] = f"Positive and aligned (average pulse: {g_avg:.1f})."
            elif g_avg >= 45.0:
                group_trends[grp] = f"Guarded / neutral alignment (average pulse: {g_avg:.1f})."
            else:
                group_trends[grp] = f"Critical delivery friction detected (average pulse: {g_avg:.1f})."

        risk_warning: str | None = None
        has_critical_drop = any(p.pulse_score < 40.0 for p in trajectory_points)
        has_steep_plunge = delta <= -15.0
        if has_critical_drop or has_steep_plunge:
            risk_warning = (
                f"Systemic Pulse Drop Alert: Session pulse dropped below critical threshold (<40 or >15 pt swing) "
                f"during the {time_window} window. Immediate executive escalation and delivery alignment recommended."
            )

        interventions = [
            "Convene cross-functional sprint review with lagging stakeholder groups to address delivery blockers.",
            "Review flagged DRAFT_PENDING_ADJUDICATION risks and execute prioritized mitigations.",
        ]

        return AiPulseCommentary(
            headline=headline,
            trajectory_summary=summary,
            key_drivers_of_shifts=drivers,
            group_trends=group_trends,
            risk_warning=risk_warning,
            recommended_interventions=interventions,
        )

    def regenerate_meeting_insights(
        self,
        meeting_id: str,
        project_id: str,
    ) -> dict[str, Any]:
        """Re-synthesize Minutes of Meeting (MoM), top keywords per Group, and draft risks using Adjudicator-updated Group tags and adjusted Pulse scores."""
        meeting = self.meeting_repo.get_meeting(meeting_id)
        if not meeting:
            raise KeyError(f"Meeting '{meeting_id}' not found")

        blocks = self.meeting_repo.list_dialogue_blocks(meeting_id)
        if not blocks:
            return {
                "status": "no_blocks",
                "meeting_id": meeting_id,
                "pulse_score": 50.0,
                "group_scores": {},
                "inference_mode": "ZERO_BLOCKS",
                "few_shot_count": 0,
            }

        # Project canonical groups
        canonical_groups = ["BUYER", "VENDOR", "INTERNAL"]
        if self.db is not None:
            proj_doc = self.db.collection("projects").document(project_id).get()
            if proj_doc.exists:
                proj_data = proj_doc.to_dict() or {}
                if proj_data.get("canonical_groups"):
                    canonical_groups = list(proj_data["canonical_groups"])

        # Fetch few-shot exemplars
        exemplars = self.sentiment_repo.list_calibrations(
            project_id=project_id
        )[:5]

        # Build adjudicated block summaries reflecting human overrides
        adjudicated_block_summaries: list[dict[str, Any]] = []
        for b in blocks:
            active_grp = b.group_name or b.group_id or "INTERNAL"
            active_score = (
                b.sentiment_score
                if b.sentiment_score is not None
                else (b.ai_initial_score if b.ai_initial_score is not None else 50.0)
            )
            adjudicated_block_summaries.append(
                {
                    "block_id": b.block_id,
                    "group": active_grp,
                    "sentiment_score": active_score,
                    "is_human_overridden": bool(b.is_human_overridden),
                    "is_pinned": bool(b.is_pinned),
                    "text": b.text_scrubbed,
                }
            )

        prompt = (
            f"You are Vertex AI Gemini analyzing an enterprise business meeting ({meeting_id}) in project {project_id}.\n"
            f"Human Adjudicators have reviewed and updated dialogue blocks with verified Group tags and adjusted sentiment scores:\n"
            f"{json.dumps(adjudicated_block_summaries, indent=2)}\n\n"
            f"Canonical Stakeholder Groups: {', '.join(canonical_groups)}\n\n"
            f"Instructions:\n"
            f"1. Synthesize accurate Minutes of Meeting (MoM) reflecting the discussions, consensus, and action items according to the assigned stakeholder groups.\n"
            f"2. Extract the top 5 liked and top 5 disliked words specifically for each stakeholder group based on their assigned dialogue blocks.\n"
            f"3. Discover draft risks (status: DRAFT_PENDING_ADJUDICATION) focusing on unresolved friction, low-scoring blocks, or commitments at risk.\n"
            f"4. Propose actionable recommended mitigations.\n"
        )

        analysis: PostMeetingAnalysisResponse | None = None
        inference_mode = "FEW_SHOT" if exemplars else "ZERO_SHOT"

        if self._client is not None and genai_types is not None:
            try:
                response = self._client.models.generate_content(
                    model=self.settings.gemini_model_name,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=PostMeetingAnalysisResponse,
                        temperature=0.1,
                    ),
                )
                if getattr(response, "parsed", None) and isinstance(
                    response.parsed, PostMeetingAnalysisResponse
                ):
                    analysis = response.parsed
                elif getattr(response, "text", None):
                    analysis = PostMeetingAnalysisResponse.model_validate_json(
                        response.text
                    )
            except Exception as e:
                logger.warning(
                    f"Regenerate insights LLM call fell back to deterministic generator: {e}"
                )

        if analysis is None:
            analysis = self._deterministic_regeneration_analysis(
                blocks=blocks,
                canonical_groups=canonical_groups,
                exemplars=exemplars,
            )
            inference_mode = "DETERMINISTIC_REGENERATION"

        # Re-compute group pulse scores and overall pulse strictly respecting human overrides
        group_weighted_sums: dict[str, float] = {}
        group_weights: dict[str, int] = {}
        group_counts: dict[str, int] = {}
        keywords_by_group = {k.group_name: k for k in analysis.group_keywords}

        for block in blocks:
            grp = block.group_name or block.group_id or "INTERNAL"
            score = (
                block.sentiment_score
                if block.sentiment_score is not None
                else (
                    block.ai_initial_score
                    if block.ai_initial_score is not None
                    else 50.0
                )
            )
            w = max(1, block.word_count or len(block.text_scrubbed.split()))
            group_weighted_sums[grp] = group_weighted_sums.get(grp, 0.0) + (score * w)
            group_weights[grp] = group_weights.get(grp, 0) + w
            group_counts[grp] = group_counts.get(grp, 0) + 1

        group_scores: dict[str, Any] = {}
        for grp, weighted_sum in group_weighted_sums.items():
            total_w = max(1, group_weights.get(grp, 1))
            grp_score = round(weighted_sum / total_w, 1)
            kw = keywords_by_group.get(grp)
            group_scores[grp] = GroupPulseMetric(
                pulse_score=grp_score,
                block_count=group_counts.get(grp, 1),
                top_liked_words=kw.top_liked_words if kw else [],
                top_disliked_words=kw.top_disliked_words if kw else [],
            ).model_dump()

        overall_pulse = (
            round(
                sum(g["pulse_score"] for g in group_scores.values()) / len(group_scores),
                1,
            )
            if group_scores
            else 50.0
        )

        mom_dict = MoMSummary(
            date_time=datetime.now(timezone.utc).isoformat(),
            location=(
                getattr(meeting.mom_summary, "location", "Google Meet")
                if hasattr(meeting.mom_summary, "location")
                else "Google Meet"
            ),
            title=meeting.title or f"Meeting {meeting_id}",
            agenda=analysis.agenda or ["Stakeholder Review", "Risk Alignment"],
            topics_of_discussion=analysis.topics_of_discussion
            or ["Action Items", "Deliverables"],
            summary=analysis.summary,
            action_items=[
                ActionItem(
                    action_id=f"act-{i + 1:02d}",
                    description=item.description,
                    owner_group=item.owner_group,
                    due_date=item.due_date,
                )
                for i, item in enumerate(analysis.action_items)
            ],
            recommended_mitigations=analysis.recommended_mitigations,
        ).model_dump()

        # Update meeting record
        now_iso = datetime.now(timezone.utc).isoformat()
        self.meeting_repo.update_meeting(
            meeting_id,
            {
                "mom_summary": mom_dict,
                "group_scores": group_scores,
                "pulse_score": overall_pulse,
                "status": MeetingStatus.PENDING_ADJUDICATION.value,
                "updated_at": now_iso,
            },
        )

        # Refresh DRAFT_PENDING_ADJUDICATION draft risks in risk_register
        created_risks_count = 0
        if self.db is not None:
            existing_risks = self.risk_repo.list_risks(project_id=project_id)
            for r in existing_risks:
                if r.meeting_id == meeting_id and (
                    str(r.status) in ("DRAFT_PENDING_ADJUDICATION", RiskStatus.DRAFT_PENDING_ADJUDICATION.value)
                    or r.status == RiskStatus.DRAFT_PENDING_ADJUDICATION
                ):
                    self.db.collection("risk_register").document(r.risk_id).delete()

            for idx, dr in enumerate(analysis.draft_risks):
                cat_str = dr.category.upper()
                cat = (
                    RiskCategory(cat_str)
                    if cat_str in RiskCategory.__members__
                    else RiskCategory.OPERATIONAL
                )
                self.risk_repo.create_risk(
                    RiskRegisterCreate(
                        risk_id=f"risk_regen_{meeting_id}_{idx + 1:02d}_{uuid.uuid4().hex[:6]}",
                        project_id=project_id,
                        meeting_id=meeting_id,
                        company_name=analysis.inferred_company_name,
                        associated_groups=dr.associated_groups or [canonical_groups[0]],
                        title=dr.title,
                        description=dr.contextual_description,
                        category=cat,
                        impact_score=dr.impact_score,
                        probability_score=dr.probability_score,
                        status=RiskStatus.DRAFT_PENDING_ADJUDICATION,
                        recommended_mitigation=dr.recommended_mitigation,
                    )
                )
                created_risks_count += 1

        return {
            "status": "insights_regenerated",
            "meeting_id": meeting_id,
            "pulse_score": overall_pulse,
            "group_scores": group_scores,
            "mom_summary": mom_dict,
            "draft_risks_created": created_risks_count,
            "inference_mode": inference_mode,
            "few_shot_count": len(exemplars),
        }

    def _deterministic_regeneration_analysis(
        self,
        blocks: list[DialogueBlockResponse],
        canonical_groups: list[str],
        exemplars: list[SentimentCalibrationResponse],
    ) -> PostMeetingAnalysisResponse:
        """Deterministic re-synthesis reflecting human-adjudicated group assignments and scores."""
        action_items: list[ActionItemResult] = []
        draft_risks: list[DraftRiskResult] = []
        group_keywords_map: dict[str, dict[str, list[str]]] = {
            grp: {"liked": [], "disliked": []} for grp in canonical_groups
        }

        for idx, b in enumerate(blocks):
            grp = b.group_name or b.group_id or canonical_groups[0]
            if grp not in group_keywords_map:
                group_keywords_map[grp] = {"liked": [], "disliked": []}

            words = re.findall(r"[a-zA-Z]+", b.text_scrubbed.lower())
            pos = [w for w in words if w in _POSITIVE_CUES]
            neg = [w for w in words if w in _NEGATIVE_CUES]

            group_keywords_map[grp]["liked"].extend(pos)
            group_keywords_map[grp]["disliked"].extend(neg)

            sc = (
                b.sentiment_score
                if b.sentiment_score is not None
                else (b.ai_initial_score or 50.0)
            )
            if sc < 45.0 or neg:
                draft_risks.append(
                    DraftRiskResult(
                        title=f"Adjudicated Delivery Friction ({grp})",
                        contextual_description=f"Block {b.block_id}: {b.text_scrubbed[:150]}",
                        associated_groups=[grp],
                        category="COMPLIANCE" if "audit" in neg else "OPERATIONAL",
                        impact_score=4 if sc < 35.0 else 3,
                        probability_score=4 if len(neg) > 1 else 3,
                        recommended_mitigation=f"Schedule focused alignment with {grp} leads.",
                    )
                )

            if any(k in words for k in ("deliver", "send", "schedule", "review", "update")):
                action_items.append(
                    ActionItemResult(
                        description=f"Action from block {b.block_id}: {b.text_scrubbed[:80]}",
                        owner_group=grp,
                        due_date=None,
                    )
                )

        default_liked = ["alignment", "progress", "milestone", "delivery", "quality"]
        default_disliked = ["delay", "blocker", "risk", "ambiguity", "escalation"]

        group_keywords: list[GroupKeywordsResult] = []
        for grp, kw in group_keywords_map.items():
            liked = list(dict.fromkeys(kw["liked"] + default_liked))[:5]
            disliked = list(dict.fromkeys(kw["disliked"] + default_disliked))[:5]
            group_keywords.append(
                GroupKeywordsResult(
                    group_name=grp,
                    top_liked_words=liked,
                    top_disliked_words=disliked,
                )
            )

        return PostMeetingAnalysisResponse(
            inferred_company_name="Enterprise Client",
            agenda=["Adjudicated Stakeholder Review", "Risk Register Alignment"],
            topics_of_discussion=["Deliverable milestone sign-off", "Cross-group dependencies"],
            summary=f"Re-synthesized insights across {len(blocks)} dialogue blocks incorporating adjudicator group tags and adjusted pulse scores.",
            action_items=action_items[:5],
            recommended_mitigations=[
                "Review regenerated draft risks during the next project governance checkpoint."
            ],
            block_results=[],
            group_keywords=group_keywords,
            draft_risks=draft_risks[:3],
        )


def get_sentiment_service(db: Any | None = None) -> SentimentService:
    return SentimentService(db=db)

