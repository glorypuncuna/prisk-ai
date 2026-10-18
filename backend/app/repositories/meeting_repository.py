from datetime import datetime, timezone
from typing import Any
from google.cloud.firestore_v1.vector import Vector

from app.core.database import get_firestore_client
from app.schemas.meeting import (
    DialogueBlockCreate,
    DialogueBlockResponse,
    MeetingCreate,
    MeetingResponse,
)


class MeetingRepository:
    """Firestore repository for `meetings` collection and `dialogue_blocks` subcollection."""

    def __init__(self, db: Any | None = None) -> None:
        self.db = db or get_firestore_client()

    def create_meeting(self, meeting: MeetingCreate) -> MeetingResponse:
        doc_data = meeting.model_dump()
        self.db.collection("meetings").document(meeting.meeting_id).set(doc_data)
        return MeetingResponse.model_validate(doc_data)

    def get_meeting(self, meeting_id: str) -> MeetingResponse | None:
        doc = self.db.collection("meetings").document(meeting_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        data["meeting_id"] = data.get("meeting_id") or doc.id
        return MeetingResponse.model_validate(data)


    def update_meeting(self, meeting_id: str, updates: dict[str, Any]) -> MeetingResponse:
        data = dict(updates)
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.db.collection("meetings").document(meeting_id).set(data, merge=True)
        updated = self.get_meeting(meeting_id)
        if not updated:
            raise KeyError(f"Meeting '{meeting_id}' not found after update")
        return updated

    def delete_meeting(self, meeting_id: str) -> bool:
        doc_ref = self.db.collection("meetings").document(meeting_id)
        # Delete dialogue blocks first
        blocks = doc_ref.collection("dialogue_blocks").stream()
        for b in blocks:
            doc_ref.collection("dialogue_blocks").document(b.id).delete()
        doc_ref.delete()
        return True

    def create_dialogue_block(
        self, meeting_id: str, block: DialogueBlockCreate
    ) -> DialogueBlockResponse:
        doc_data = block.model_dump()
        # Convert embedding to Vector if using live Firestore
        save_data = dict(doc_data)
        if save_data.get("embedding") is not None:
            try:
                save_data["embedding"] = Vector(save_data["embedding"])
            except Exception:
                pass
        self.db.collection("meetings").document(meeting_id).collection(
            "dialogue_blocks"
        ).document(block.block_id).set(save_data)
        return DialogueBlockResponse.model_validate(doc_data)

    def get_dialogue_block(
        self, meeting_id: str, block_id: str
    ) -> DialogueBlockResponse | None:
        doc = (
            self.db.collection("meetings")
            .document(meeting_id)
            .collection("dialogue_blocks")
            .document(block_id)
            .get()
        )
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        # Convert Vector back to list[float] if needed
        if "embedding" in data and hasattr(data["embedding"], "to_map_value"):
            data["embedding"] = list(data["embedding"])
        elif "embedding" in data and hasattr(data["embedding"], "__iter__") and not isinstance(data["embedding"], list):
            data["embedding"] = list(data["embedding"])
        return DialogueBlockResponse.model_validate(data)

    def list_dialogue_blocks(self, meeting_id: str) -> list[DialogueBlockResponse]:
        snaps = (
            self.db.collection("meetings")
            .document(meeting_id)
            .collection("dialogue_blocks")
            .stream()
        )
        results: list[DialogueBlockResponse] = []
        for s in snaps:
            data = s.to_dict() or {}
            if "embedding" in data and hasattr(data["embedding"], "__iter__") and not isinstance(data["embedding"], list):
                data["embedding"] = list(data["embedding"])
            results.append(DialogueBlockResponse.model_validate(data))
        results.sort(key=lambda b: b.sequence_index)
        return results

    def update_dialogue_block(
        self, meeting_id: str, block_id: str, updates: dict[str, Any]
    ) -> DialogueBlockResponse:
        save_data = dict(updates)
        if save_data.get("embedding") is not None:
            try:
                save_data["embedding"] = Vector(save_data["embedding"])
            except Exception:
                pass
        self.db.collection("meetings").document(meeting_id).collection(
            "dialogue_blocks"
        ).document(block_id).set(save_data, merge=True)
        updated = self.get_dialogue_block(meeting_id, block_id)
        if not updated:
            raise KeyError(f"Dialogue block '{block_id}' not found after update")
        return updated

    def delete_dialogue_block(self, meeting_id: str, block_id: str) -> bool:
        self.db.collection("meetings").document(meeting_id).collection(
            "dialogue_blocks"
        ).document(block_id).delete()
        return True

    def find_by_bot_id(self, bot_id: str) -> MeetingResponse | None:
        """Find meeting document associated with a specific MeetStream bot ID."""
        snaps = self.db.collection("meetings").stream()
        for snap in snaps:
            data = snap.to_dict() or {}
            if data.get("meetstream_bot_id") == bot_id or (
                isinstance(data.get("model_metadata"), dict)
                and data["model_metadata"].get("bot_id") == bot_id
            ):
                return MeetingResponse.model_validate(data)
        return None

    def save_scrubbed_dialogue_blocks(
        self,
        meeting_id: str,
        blocks: list[DialogueBlockCreate],
        meeting_updates: dict[str, Any] | None = None,
    ) -> list[DialogueBlockResponse]:
        """Atomically persist scrubbed dialogue blocks and update meeting status to PROCESSING_POST_MEETING.
        
        Uses a Firestore WriteBatch to guarantee all blocks and the meeting status update commit atomically.
        """
        meeting_ref = self.db.collection("meetings").document(meeting_id)
        blocks_coll = meeting_ref.collection("dialogue_blocks")

        batch = self.db.batch()

        updates = dict(meeting_updates or {})
        updates["status"] = "PROCESSING_POST_MEETING"
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()

        participants: set[str] = set()
        for b in blocks:
            if b.speaker_alias:
                participants.add(b.speaker_alias)
        if participants:
            updates["participants"] = sorted(list(participants))

        batch.set(meeting_ref, updates, merge=True)

        responses: list[DialogueBlockResponse] = []
        for block in blocks:
            b_data = block.model_dump()
            save_data = dict(b_data)
            if save_data.get("embedding") is not None:
                try:
                    save_data["embedding"] = Vector(save_data["embedding"])
                except Exception:
                    pass
            doc_ref = blocks_coll.document(block.block_id)
            batch.set(doc_ref, save_data)
            responses.append(DialogueBlockResponse.model_validate(b_data))

        batch.commit()
        return responses

