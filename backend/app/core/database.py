from copy import deepcopy
from datetime import datetime, timezone
import os
from typing import Any

from app.core.config import get_settings


class InMemoryDocumentSnapshot:
    """In-memory equivalent of a Firestore DocumentSnapshot."""

    def __init__(self, doc_id: str, data: dict[str, Any] | None) -> None:
        self.id = doc_id
        self._data = deepcopy(data) if data is not None else None

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> dict[str, Any] | None:
        return deepcopy(self._data) if self._data is not None else None


class InMemoryDocumentReference:
    """In-memory equivalent of a Firestore DocumentReference."""

    def __init__(
        self,
        collection_store: dict[str, dict[str, Any]],
        doc_id: str,
        client: "InMemoryFirestoreClient | None" = None,
        collection_path: str = "",
    ) -> None:
        self._collection_store = collection_store
        self.id = doc_id
        self._client = client
        self._collection_path = collection_path

    def get(self) -> InMemoryDocumentSnapshot:
        return InMemoryDocumentSnapshot(self.id, self._collection_store.get(self.id))

    def set(self, data: dict[str, Any], merge: bool = False) -> None:
        if merge and self.id in self._collection_store:
            merged = deepcopy(self._collection_store[self.id])
            merged.update(deepcopy(data))
            self._collection_store[self.id] = merged
        else:
            self._collection_store[self.id] = deepcopy(data)

    def update(self, data: dict[str, Any]) -> None:
        if self.id not in self._collection_store:
            raise KeyError(f"Document '{self.id}' does not exist")
        updated = deepcopy(self._collection_store[self.id])
        updated.update(deepcopy(data))
        self._collection_store[self.id] = updated

    def delete(self) -> None:
        self._collection_store.pop(self.id, None)

    def collection(self, name: str) -> "InMemoryCollectionReference":
        if self._client is None:
            raise RuntimeError("InMemoryDocumentReference initialized without client reference")
        sub_path = f"{self._collection_path}/{self.id}/{name}"
        return self._client.collection(sub_path)


class InMemoryCollectionReference:
    """In-memory equivalent of a Firestore CollectionReference."""

    def __init__(
        self,
        collection_store: dict[str, dict[str, Any]],
        client: "InMemoryFirestoreClient | None" = None,
        collection_path: str = "",
    ) -> None:
        self._collection_store = collection_store
        self._client = client
        self._collection_path = collection_path
        self.id = collection_path.split("/")[-1] if collection_path else ""

    def document(self, doc_id: str) -> InMemoryDocumentReference:
        return InMemoryDocumentReference(
            self._collection_store,
            doc_id,
            client=self._client,
            collection_path=self._collection_path,
        )

    def stream(self) -> list[InMemoryDocumentSnapshot]:
        return [
            InMemoryDocumentSnapshot(doc_id, data)
            for doc_id, data in self._collection_store.items()
        ]

    def where(self, field: str, op: str, value: Any) -> "InMemoryQuery":
        return InMemoryQuery(self.stream()).where(field, op, value)

    def limit(self, count: int) -> "InMemoryQuery":
        return InMemoryQuery(self.stream()).limit(count)

    def find_nearest(
        self,
        vector_field: str,
        query_vector: Any,
        distance_measure: Any = None,
        limit: int = 5,
    ) -> "InMemoryQuery":
        return InMemoryQuery(self.stream()).find_nearest(
            vector_field=vector_field,
            query_vector=query_vector,
            distance_measure=distance_measure,
            limit=limit,
        )


def _compute_cosine_similarity(v1: list[float], v2: list[float]) -> float:
    import math

    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    if n1 == 0 or n2 == 0:
        return 0.0
    return dot / (n1 * n2)


class InMemoryQuery:
    """Simple query filter over in-memory snapshots."""

    def __init__(self, snapshots: list[InMemoryDocumentSnapshot]) -> None:
        self._snapshots = snapshots

    def where(self, field: str, op: str, value: Any) -> "InMemoryQuery":
        filtered: list[InMemoryDocumentSnapshot] = []
        for snap in self._snapshots:
            doc = snap.to_dict() or {}
            field_val = doc.get(field)
            if op == "==" and field_val == value:
                filtered.append(snap)
            elif op == "in" and isinstance(value, list) and field_val in value:
                filtered.append(snap)
            elif op == "array_contains" and isinstance(field_val, list) and value in field_val:
                filtered.append(snap)
        return InMemoryQuery(filtered)

    def limit(self, count: int) -> "InMemoryQuery":
        return InMemoryQuery(self._snapshots[:count])

    def find_nearest(
        self,
        vector_field: str,
        query_vector: Any,
        distance_measure: Any = None,
        limit: int = 5,
    ) -> "InMemoryQuery":
        q_vec = list(query_vector) if hasattr(query_vector, "__iter__") else []
        scored: list[tuple[InMemoryDocumentSnapshot, float]] = []
        for snap in self._snapshots:
            doc = snap.to_dict() or {}
            emb = doc.get(vector_field)
            if emb is None:
                continue
            emb_list = list(emb) if hasattr(emb, "__iter__") else []
            if not emb_list or not q_vec:
                continue
            sim = _compute_cosine_similarity(q_vec, emb_list)
            scored.append((snap, sim))
        scored.sort(key=lambda item: item[1], reverse=True)
        return InMemoryQuery([item[0] for item in scored[:limit]])

    def stream(self) -> list[InMemoryDocumentSnapshot]:
        return list(self._snapshots)

    def get(self) -> list[InMemoryDocumentSnapshot]:
        return list(self._snapshots)


class InMemoryBatch:
    """In-memory WriteBatch mimicking Google Cloud Firestore batch operations."""

    def __init__(self) -> None:
        self._operations: list[tuple[Any, dict[str, Any], bool]] = []

    def set(self, doc_ref: Any, data: dict[str, Any], merge: bool = False) -> None:
        self._operations.append((doc_ref, data, merge))

    def commit(self) -> None:
        for doc_ref, data, merge in self._operations:
            doc_ref.set(data, merge=merge)
        self._operations.clear()


class InMemoryFirestoreClient:
    """In-memory Firestore client for local development and tests."""

    def __init__(self) -> None:
        self._collections: dict[str, dict[str, dict[str, Any]]] = {}

    def collection(self, name: str) -> InMemoryCollectionReference:
        if name not in self._collections:
            self._collections[name] = {}
        return InMemoryCollectionReference(
            self._collections[name], client=self, collection_path=name
        )

    def collections(self) -> list[InMemoryCollectionReference]:
        """Return all top-level collection references."""
        return [
            self.collection(k)
            for k in self._collections.keys()
            if "/" not in k
        ]

    def batch(self) -> InMemoryBatch:
        """Return an in-memory batch write instance."""
        return InMemoryBatch()

    def clear(self) -> None:
        self._collections.clear()


_in_memory_db = InMemoryFirestoreClient()


def get_firestore_client() -> Any:
    """Return the active Firestore client (Cloud Firestore or in-memory store)."""
    settings = get_settings()
    if settings.use_in_memory_firestore:
        return _in_memory_db

    from google.cloud import firestore  # type: ignore[import-untyped]

    cred_path = settings.google_application_credentials or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if cred_path and os.path.isfile(cred_path):
        return firestore.Client.from_service_account_json(
            cred_path,
            project=settings.gcp_project_id,
        )

    return firestore.Client(project=settings.gcp_project_id)


def record_audit_event(
    db: Any,
    event_type: str,
    actor_uid: str,
    target_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write an immutable audit event to the `audit_ledger` collection."""
    now_iso = datetime.now(timezone.utc).isoformat()
    event_id = f"{event_type.lower()}_{target_id}_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    payload: dict[str, Any] = {
        "event_id": event_id,
        "event_type": event_type,
        "actor_uid": actor_uid,
        "target_id": target_id,
        "metadata": metadata or {},
        "timestamp": now_iso,
    }
    db.collection("audit_ledger").document(event_id).set(payload)
    return payload
