#!/usr/bin/env python3
"""CLI utility to inspect or elevate a user's RBAC role in Firestore and Firebase Custom Claims.

Usage:
    python backend/scripts/set_role.py <email-or-uid> [ROLE] [PROJECT_ID ...]

Examples:
    python backend/scripts/set_role.py budi@enterprise.com EXECUTIVE proj-alpha
    python backend/scripts/set_role.py uid_12345 MANAGER
"""

import sys
from pathlib import Path

# Ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import get_firestore_client, record_audit_event
from app.core.enums import UserRole
from app.core.firebase import set_firebase_custom_user_claims


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python backend/scripts/set_role.py <email-or-uid> [ROLE] [PROJECT_ID ...]")
        sys.exit(1)

    target = sys.argv[1].strip().lower()
    target_role_str = sys.argv[2].strip().upper() if len(sys.argv) > 2 else "EXECUTIVE"
    try:
        new_role = UserRole(target_role_str)
    except ValueError:
        print(f"Error: Invalid role '{target_role_str}'. Valid roles: {[r.value for r in UserRole]}")
        sys.exit(1)

    additional_projects = sys.argv[3:] if len(sys.argv) > 3 else ["proj-alpha"]

    db = get_firestore_client()
    users_coll = db.collection("users")

    # Match by UID or Email
    target_doc = None
    target_uid = None

    snap = users_coll.document(target).get()
    if snap.exists:
        target_doc = snap.to_dict()
        target_uid = target
    else:
        # Search by email
        for s in users_coll.stream():
            d = s.to_dict() or {}
            if str(d.get("email", "")).strip().lower() == target:
                target_doc = d
                target_uid = s.id
                break

    if not target_doc or not target_uid:
        print(f"Error: User '{target}' not found in registered Firestore profiles.")
        print("Available registered users:")
        for s in users_coll.stream():
            d = s.to_dict() or {}
            print(f" - UID: {s.id} | Email: {d.get('email')} | Current Role: {d.get('role')}")
        sys.exit(1)

    previous_role = target_doc.get("role", "EXTERNAL_STAKEHOLDER")
    assigned_projects = list(
        dict.fromkeys(list(target_doc.get("assigned_project_ids", [])) + additional_projects)
    )

    target_doc["role"] = new_role.value
    target_doc["assigned_project_ids"] = assigned_projects
    target_doc["onboarding_status"] = "ACTIVE"

    users_coll.document(target_uid).set(target_doc, merge=True)
    set_firebase_custom_user_claims(
        target_uid,
        {"role": new_role.value, "assigned_project_ids": assigned_projects},
    )

    record_audit_event(
        db=db,
        event_type="ROLE_ELEVATED",
        actor_uid="system_cli_bootstrap",
        target_id=target_uid,
        metadata={
            "previous_role": previous_role,
            "new_role": new_role.value,
            "assigned_project_ids": assigned_projects,
            "via": "set_role.py",
        },
    )

    print(f"Successfully elevated user '{target_uid}' ({target_doc.get('email')})!")
    print(f"  Role: {new_role.value}")
    print(f"  Assigned Projects: {assigned_projects}")
    print(f"  Onboarding Status: ACTIVE")


if __name__ == "__main__":
    main()
