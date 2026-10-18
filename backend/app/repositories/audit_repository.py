from datetime import datetime, timezone
from typing import Any

from app.core.database import get_firestore_client
from app.schemas.audit import (
    AuditLedgerEntryCreate,
    AuditLedgerEntryResponse,
)


class AuditRepository:
    """Firestore repository for immutable `audit_ledger` collection."""

    def __init__(self, db: Any | None = None) -> None:
        self.db = db or get_firestore_client()

    def record_event(
        self, event: AuditLedgerEntryCreate
    ) -> AuditLedgerEntryResponse:
        data = event.model_dump()
        self.db.collection("audit_ledger").document(event.event_id).set(data)
        return AuditLedgerEntryResponse.model_validate(data)

    def log(
        self,
        event_type: str,
        actor_uid: str,
        target_id: str,
        metadata: dict[str, Any] | None = None,
        actor_role: str | None = None,
        action_type: str | None = None,
        entity_type: str | None = None,
        sha256_hash: str | None = None,
    ) -> AuditLedgerEntryResponse:
        timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        event_id = f"{event_type.lower()}_{target_id}_{timestamp_ms}"
        entry = AuditLedgerEntryCreate(
            event_id=event_id,
            event_type=event_type,
            actor_uid=actor_uid,
            target_id=target_id,
            actor_role=actor_role,
            action_type=action_type,
            entity_type=entity_type,
            metadata=metadata or {},
            sha256_hash=sha256_hash,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        return self.record_event(entry)

    def list_events(
        self, target_id: str | None = None, event_type: str | None = None
    ) -> list[AuditLedgerEntryResponse]:
        col = self.db.collection("audit_ledger")
        snaps = col.stream()
        results: list[AuditLedgerEntryResponse] = []
        for s in snaps:
            data = s.to_dict() or {}
            if target_id and data.get("target_id") != target_id:
                continue
            if event_type and data.get("event_type") != event_type:
                continue
            results.append(AuditLedgerEntryResponse.model_validate(data))
        results.sort(key=lambda e: e.timestamp, reverse=True)
        return results
