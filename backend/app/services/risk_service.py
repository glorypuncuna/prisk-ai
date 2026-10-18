from datetime import datetime, timedelta, timezone
import json
from typing import Any

from app.core.bigquery import BigQueryAnalyticsClient
from app.core.database import get_firestore_client
from app.core.enums import UserRole
from app.repositories.audit_repository import AuditRepository
from app.repositories.meeting_repository import MeetingRepository
from app.repositories.risk_repository import RiskRepository
from app.schemas.audit import AuditActionType, AuditEntityType, AuditLedgerEntryCreate
from app.schemas.risk import (
    AiMitigationResponse,
    AiRiskDiscoverResponse,
    DiscoveredRiskItem,
    EscalationTier,
    HeatmapCellNode,
    PortfolioRisksAnalyticsResponse,
    RiskCategory,
    RiskRegisterCreate,
    RiskRegisterResponse,
    RiskRegisterUpdate,
    RiskStatus,
    SeverityBand,
    SystemicRiskSpikeStatus,
    compute_severity_band,
)
from app.services.email import (
    send_risk_escalation_email,
    send_systemic_risk_spike_email,
)
from app.services.sentiment_service import get_sentiment_service


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


class RiskService:
    """Enterprise Risk & Mitigation Engine (COSO/ISO 31000 matrix, 24h/48h/72h SLAs, systemic spike detection)."""

    def __init__(self, db: Any | None = None) -> None:
        self.db = db or get_firestore_client()
        self.risk_repo = RiskRepository(db=self.db)
        self.meeting_repo = MeetingRepository(db=self.db)
        self.audit_repo = AuditRepository(db=self.db)
        self.bq_client = BigQueryAnalyticsClient()


    def register_risk(
        self,
        payload: RiskRegisterCreate,
        actor_uid: str,
        actor_role: str | None = None,
    ) -> RiskRegisterResponse:
        """Create a risk record, stream to BigQuery, and log to the immutable audit ledger."""
        created = self.risk_repo.create_risk(payload)
        risk_dict = created.model_dump()
        self.bq_client.stream_portfolio_risk(risk_dict)

        now_iso = datetime.now(timezone.utc).isoformat()
        event_id = f"risk_created_{created.risk_id}_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        audit_entry = AuditLedgerEntryCreate(
            event_id=event_id,
            event_type="RISK_REGISTERED",
            actor_uid=actor_uid,
            target_id=created.risk_id,
            actor_role=actor_role,
            action_type="RISK_REGISTERED",
            entity_type=AuditEntityType.RISK.value,
            metadata={
                "risk_id": created.risk_id,
                "project_id": created.project_id,
                "impact": created.impact,
                "probability": created.probability,
                "severity_score": created.severity_score,
                "severity_band": created.severity_band,
                "category": str(created.category),
                "status": str(created.status),
            },
            new_state_json=json.dumps(risk_dict),
            timestamp=now_iso,
        )
        recorded = self.audit_repo.record_event(audit_entry)
        self.bq_client.stream_audit_ledger_event(recorded.model_dump())
        return created

    def override_or_update_risk(
        self,
        risk_id: str,
        updates: RiskRegisterUpdate | dict[str, Any],
        actor_uid: str,
        actor_role: str | None = None,
    ) -> RiskRegisterResponse:
        """Update or override a risk record, recalculate severity, and append immutable audit state diffs."""
        previous = self.risk_repo.get_risk(risk_id)
        if not previous:
            raise KeyError(f"Risk '{risk_id}' not found")

        prev_dict = previous.model_dump()
        updated = self.risk_repo.update_risk(
            risk_id=risk_id,
            updates=updates,
            actor_uid=actor_uid,
            actor_role=actor_role,
        )
        new_dict = updated.model_dump()
        self.bq_client.stream_portfolio_risk(new_dict)

        now_iso = datetime.now(timezone.utc).isoformat()
        event_id = f"risk_override_{risk_id}_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        audit_entry = AuditLedgerEntryCreate(
            event_id=event_id,
            event_type=AuditActionType.RISK_OVERRIDE.value,
            actor_uid=actor_uid,
            target_id=risk_id,
            actor_role=actor_role,
            action_type=AuditActionType.RISK_OVERRIDE.value,
            entity_type=AuditEntityType.RISK.value,
            metadata={
                "risk_id": risk_id,
                "project_id": updated.project_id,
                "previous_severity_score": previous.severity_score,
                "new_severity_score": updated.severity_score,
                "previous_status": str(previous.status),
                "new_status": str(updated.status),
                "previous_owner_uid": previous.owner_uid,
                "new_owner_uid": updated.owner_uid,
            },
            previous_state_json=json.dumps(prev_dict),
            new_state_json=json.dumps(new_dict),
            timestamp=now_iso,
        )
        recorded = self.audit_repo.record_event(audit_entry)
        self.bq_client.stream_audit_ledger_event(recorded.model_dump())
        return updated

    def evaluate_systemic_risk_spike(
        self,
        risks: list[RiskRegisterResponse] | None = None,
        now: datetime | None = None,
        dispatch_alerts: bool = False,
    ) -> SystemicRiskSpikeStatus:
        """Evaluate Systemic Risk Spike rule (>=3 concurrent critical projects OR >25% 7-day severity surge)."""
        eval_now = now or datetime.now(timezone.utc)
        now_iso = eval_now.isoformat()

        if risks is None:
            risks = self.risk_repo.list_risks()

        active_statuses = {
            RiskStatus.OPEN.value,
            RiskStatus.ESCALATED.value,
            RiskStatus.OPEN,
            RiskStatus.ESCALATED,
        }
        active_risks = [r for r in risks if r.status in active_statuses]

        # Condition 1: >= 3 distinct projects with active Critical risks (severity_score >= 20)
        critical_projects = sorted(
            {
                r.project_id
                for r in active_risks
                if r.severity_score >= 20 and r.project_id
            }
        )
        triggered_by_critical = len(critical_projects) >= 3

        # Condition 2: Portfolio-wide average severity_score increases by > 25% over rolling 7-day window
        window_7d_start = eval_now - timedelta(days=7)
        window_14d_start = eval_now - timedelta(days=14)

        recent_scores: list[int] = []
        prior_scores: list[int] = []

        for r in active_risks:
            created_dt = _parse_iso_datetime(r.created_at)
            if created_dt is None:
                recent_scores.append(r.severity_score)
            elif created_dt >= window_7d_start:
                recent_scores.append(r.severity_score)
            elif created_dt >= window_14d_start:
                prior_scores.append(r.severity_score)
            else:
                prior_scores.append(r.severity_score)

        current_7d_avg = (
            round(sum(recent_scores) / len(recent_scores), 2)
            if recent_scores
            else (
                round(
                    sum(r.severity_score for r in active_risks) / len(active_risks),
                    2,
                )
                if active_risks
                else 0.0
            )
        )
        previous_7d_avg = (
            round(sum(prior_scores) / len(prior_scores), 2)
            if prior_scores
            else 0.0
        )

        velocity_surge_pct = 0.0
        if previous_7d_avg > 0:
            velocity_surge_pct = round(
                ((current_7d_avg - previous_7d_avg) / previous_7d_avg) * 100.0,
                2,
            )

        triggered_by_velocity = velocity_surge_pct > 25.0
        is_active = triggered_by_critical or triggered_by_velocity

        alert_reasons: list[str] = []
        if triggered_by_critical:
            alert_reasons.append(
                f"{len(critical_projects)} projects have concurrent Critical risks (severity >= 20): {', '.join(critical_projects)}"
            )
        if triggered_by_velocity:
            alert_reasons.append(
                f"Portfolio 7-day average severity surged by +{velocity_surge_pct:.1f}% ({previous_7d_avg:.1f} to {current_7d_avg:.1f})"
            )

        alert_message = (
            "Systemic Risk Spike active: " + "; ".join(alert_reasons)
            if alert_reasons
            else None
        )

        status_obj = SystemicRiskSpikeStatus(
            is_active=is_active,
            triggered_by_critical_projects=triggered_by_critical,
            triggered_by_velocity_surge=triggered_by_velocity,
            concurrent_critical_project_count=len(critical_projects),
            concurrent_critical_project_ids=critical_projects,
            current_7d_avg_severity=current_7d_avg,
            previous_7d_avg_severity=previous_7d_avg,
            velocity_surge_pct=velocity_surge_pct,
            evaluated_at=now_iso,
            alert_message=alert_message,
        )

        if is_active and dispatch_alerts:
            spike_dict = status_obj.model_dump()
            self.db.collection("system_alerts").document("systemic_risk_spike").set(
                spike_dict
            )
            send_systemic_risk_spike_email(self.db, spike_dict)
            event_id = f"systemic_risk_spike_{int(eval_now.timestamp() * 1000)}"
            audit_entry = AuditLedgerEntryCreate(
                event_id=event_id,
                event_type="SYSTEMIC_RISK_SPIKE_DETECTED",
                actor_uid="system_scheduler",
                target_id="portfolio",
                actor_role="SYSTEM",
                action_type="SYSTEMIC_RISK_SPIKE_DETECTED",
                entity_type=AuditEntityType.SYSTEM.value,
                metadata=spike_dict,
                timestamp=now_iso,
            )
            recorded = self.audit_repo.record_event(audit_entry)
            self.bq_client.stream_audit_ledger_event(recorded.model_dump())

        return status_obj

    def build_portfolio_risk_analytics(
        self,
        project_id: str | None = None,
        category: str | None = None,
        status: str | None = None,
        allowed_project_ids: set[str] | None = None,
    ) -> PortfolioRisksAnalyticsResponse:
        """Build 5x5 COSO/ISO 31000 heatmap matrix, distribution summaries, and systemic spike status."""
        filtered_risks = self.risk_repo.list_risks(
            project_id=project_id,
            category=category,
            status=status,
            allowed_project_ids=allowed_project_ids,
        )
        all_accessible_risks = self.risk_repo.list_risks(
            allowed_project_ids=allowed_project_ids
        )

        cell_map: dict[tuple[int, int], HeatmapCellNode] = {}
        for imp in range(1, 6):
            for prob in range(1, 6):
                sev = imp * prob
                cell_map[(imp, prob)] = HeatmapCellNode(
                    impact=imp,
                    probability=prob,
                    severity_score=sev,
                    severity_band=compute_severity_band(sev),
                    risk_count=0,
                    risk_ids=[],
                    project_ids=[],
                )

        cat_dist: dict[str, int] = {
            "FINANCIAL": 0,
            "OPERATIONAL": 0,
            "COMPLIANCE": 0,
            "STRATEGIC": 0,
            "RELATIONSHIP": 0,
        }
        proj_map: dict[str, dict[str, Any]] = {}

        crit_count = 0
        high_count = 0
        med_count = 0
        low_count = 0
        open_or_esc_count = 0

        for r in filtered_risks:
            cell = cell_map.get((r.impact, r.probability))
            if cell is not None:
                cell.risk_count += 1
                cell.risk_ids.append(r.risk_id)
                if r.project_id not in cell.project_ids:
                    cell.project_ids.append(r.project_id)

            cat_key = str(r.category)
            cat_dist[cat_key] = cat_dist.get(cat_key, 0) + 1

            if r.severity_band == SeverityBand.CRITICAL.value:
                crit_count += 1
            elif r.severity_band == SeverityBand.HIGH.value:
                high_count += 1
            elif r.severity_band == SeverityBand.MEDIUM.value:
                med_count += 1
            else:
                low_count += 1

            if r.status in (RiskStatus.OPEN, RiskStatus.ESCALATED):
                open_or_esc_count += 1

            p_entry = proj_map.setdefault(
                r.project_id,
                {
                    "project_id": r.project_id,
                    "company_name": r.company_name or "Enterprise Client",
                    "risk_count": 0,
                    "critical_count": 0,
                    "high_count": 0,
                    "max_severity": 0,
                    "avg_severity": 0.0,
                    "_sum_sev": 0,
                },
            )
            p_entry["risk_count"] += 1
            p_entry["_sum_sev"] += r.severity_score
            if r.severity_score > p_entry["max_severity"]:
                p_entry["max_severity"] = r.severity_score
            if r.severity_band == SeverityBand.CRITICAL.value:
                p_entry["critical_count"] += 1
            elif r.severity_band == SeverityBand.HIGH.value:
                p_entry["high_count"] += 1

        project_summaries: list[dict[str, Any]] = []
        for p_id, p_data in sorted(proj_map.items()):
            cnt = p_data["risk_count"]
            p_data["avg_severity"] = (
                round(p_data.pop("_sum_sev") / cnt, 2) if cnt else 0.0
            )
            project_summaries.append(p_data)

        avg_sev = (
            round(
                sum(r.severity_score for r in filtered_risks) / len(filtered_risks),
                2,
            )
            if filtered_risks
            else 0.0
        )

        # Order heatmap cells from Impact 5 down to 1, Probability 1 to 5
        heatmap_cells = [
            cell_map[(imp, prob)]
            for imp in range(5, 0, -1)
            for prob in range(1, 6)
        ]

        spike_status = self.evaluate_systemic_risk_spike(
            risks=all_accessible_risks,
            dispatch_alerts=False,
        )

        return PortfolioRisksAnalyticsResponse(
            total_risks=len(filtered_risks),
            open_or_escalated_count=open_or_esc_count,
            critical_count=crit_count,
            high_count=high_count,
            medium_count=med_count,
            low_count=low_count,
            average_severity_score=avg_sev,
            heatmap_cells=heatmap_cells,
            category_distribution=cat_dist,
            project_summaries=project_summaries,
            systemic_spike=spike_status,
            risks=filtered_risks,
        )

    def _resolve_recipient_emails_for_tier(
        self, risk: RiskRegisterResponse, tier_hours: int
    ) -> list[str]:
        """Resolve email addresses for 24h (Risk Owner), 48h (Project Managers), and 72h (Executives + custom)."""
        emails: list[str] = []
        user_docs: dict[str, dict[str, Any]] = {}
        for snap in self.db.collection("users").stream():
            d = snap.to_dict() or {}
            uid = str(d.get("uid") or snap.id)
            user_docs[uid] = d

        if risk.owner_uid and risk.owner_uid in user_docs:
            owner_email = user_docs[risk.owner_uid].get("email")
            if owner_email:
                emails.append(str(owner_email))
        elif risk.owner_uid and "@" in risk.owner_uid:
            emails.append(risk.owner_uid)

        esc_cfg = risk.escalation_config or {}

        if tier_hours >= 48:
            manager_uids = list(esc_cfg.get("manager_uids", []))
            for m_uid in manager_uids:
                if m_uid in user_docs and user_docs[m_uid].get("email"):
                    e = str(user_docs[m_uid]["email"])
                    if e not in emails:
                        emails.append(e)
            for uid, u_doc in user_docs.items():
                if u_doc.get("role") == UserRole.MANAGER.value:
                    assigned = u_doc.get("assigned_project_ids", [])
                    if risk.project_id in assigned and u_doc.get("email"):
                        e = str(u_doc["email"])
                        if e not in emails:
                            emails.append(e)

        if tier_hours >= 72:
            for uid, u_doc in user_docs.items():
                if u_doc.get("role") in (
                    UserRole.EXECUTIVE.value,
                    UserRole.ADMIN.value,
                ):
                    if u_doc.get("email"):
                        e = str(u_doc["email"])
                        if e not in emails:
                            emails.append(e)
            for custom_email in esc_cfg.get("custom_recipients", []):
                if custom_email and str(custom_email) not in emails:
                    emails.append(str(custom_email))

        if not emails:
            if tier_hours >= 72:
                emails.append("executives@priskai.enterprise.local")
            elif tier_hours >= 48:
                emails.append("managers@priskai.enterprise.local")
            else:
                emails.append("risk-owner@priskai.enterprise.local")

        return emails

    def evaluate_sla_escalations(
        self, reference_time: datetime | None = None
    ) -> dict[str, Any]:
        """Evaluate 24h, 48h, and 72h SLA thresholds on unmitigated High/Critical risks and check Systemic Risk Spike."""
        eval_now = reference_time or datetime.now(timezone.utc)
        now_iso = eval_now.isoformat()

        all_risks = self.risk_repo.list_risks()
        escalated_24h: list[str] = []
        escalated_48h: list[str] = []
        escalated_72h: list[str] = []
        notifications_dispatched = 0

        for risk in all_risks:
            if risk.status != RiskStatus.OPEN:
                continue
            if risk.severity_score < 12:
                continue

            esc_cfg = dict(risk.escalation_config or {})
            if esc_cfg.get("enabled") is False:
                continue

            sla_start_str = esc_cfg.get("sla_started_at") or risk.created_at
            sla_start_dt = _parse_iso_datetime(sla_start_str)
            if sla_start_dt is None:
                continue

            elapsed_hours = (eval_now - sla_start_dt).total_seconds() / 3600.0
            last_tier = int(esc_cfg.get("last_escalated_tier_hours", 0))

            target_tier: int | None = None
            if elapsed_hours >= 72.0 and last_tier < 72:
                target_tier = 72
            elif elapsed_hours >= 48.0 and last_tier < 48:
                target_tier = 48
            elif elapsed_hours >= 24.0 and last_tier < 24:
                target_tier = 24

            if target_tier is None:
                continue

            esc_cfg["last_escalated_tier_hours"] = target_tier
            esc_cfg["last_escalated_at"] = now_iso
            esc_cfg["elapsed_hours"] = round(elapsed_hours, 2)

            updates: dict[str, Any] = {
                "escalation_config": esc_cfg,
                "sla_escalation_tier": f"{target_tier}h",
            }
            if target_tier == 72:
                updates["status"] = RiskStatus.ESCALATED.value

            updated_risk = self.risk_repo.update_risk(risk.risk_id, updates)
            recipients = self._resolve_recipient_emails_for_tier(
                updated_risk, target_tier
            )
            sent = send_risk_escalation_email(
                self.db,
                updated_risk.model_dump(),
                tier_hours=target_tier,
                recipients=recipients,
            )
            notifications_dispatched += len(sent)

            if target_tier == 72:
                escalated_72h.append(risk.risk_id)
            elif target_tier == 48:
                escalated_48h.append(risk.risk_id)
            else:
                escalated_24h.append(risk.risk_id)

            event_type = f"SLA_ESCALATION_{target_tier}H"
            event_id = f"sla_{target_tier}h_{risk.risk_id}_{int(eval_now.timestamp() * 1000)}"
            audit_entry = AuditLedgerEntryCreate(
                event_id=event_id,
                event_type=event_type,
                actor_uid="system_scheduler",
                target_id=risk.risk_id,
                actor_role="SYSTEM",
                action_type=event_type,
                entity_type=AuditEntityType.RISK.value,
                metadata={
                    "risk_id": risk.risk_id,
                    "project_id": risk.project_id,
                    "tier_hours": target_tier,
                    "elapsed_hours": round(elapsed_hours, 2),
                    "severity_score": risk.severity_score,
                    "new_status": str(updated_risk.status),
                    "recipients": recipients,
                },
                timestamp=now_iso,
            )
            recorded = self.audit_repo.record_event(audit_entry)
            self.bq_client.stream_audit_ledger_event(recorded.model_dump())

        refreshed_risks = self.risk_repo.list_risks()
        spike_status = self.evaluate_systemic_risk_spike(
            risks=refreshed_risks,
            now=eval_now,
            dispatch_alerts=True,
        )

        return {
            "evaluated_at": now_iso,
            "total_risks_scanned": len(all_risks),
            "escalated_24h_risk_ids": escalated_24h,
            "escalated_48h_risk_ids": escalated_48h,
            "escalated_72h_risk_ids": escalated_72h,
            "notifications_dispatched": notifications_dispatched,
            "systemic_spike": spike_status.model_dump(),
        }

    def discover_emerging_risks(
        self,
        project_id: str | None = None,
        meeting_id: str | None = None,
        lookback_window: str = "30D",
        auto_register: bool = False,
        actor_uid: str = "system_ai_discovery",
        actor_role: str = "SYSTEM",
    ) -> AiRiskDiscoverResponse:
        """Automated AI Risk Discovery using Gemini 2.5 Flash across pulse drops (>15 pts or <40) and dialogue friction."""
        sentiment_svc = get_sentiment_service(db=self.db)
        meetings_to_scan: list[dict[str, Any]] = []

        if meeting_id:
            mtg = self.meeting_repo.get_meeting(meeting_id)
            if mtg:
                meetings_to_scan.append(mtg.model_dump())
        else:
            snaps = self.db.collection("meetings").stream()
            for s in snaps:
                data = s.to_dict() or {}
                data["meeting_id"] = data.get("meeting_id") or s.id
                m_proj = data.get("project_id", "proj-alpha")
                if project_id and m_proj != project_id:
                    continue
                meetings_to_scan.append(data)

        # Sort chronologically
        meetings_to_scan.sort(key=lambda m: str(m.get("meeting_date", "")))

        # Group meetings by project
        project_meetings: dict[str, list[dict[str, Any]]] = {}
        for m in meetings_to_scan:
            p = str(m.get("project_id", "proj-alpha"))
            project_meetings.setdefault(p, []).append(m)

        detected_drop_events: list[dict[str, Any]] = []

        for p_id, p_mtgs in project_meetings.items():
            prev_group_scores: dict[str, float] = {}
            for m in p_mtgs:
                m_id = str(m.get("meeting_id"))
                m_title = str(m.get("title", f"Meeting {m_id}"))
                m_date = str(m.get("meeting_date", ""))
                overall_pulse = m.get("pulse_score")

                # Parse group breakdown
                group_breakdown = (
                    m.get("group_pulse_scores")
                    or m.get("group_breakdown")
                    or m.get("group_scores")
                    or {}
                )
                curr_group_scores: dict[str, float] = {}
                if isinstance(group_breakdown, dict):
                    for g_name, g_score in group_breakdown.items():
                        try:
                            curr_group_scores[str(g_name)] = float(g_score)
                        except (TypeError, ValueError):
                            continue

                # 1. Check meeting overall pulse < 40
                if overall_pulse is not None and float(overall_pulse) < 40.0:
                    detected_drop_events.append({
                        "project_id": p_id,
                        "meeting_id": m_id,
                        "meeting_title": m_title,
                        "meeting_date": m_date,
                        "trigger_reason": f"Overall meeting pulse fell to {float(overall_pulse):.1f} (below 40.0 critical threshold)",
                        "affected_groups": list(curr_group_scores.keys()) or ["Project Stakeholders"],
                        "severity_weight": 4,
                        "drop_magnitude": round(40.0 - float(overall_pulse), 1),
                    })

                # 2. Check group pulse drops > 15 pts or absolute group pulse < 40
                for g_name, score in curr_group_scores.items():
                    prev_score = prev_group_scores.get(g_name)
                    if prev_score is not None and (prev_score - score) >= 15.0:
                        detected_drop_events.append({
                            "project_id": p_id,
                            "meeting_id": m_id,
                            "meeting_title": m_title,
                            "meeting_date": m_date,
                            "trigger_reason": f"{g_name} pulse dropped by {prev_score - score:.1f} pts (from {prev_score:.1f} to {score:.1f})",
                            "affected_groups": [g_name],
                            "severity_weight": 4 if (prev_score - score) >= 20.0 or score < 40.0 else 3,
                            "drop_magnitude": round(prev_score - score, 1),
                        })
                    elif score < 40.0:
                        detected_drop_events.append({
                            "project_id": p_id,
                            "meeting_id": m_id,
                            "meeting_title": m_title,
                            "meeting_date": m_date,
                            "trigger_reason": f"{g_name} sentiment at critical friction level ({score:.1f} < 40.0)",
                            "affected_groups": [g_name],
                            "severity_weight": 4,
                            "drop_magnitude": round(40.0 - score, 1),
                        })

                # Update running group scores for consecutive comparison
                if curr_group_scores:
                    prev_group_scores = curr_group_scores

        # Deduplicate events by meeting_id and trigger_reason
        seen_keys: set[str] = set()
        unique_events: list[dict[str, Any]] = []
        for ev in detected_drop_events:
            k = f"{ev['project_id']}:{ev['meeting_id']}:{ev['trigger_reason']}"
            if k not in seen_keys:
                seen_keys.add(k)
                unique_events.append(ev)

        discovered_risks: list[DiscoveredRiskItem] = []
        registered_count = 0

        for ev in unique_events:
            m_id = ev["meeting_id"]
            p_id = ev["project_id"]
            m_title = ev["meeting_title"]
            m_date = ev["meeting_date"]
            trigger = ev["trigger_reason"]
            groups = ev["affected_groups"]
            base_sev = ev["severity_weight"]

            # Collect dialogue blocks for verbatim-free synthesis context
            blocks = self.meeting_repo.list_dialogue_blocks(m_id)
            dialogue_excerpts = [
                b.text_scrubbed for b in blocks if b.text_scrubbed
            ][:6]
            excerpts_text = "\n".join(f"- {txt}" for txt in dialogue_excerpts) if dialogue_excerpts else "No transcript blocks logged."

            # Attempt Gemini 2.5 Flash synthesis
            title: str | None = None
            category_val: RiskCategory = RiskCategory.OPERATIONAL
            impact_val = base_sev
            prob_val = base_sev
            desc_val: str | None = None
            mitigation_val: str | None = None
            exec_brief_val: str | None = None

            if sentiment_svc._client is not None:
                try:
                    prompt = f"""You are an enterprise risk officer and COSO/ISO 31000 certified risk manager.
Analyze the following meeting pulse drop event:
Project ID: {p_id}
Meeting: {m_title} ({m_date})
Pulse Drop Trigger: {trigger}
Affected Stakeholder Groups: {', '.join(groups)}
Recent Dialogue Signals:
{excerpts_text}

Generate a concise, professional risk assessment JSON object with these exact keys:
{{
  "title": "Concise risk title (under 80 chars)",
  "category": "OPERATIONAL" | "FINANCIAL" | "COMPLIANCE" | "STRATEGIC" | "RELATIONSHIP",
  "impact": 1 to 5 integer,
  "probability": 1 to 5 integer,
  "description": "2-3 sentences explaining root causes and specific project delivery impact",
  "mitigation_strategy": "Concrete proactive mitigation steps with owners and immediate milestones",
  "executive_brief": "Executive escalation brief suitable for steering committee and C-suite"
}}
Output strictly valid JSON only."""
                    response = sentiment_svc._client.models.generate_content(
                        model=sentiment_svc.settings.gemini_model_name,
                        contents=prompt,
                    )
                    raw_text = getattr(response, "text", "") or ""
                    clean_json = raw_text.strip()
                    if clean_json.startswith("```"):
                        clean_json = clean_json.strip("`")
                        if clean_json.startswith("json"):
                            clean_json = clean_json[4:].strip()
                    parsed = json.loads(clean_json)
                    title = parsed.get("title")
                    cat_candidate = str(parsed.get("category", "OPERATIONAL")).upper()
                    if cat_candidate in RiskCategory.__members__:
                        category_val = RiskCategory[cat_candidate]
                    impact_val = max(1, min(5, int(parsed.get("impact", base_sev))))
                    prob_val = max(1, min(5, int(parsed.get("probability", base_sev))))
                    desc_val = parsed.get("description")
                    mitigation_val = parsed.get("mitigation_strategy")
                    exec_brief_val = parsed.get("executive_brief")
                except Exception:
                    pass

            # Fallback deterministic synthesis
            primary_group = groups[0] if groups else "Stakeholders"
            if not title:
                if any(k in primary_group.upper() for k in ("VENDOR", "BUYER", "CLIENT", "PARTNER")):
                    category_val = RiskCategory.RELATIONSHIP
                    title = f"Stakeholder Friction & Trust Erosion: {primary_group}"
                elif any(k in primary_group.upper() for k in ("FINANCE", "BUDGET", "EXEC")):
                    category_val = RiskCategory.FINANCIAL
                    title = f"Budget & Commercial Alignment Risk: {primary_group}"
                elif any(k in primary_group.upper() for k in ("LEGAL", "COMPLIANCE", "SECURITY")):
                    category_val = RiskCategory.COMPLIANCE
                    title = f"Regulatory & Compliance Assurance Friction: {primary_group}"
                else:
                    category_val = RiskCategory.OPERATIONAL
                    title = f"Operational Delivery Milestone Risk: {primary_group}"

            if not desc_val:
                desc_val = (
                    f"Longitudinal AI pulse tracking detected a severe sentiment shift during '{m_title}'. "
                    f"Triggered by: {trigger}. Friction within {', '.join(groups)} indicates misalignment "
                    f"on deliverables and delivery expectations requiring prompt intervention."
                )

            if not mitigation_val:
                mitigation_val = (
                    f"1. Convene a dedicated alignment session between {', '.join(groups)} within 48h.\n"
                    f"2. Re-validate baseline assumptions, scope boundaries, and delivery dependencies.\n"
                    f"3. Establish weekly milestone burndown checkpoints with designated risk owners."
                )

            if not exec_brief_val:
                exec_brief_val = (
                    f"Executive Escalation Brief: Project '{p_id}' registered a notable pulse drop in '{m_title}' "
                    f"({trigger}). Immediate leadership engagement is advised to safeguard project schedule and contract health."
                )

            sev_score = impact_val * prob_val
            sev_band = compute_severity_band(sev_score)

            item = DiscoveredRiskItem(
                project_id=p_id,
                meeting_id=m_id,
                title=title,
                description=desc_val,
                category=category_val,
                impact=impact_val,
                probability=prob_val,
                severity_score=sev_score,
                severity_band=sev_band,
                trigger_reason=trigger,
                mitigation_strategy=mitigation_val,
                executive_brief=exec_brief_val,
                associated_groups=groups,
                status=RiskStatus.OPEN if auto_register else RiskStatus.DRAFT_PENDING_ADJUDICATION,
            )

            if auto_register:
                reg_payload = RiskRegisterCreate(
                    project_id=p_id,
                    meeting_id=m_id,
                    title=item.title,
                    description=item.description,
                    category=item.category,
                    impact=item.impact,
                    probability=item.probability,
                    status=RiskStatus.OPEN,
                    associated_groups=item.associated_groups,
                    mitigation_plan={
                        "mitigation_strategy": item.mitigation_strategy,
                        "executive_escalation_brief": item.executive_brief,
                        "suggested_action_items": [
                            {"action": f"Convene realignment session with {primary_group}", "owner_role": "Risk Owner", "timeline": "24h SLA", "status": "PENDING"},
                            {"action": "Publish revised milestone roadmap", "owner_role": "Project Manager", "timeline": "48h SLA", "status": "PENDING"},
                        ],
                    },
                )
                created_risk = self.register_risk(
                    payload=reg_payload,
                    actor_uid=actor_uid,
                    actor_role=actor_role,
                )
                item.risk_id = created_risk.risk_id
                item.status = created_risk.status
                registered_count += 1

            discovered_risks.append(item)

        summary_msg = (
            f"Evaluated {len(meetings_to_scan)} meeting(s). Identified {len(unique_events)} pulse drop event(s) "
            f"yielding {len(discovered_risks)} discovered risk(s) ({registered_count} auto-registered)."
        )

        return AiRiskDiscoverResponse(
            project_id=project_id,
            discovered_risks=discovered_risks,
            pulse_drops_evaluated=len(unique_events),
            total_risks_found=len(discovered_risks),
            registered_count=registered_count,
            summary=summary_msg,
        )

    def synthesize_ai_mitigation(
        self,
        risk_id: str,
        apply_to_risk: bool = False,
        context_notes: str | None = None,
        actor_uid: str = "system_mitigation_synth",
        actor_role: str = "SYSTEM",
    ) -> AiMitigationResponse:
        """Synthesize proactive mitigation strategy and executive escalation brief using Gemini 2.5 Flash."""
        risk = self.risk_repo.get_risk(risk_id)
        if not risk:
            raise KeyError(f"Risk '{risk_id}' not found")

        sentiment_svc = get_sentiment_service(db=self.db)
        category_name = str(risk.category.value if hasattr(risk.category, "value") else risk.category)
        groups_str = ", ".join(risk.associated_groups) if risk.associated_groups else "Organizational Group"

        # Check source meeting title if available
        meeting_title = "Adjudicated Golden Record Meeting"
        if risk.meeting_id:
            mtg = self.meeting_repo.get_meeting(risk.meeting_id)
            if mtg:
                meeting_title = mtg.title

        strategy: str | None = None
        action_items: list[dict[str, Any]] = []
        exec_brief: str | None = None
        res_impact = max(1, risk.impact - 1)
        res_prob = max(1, risk.probability - 1)

        if sentiment_svc._client is not None:
            try:
                prompt = f"""You are an enterprise risk mitigation officer and executive advisor.
Formulate a proactive mitigation plan and C-suite escalation brief for this COSO/ISO 31000 risk:
Risk ID: {risk.risk_id}
Title: {risk.title}
Category: {category_name}
Initial Impact: {risk.impact}/5, Initial Probability: {risk.probability}/5 (Severity: {risk.severity_score})
Associated Groups: {groups_str}
Source Meeting: {meeting_title}
Description: {risk.description}
Additional Context: {context_notes or 'None provided.'}

Generate a JSON object with these exact keys:
{{
  "mitigation_strategy": "Multi-phase actionable mitigation strategy with immediate controls and governance gates",
  "suggested_action_items": [
    {{"action": "Actionable task description", "owner_role": "Risk Owner | Project Manager | Lead Architect", "timeline": "24h SLA | 48h SLA | 72h SLA", "status": "PROPOSED"}}
  ],
  "executive_escalation_brief": "2-3 paragraph executive treatment summary explaining exposure, risk appetite, and leadership decisions required",
  "residual_impact": 1 to 5 integer (expected post-mitigation impact),
  "residual_probability": 1 to 5 integer (expected post-mitigation probability)
}}
Output strictly valid JSON only."""
                response = sentiment_svc._client.models.generate_content(
                    model=sentiment_svc.settings.gemini_model_name,
                    contents=prompt,
                )
                raw_text = getattr(response, "text", "") or ""
                clean_json = raw_text.strip()
                if clean_json.startswith("```"):
                    clean_json = clean_json.strip("`")
                    if clean_json.startswith("json"):
                        clean_json = clean_json[4:].strip()
                parsed = json.loads(clean_json)
                strategy = parsed.get("mitigation_strategy")
                action_items = list(parsed.get("suggested_action_items") or [])
                exec_brief = parsed.get("executive_escalation_brief")
                res_impact = max(1, min(5, int(parsed.get("residual_impact", res_impact))))
                res_prob = max(1, min(5, int(parsed.get("residual_probability", res_prob))))
            except Exception:
                pass

        if not strategy:
            strategy = (
                f"1. Establish an immediate rapid-response alignment session between designated risk owners and {groups_str}.\n"
                f"2. Audit all dependent deliverables, contractual milestones, and technical blockers.\n"
                f"3. Institute bi-weekly pulse check-ins and structured sign-off criteria before subsequent milestones.\n"
                f"4. Integrate continuous monitoring into the project's executive steering committee dashboard."
            )

        if not action_items:
            action_items = [
                {
                    "action": f"Convene 30-minute alignment standup with {groups_str} leads",
                    "owner_role": "Risk Owner",
                    "timeline": "24h SLA",
                    "status": "PROPOSED",
                },
                {
                    "action": "Publish revised milestone mitigation brief to steering committee",
                    "owner_role": "Project Manager",
                    "timeline": "48h SLA",
                    "status": "PROPOSED",
                },
                {
                    "action": "Conduct validation review and confirm pulse sentiment stabilization",
                    "owner_role": "Adjudicator",
                    "timeline": "72h SLA",
                    "status": "PROPOSED",
                },
            ]

        if not exec_brief:
            exec_brief = (
                f"Executive Escalation Brief for {risk.title} ({risk.risk_id}): Under COSO/ISO 31000 standards, "
                f"this risk presents an initial severity score of {risk.severity_score} ({risk.severity_band}). "
                f"Root drivers point to delivery hesitation within {groups_str}. Execution of the prescribed "
                f"24h/48h/72h SLA action items is projected to reduce exposure to a residual severity score of "
                f"{res_impact * res_prob} (Impact {res_impact}, Probability {res_prob}), well within organizational risk tolerance."
            )

        res_sev = res_impact * res_prob
        updated_risk_resp: RiskRegisterResponse | None = None

        if apply_to_risk:
            mitigation_payload = {
                "mitigation_strategy": strategy,
                "suggested_action_items": action_items,
                "executive_escalation_brief": exec_brief,
                "residual_impact": res_impact,
                "residual_probability": res_prob,
                "residual_severity_score": res_sev,
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "applied_by_uid": actor_uid,
                "applied_by_role": actor_role,
            }
            comment_text = f"AI Proactive Mitigation Strategy synthesized and applied by {actor_role} ({actor_uid})."
            updates = RiskRegisterUpdate(
                mitigation_plan=mitigation_payload,
                comment=comment_text,
            )
            updated_risk_resp = self.override_or_update_risk(
                risk_id=risk_id,
                updates=updates,
                actor_uid=actor_uid,
                actor_role=actor_role,
            )

        return AiMitigationResponse(
            risk_id=risk.risk_id,
            project_id=risk.project_id,
            title=risk.title,
            mitigation_strategy=strategy,
            suggested_action_items=action_items,
            executive_escalation_brief=exec_brief,
            residual_impact=res_impact,
            residual_probability=res_prob,
            residual_severity_score=res_sev,
            applied=apply_to_risk,
            updated_risk=updated_risk_resp,
        )


def get_risk_service(db: Any | None = None) -> RiskService:

    return RiskService(db=db)
