from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings
from app.core.enums import UserRole

# Outbox log for inspecting sent email notifications in local dev and automated tests
_sent_emails: list[dict[str, Any]] = []


def get_sent_emails() -> list[dict[str, Any]]:
    """Return a copy of all dispatched email notifications."""
    return list(_sent_emails)


def clear_sent_emails() -> None:
    """Clear the email outbox (for test isolation)."""
    _sent_emails.clear()


def notify_managers_of_new_registration(
    db: Any,
    user_profile: dict[str, Any],
) -> list[dict[str, Any]]:
    """Dispatch an email notification alert to all `MANAGER` and `EXECUTIVE` accounts
    when a new user completes registration in the default `EXTERNAL_STAKEHOLDER` quarantine state.
    """
    settings = get_settings()
    recipient_emails: list[str] = []

    for snap in db.collection("users").stream():
        doc = snap.to_dict() or {}
        if doc.get("role") in {UserRole.MANAGER.value, UserRole.EXECUTIVE.value}:
            email = doc.get("email")
            if email and email not in recipient_emails:
                recipient_emails.append(str(email))

    # Always include a default enterprise manager alert address if no managers are seeded yet
    if not recipient_emails:
        recipient_emails.append("managers@priskai.enterprise.local")

    now_iso = datetime.now(timezone.utc).isoformat()
    dispatched: list[dict[str, Any]] = []
    for recipient in recipient_emails:
        email_record: dict[str, Any] = {
            "type": "NEW_USER_REGISTRATION_ALERT",
            "from": settings.smtp_from_email,
            "to": recipient,
            "subject": (
                f"[pRiskAI] New User Registration Pending Project Invitation: "
                f"{user_profile['first_name']} {user_profile['last_name']}"
            ),
            "body": (
                f"User {user_profile['first_name']} {user_profile['last_name']} "
                f"({user_profile['email']}, {user_profile['phone_number']}) has registered with "
                f"default role {user_profile['role']}. Issue a Project Invitation or elevate their "
                f"role to grant project workspace access."
            ),
            "target_uid": user_profile["uid"],
            "sent_at": now_iso,
        }
        _sent_emails.append(email_record)
        db.collection("email_notifications").document(
            f"reg_alert_{user_profile['uid']}_{recipient}"
        ).set(email_record)
        dispatched.append(email_record)

    return dispatched


def send_project_invitation_email(
    db: Any,
    invitation: dict[str, Any],
    project_name: str,
) -> dict[str, Any]:
    """Dispatch an email notification when a user is invited to a project."""
    settings = get_settings()
    now_iso = datetime.now(timezone.utc).isoformat()
    email_record: dict[str, Any] = {
        "type": "PROJECT_INVITATION",
        "from": settings.smtp_from_email,
        "to": invitation["invitee_email"],
        "subject": f"[pRiskAI] Invitation to Project: {project_name}",
        "body": (
            f"You have been invited to join project '{project_name}' ({invitation['project_id']}) "
            f"by {invitation['invited_by_uid']}. Accept this invitation in your pRiskAI dashboard."
        ),
        "invitation_id": invitation["invitation_id"],
        "project_id": invitation["project_id"],
        "sent_at": now_iso,
    }
    _sent_emails.append(email_record)
    db.collection("email_notifications").document(
        f"proj_invite_{invitation['invitation_id']}"
    ).set(email_record)
    return email_record


def send_risk_escalation_email(
    db: Any,
    risk: dict[str, Any],
    tier_hours: int,
    recipients: list[str],
) -> list[dict[str, Any]]:
    """Dispatch SLA escalation emails (24h, 48h, or 72h) to designated recipients."""
    settings = get_settings()
    now_iso = datetime.now(timezone.utc).isoformat()
    dispatched: list[dict[str, Any]] = []
    risk_id = str(risk.get("risk_id", "RSK-UNKNOWN"))
    project_id = str(risk.get("project_id", "proj-alpha"))
    title = str(risk.get("title", "Unmitigated Risk"))
    sev = int(risk.get("severity_score", 12))

    if not recipients:
        recipients = ["risk-owners@priskai.enterprise.local"]

    for recipient in recipients:
        email_record: dict[str, Any] = {
            "type": f"RISK_SLA_ESCALATION_{tier_hours}H",
            "from": settings.smtp_from_email,
            "to": recipient,
            "subject": (
                f"[pRiskAI {tier_hours}h SLA Escalation] Risk {risk_id} ({title}) "
                f"- Severity {sev}/25"
            ),
            "body": (
                f"Risk {risk_id} ('{title}') in project '{project_id}' has remained unmitigated "
                f"beyond the {tier_hours}-hour SLA threshold (Severity Index: {sev}/25). "
                f"Immediate review and mitigation action is required."
            ),
            "risk_id": risk_id,
            "project_id": project_id,
            "tier_hours": tier_hours,
            "sent_at": now_iso,
        }
        _sent_emails.append(email_record)
        doc_id = f"sla_{tier_hours}h_{risk_id}_{recipient}_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        db.collection("email_notifications").document(doc_id).set(email_record)
        dispatched.append(email_record)

    return dispatched


def send_systemic_risk_spike_email(
    db: Any,
    spike_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    """Dispatch urgent portfolio systemic risk spike alerts to Executive and Risk Manager users."""
    settings = get_settings()
    now_iso = datetime.now(timezone.utc).isoformat()
    recipient_emails: list[str] = []

    for snap in db.collection("users").stream():
        doc = snap.to_dict() or {}
        if doc.get("role") in {
            UserRole.EXECUTIVE.value,
            UserRole.ADMIN.value,
            UserRole.MANAGER.value,
        }:
            email = doc.get("email")
            if email and str(email) not in recipient_emails:
                recipient_emails.append(str(email))

    if not recipient_emails:
        recipient_emails.append("executives@priskai.enterprise.local")

    dispatched: list[dict[str, Any]] = []
    crit_projects = spike_summary.get("concurrent_critical_project_ids", [])
    surge_pct = spike_summary.get("velocity_surge_pct", 0.0)
    alert_msg = spike_summary.get(
        "alert_message", "Systemic portfolio risk threshold exceeded."
    )

    for recipient in recipient_emails:
        email_record: dict[str, Any] = {
            "type": "SYSTEMIC_RISK_SPIKE_EXECUTIVE_ALERT",
            "from": settings.smtp_from_email,
            "to": recipient,
            "subject": "[pRiskAI Executive Alert] Systemic Portfolio Risk Spike Detected",
            "body": (
                f"{alert_msg} Concurrent Critical Projects: {len(crit_projects)} "
                f"({', '.join(crit_projects) if crit_projects else 'none'}). "
                f"7-Day Severity Velocity Change: {surge_pct:+.1f}%."
            ),
            "concurrent_critical_project_ids": crit_projects,
            "velocity_surge_pct": surge_pct,
            "sent_at": now_iso,
        }
        _sent_emails.append(email_record)
        doc_id = f"spike_alert_{recipient}_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        db.collection("email_notifications").document(doc_id).set(email_record)
        dispatched.append(email_record)

    return dispatched

