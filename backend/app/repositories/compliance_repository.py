from typing import Any

from app.core.database import get_firestore_client
from app.schemas.compliance import (
    CompliancePackageCreate,
    CompliancePackageResponse,
)


class ComplianceRepository:
    """Firestore repository for `compliance_packages` collection."""

    def __init__(self, db: Any | None = None) -> None:
        self.db = db or get_firestore_client()

    def create_package(
        self, package: CompliancePackageCreate
    ) -> CompliancePackageResponse:
        data = package.model_dump()
        self.db.collection("compliance_packages").document(
            package.package_id
        ).set(data)
        return CompliancePackageResponse.model_validate(data)

    def get_package(self, package_id: str) -> CompliancePackageResponse | None:
        doc = self.db.collection("compliance_packages").document(package_id).get()
        if not doc.exists:
            return None
        return CompliancePackageResponse.model_validate(doc.to_dict())

    def update_package(
        self, package_id: str, updates: dict[str, Any]
    ) -> CompliancePackageResponse | None:
        self.db.collection("compliance_packages").document(package_id).set(
            updates, merge=True
        )
        return self.get_package(package_id)

    def list_packages(
        self,
        project_id: str | None = None,
        allowed_project_ids: list[str] | None = None,
    ) -> list[CompliancePackageResponse]:
        col = self.db.collection("compliance_packages")
        snaps = col.stream()
        results: list[CompliancePackageResponse] = []
        allowed_set = set(allowed_project_ids) if allowed_project_ids is not None else None
        for s in snaps:
            data = s.to_dict() or {}
            pkg_proj = data.get("project_id")
            if project_id and pkg_proj != project_id:
                continue
            if allowed_set is not None and pkg_proj not in allowed_set:
                continue
            results.append(CompliancePackageResponse.model_validate(data))
        results.sort(key=lambda p: p.generated_at or "", reverse=True)
        return results
