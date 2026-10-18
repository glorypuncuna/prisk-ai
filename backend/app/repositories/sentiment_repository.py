import math
from typing import Any
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector

from app.core.database import get_firestore_client
from app.schemas.sentiment import (
    CorrectedContextCreate,
    CorrectedContextResponse,
    SentimentCalibrationCreate,
    SentimentCalibrationResponse,
)


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def _normalize_vector_field(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    if (
        "embedding" in out
        and hasattr(out["embedding"], "__iter__")
        and not isinstance(out["embedding"], list)
    ):
        out["embedding"] = list(out["embedding"])
    return out


class SentimentRepository:
    """Firestore repository for `sentiment_calibrations` and `corrected_contexts` Few-Shot vector search."""

    def __init__(self, db: Any | None = None) -> None:
        self.db = db or get_firestore_client()

    def create_calibration(
        self, calibration: SentimentCalibrationCreate
    ) -> SentimentCalibrationResponse:
        data = calibration.model_dump()
        save_data = dict(data)
        if save_data.get("embedding") is not None:
            try:
                save_data["embedding"] = Vector(save_data["embedding"])
            except Exception:
                pass
        self.db.collection("sentiment_calibrations").document(
            calibration.calibration_id
        ).set(save_data)
        return SentimentCalibrationResponse.model_validate(data)

    def get_calibration(self, calibration_id: str) -> SentimentCalibrationResponse | None:
        doc = (
            self.db.collection("sentiment_calibrations")
            .document(calibration_id)
            .get()
        )
        if not doc.exists:
            return None
        data = _normalize_vector_field(doc.to_dict() or {})
        return SentimentCalibrationResponse.model_validate(data)

    def list_calibrations(
        self, project_id: str | None = None
    ) -> list[SentimentCalibrationResponse]:
        col = self.db.collection("sentiment_calibrations")
        query = col.where("project_id", "==", project_id) if project_id else col
        snaps = query.stream()
        results: list[SentimentCalibrationResponse] = []
        for s in snaps:
            data = _normalize_vector_field(s.to_dict() or {})
            results.append(SentimentCalibrationResponse.model_validate(data))
        return results

    def create_corrected_context(
        self, context: CorrectedContextCreate
    ) -> CorrectedContextResponse:
        """Persist an Adjudicator override exemplar in `corrected_contexts` and mirror to `sentiment_calibrations`."""
        data = context.model_dump()
        save_data = dict(data)
        if save_data.get("embedding") is not None:
            try:
                save_data["embedding"] = Vector(save_data["embedding"])
            except Exception:
                pass
        self.db.collection("corrected_contexts").document(
            context.correction_id
        ).set(save_data)

        # Mirror into sentiment_calibrations so unified queries see all exemplars
        cal_data = {
            "calibration_id": context.correction_id,
            "project_id": context.project_id,
            "group_name": context.group_name,
            "dialogue_text": context.scrubbed_text,
            "benchmark_score": context.human_adjusted_score,
            "rubric_breakdown": context.rubric_breakdown,
            "embedding": save_data.get("embedding"),
            "adjudicator_uid": context.adjudicator_uid,
            "created_at": context.created_at,
        }
        self.db.collection("sentiment_calibrations").document(
            context.correction_id
        ).set(cal_data)
        return CorrectedContextResponse.model_validate(data)

    def list_corrected_contexts(
        self, project_id: str | None = None, group_name: str | None = None
    ) -> list[CorrectedContextResponse]:
        col = self.db.collection("corrected_contexts")
        query: Any = col
        if project_id:
            query = query.where("project_id", "==", project_id)
        if group_name:
            query = query.where("group_name", "==", group_name)
        snaps = query.stream()
        results: list[CorrectedContextResponse] = []
        for s in snaps:
            data = _normalize_vector_field(s.to_dict() or {})
            results.append(CorrectedContextResponse.model_validate(data))
        return results

    def find_nearest_corrected_contexts(
        self,
        query_vector: list[float],
        limit: int = 5,
        project_id: str | None = None,
        group_name: str | None = None,
    ) -> list[CorrectedContextResponse]:
        """Execute Firestore Native Vector Search (`find_nearest`) on `corrected_contexts` with cosine fallback."""
        col = self.db.collection("corrected_contexts")
        base_query: Any = col
        if project_id:
            base_query = base_query.where("project_id", "==", project_id)
        if group_name:
            base_query = base_query.where("group_name", "==", group_name)

        if hasattr(base_query, "find_nearest"):
            try:
                vector_query = base_query.find_nearest(
                    vector_field="embedding",
                    query_vector=Vector(query_vector),
                    distance_measure=DistanceMeasure.COSINE,
                    limit=limit,
                )
                snaps = list(vector_query.stream())
                if snaps:
                    return [
                        CorrectedContextResponse.model_validate(
                            _normalize_vector_field(s.to_dict() or {})
                        )
                        for s in snaps
                    ]
            except Exception:
                pass

        all_ctx = self.list_corrected_contexts(
            project_id=project_id, group_name=group_name
        )
        candidates = [c for c in all_ctx if c.embedding is not None]
        if not candidates:
            return []
        scored = [
            (c, _cosine_similarity(query_vector, c.embedding))
            for c in candidates
            if c.embedding
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [item[0] for item in scored[:limit]]

    def find_nearest_exemplars(
        self,
        query_vector: list[float],
        limit: int = 5,
        project_id: str | None = None,
        group_name: str | None = None,
    ) -> list[SentimentCalibrationResponse]:
        """Retrieve top-K nearest neighbors using Firestore Native Vector Search (`find_nearest`) or cosine fallback.

        Searches `corrected_contexts` first (converting to SentimentCalibrationResponse) and merges with
        `sentiment_calibrations` so both collections work seamlessly.
        """
        col = self.db.collection("sentiment_calibrations")
        base_query: Any = col
        if project_id:
            base_query = base_query.where("project_id", "==", project_id)
        if group_name:
            base_query = base_query.where("group_name", "==", group_name)

        if hasattr(base_query, "find_nearest"):
            try:
                vector_query = base_query.find_nearest(
                    vector_field="embedding",
                    query_vector=Vector(query_vector),
                    distance_measure=DistanceMeasure.COSINE,
                    limit=limit,
                )
                snaps = list(vector_query.stream())
                if snaps:
                    return [
                        SentimentCalibrationResponse.model_validate(
                            _normalize_vector_field(s.to_dict() or {})
                        )
                        for s in snaps
                    ]
            except Exception:
                pass

        all_calibrations = self.list_calibrations(project_id)
        if group_name:
            all_calibrations = [
                c for c in all_calibrations if c.group_name == group_name
            ]

        # Also check corrected_contexts if sentiment_calibrations was populated directly via corrected_contexts
        corrected_list = self.list_corrected_contexts(
            project_id=project_id, group_name=group_name
        )
        seen_ids = {c.calibration_id for c in all_calibrations}
        for ctx in corrected_list:
            if ctx.correction_id not in seen_ids:
                all_calibrations.append(
                    SentimentCalibrationResponse(
                        calibration_id=ctx.correction_id,
                        project_id=ctx.project_id,
                        group_name=ctx.group_name,
                        dialogue_text=ctx.scrubbed_text,
                        benchmark_score=ctx.human_adjusted_score,
                        rubric_breakdown=ctx.rubric_breakdown,
                        embedding=ctx.embedding,
                        adjudicator_uid=ctx.adjudicator_uid,
                        created_at=ctx.created_at,
                    )
                )

        candidates = [c for c in all_calibrations if c.embedding is not None]
        if not candidates:
            return []

        scored = [
            (c, _cosine_similarity(query_vector, c.embedding))
            for c in candidates
            if c.embedding
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [item[0] for item in scored[:limit]]

