from datetime import datetime, timezone
from typing import Any

from app.core.database import get_firestore_client
from app.schemas.risk import (
    RiskRegisterCreate,
    RiskRegisterResponse,
    RiskRegisterUpdate,
    RiskStatus,
    compute_severity_band,
    compute_sla_tier,
)


class RiskRepository:
    """Firestore repository for `risk_register` collection."""

    def __init__(self, db: Any | None = None) -> None:
        self.db = db or get_firestore_client()

    def create_risk(self, risk: RiskRegisterCreate) -> RiskRegisterResponse:
        data = risk.model_dump(exclude={"impact_score", "probability_score", "risk_owner_uid"})
        risk_id = str(data["risk_id"])
        self.db.collection("risk_register").document(risk_id).set(data)
        return RiskRegisterResponse.model_validate(data)

    def get_risk(self, risk_id: str) -> RiskRegisterResponse | None:
        doc = self.db.collection("risk_register").document(risk_id).get()
        if not doc.exists:
            return None
        raw = doc.to_dict() or {}
        raw["risk_id"] = raw.get("risk_id") or doc.id
        return RiskRegisterResponse.model_validate(raw)

    def list_risks(
        self,
        project_id: str | None = None,
        status: str | None = None,
        category: str | None = None,
        severity_band: str | None = None,
        impact: int | None = None,
        probability: int | None = None,
        allowed_project_ids: set[str] | None = None,
    ) -> list[RiskRegisterResponse]:
        col = self.db.collection("risk_register")
        snaps = col.stream()
        results: list[RiskRegisterResponse] = []
        for s in snaps:
            data = s.to_dict() or {}
            data["risk_id"] = data.get("risk_id") or s.id
            proj = str(data.get("project_id", ""))
            if allowed_project_ids is not None and proj not in allowed_project_ids:
                continue
            if project_id and proj != project_id:
                continue
            if status and data.get("status") != status:
                continue
            if category and data.get("category") != category:
                continue
            item = RiskRegisterResponse.model_validate(data)
            if severity_band and item.severity_band != severity_band:
                continue
            if impact is not None and item.impact != impact:
                continue
            if probability is not None and item.probability != probability:
                continue
            results.append(item)
        results.sort(
            key=lambda r: (r.severity_score, r.updated_at or ""),
            reverse=True,
        )
        return results

    def update_risk(
        self,
        risk_id: str,
        updates: RiskRegisterUpdate | dict[str, Any],
        actor_uid: str | None = None,
        actor_role: str | None = None,
    ) -> RiskRegisterResponse:
        existing = self.get_risk(risk_id)
        if not existing:
            raise KeyError(f"Risk '{risk_id}' not found")

        update_dict = (
            updates.model_dump(exclude_unset=True)
            if isinstance(updates, RiskRegisterUpdate)
            else dict(updates)
        )

        if "impact_score" in update_dict and update_dict["impact_score"] is not None:
            update_dict["impact"] = update_dict.pop("impact_score")
        else:
            update_dict.pop("impact_score", None)

        if "probability_score" in update_dict and update_dict["probability_score"] is not None:
            update_dict["probability"] = update_dict.pop("probability_score")
        else:
            update_dict.pop("probability_score", None)

        if "risk_owner_uid" in update_dict and update_dict["risk_owner_uid"] is not None:
            update_dict["owner_uid"] = update_dict.pop("risk_owner_uid")
        else:
            update_dict.pop("risk_owner_uid", None)

        now_iso = datetime.now(timezone.utc).isoformat()

        comment_text = update_dict.pop("comment", None)
        if comment_text and str(comment_text).strip():
            comments = list(existing.qualitative_commentary or [])
            comments.append(
                {
                    "comment_id": f"cmt-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
                    "author_uid": actor_uid or "system",
                    "author_role": actor_role,
                    "comment": str(comment_text).strip(),
                    "created_at": now_iso,
                }
            )
            update_dict["qualitative_commentary"] = comments

        escalation_enabled = update_dict.pop("escalation_enabled", None)
        esc_cfg = dict(existing.escalation_config or {})
        if escalation_enabled is not None:
            esc_cfg["enabled"] = bool(escalation_enabled)
        if "escalation_config" in update_dict and isinstance(update_dict["escalation_config"], dict):
            esc_cfg.update(update_dict["escalation_config"])

        new_status = update_dict.get("status")
        if new_status == RiskStatus.OPEN.value or new_status == RiskStatus.OPEN:
            if not esc_cfg.get("sla_started_at"):
                esc_cfg["sla_started_at"] = now_iso
            if "enabled" not in esc_cfg:
                esc_cfg["enabled"] = True
            if "last_escalated_tier_hours" not in esc_cfg:
                esc_cfg["last_escalated_tier_hours"] = 0

        if esc_cfg:
            update_dict["escalation_config"] = esc_cfg

        impact = int(update_dict.get("impact", existing.impact))
        prob = int(update_dict.get("probability", existing.probability))
        if "impact" in update_dict or "probability" in update_dict:
            sev = impact * prob
            update_dict["severity_score"] = sev
            update_dict["severity_band"] = compute_severity_band(sev)
            if "sla_escalation_tier" not in update_dict:
                update_dict["sla_escalation_tier"] = compute_sla_tier(sev)

        update_dict["updated_at"] = now_iso
        self.db.collection("risk_register").document(risk_id).set(
            update_dict, merge=True
        )
        updated = self.get_risk(risk_id)
        if not updated:
            raise KeyError(f"Risk '{risk_id}' not found after update")
        return updated

    def delete_risk(self, risk_id: str) -> bool:
        self.db.collection("risk_register").document(risk_id).delete()
        return True
