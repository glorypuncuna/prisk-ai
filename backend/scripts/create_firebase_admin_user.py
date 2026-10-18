import os
import sys
import firebase_admin
from firebase_admin import auth, credentials

CRED_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "service-account.json",
)

if not os.path.isfile(CRED_PATH):
    print("Service account key not found.")
    sys.exit(1)

cred = credentials.Certificate(CRED_PATH)
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred, {"projectId": "prisk-ai"})

email = "admin@enterprise.com"
password = "AdminPrisk2026!"
uid = "uid_superadmin"

try:
    user = auth.get_user_by_email(email)
    print(f"User already exists in Firebase Auth: {user.uid}. Updating password...")
    auth.update_user(user.uid, password=password)
    target_uid = user.uid
except Exception:
    print(f"Creating user {email} in Firebase Auth...")
    user = auth.create_user(
        uid=uid,
        email=email,
        password=password,
        display_name="Super Administrator",
        email_verified=True,
    )
    target_uid = user.uid
    print(f"Created Firebase Auth user: {target_uid}")

# Set custom claims
auth.set_custom_user_claims(target_uid, {"role": "ADMIN", "assigned_project_ids": ["proj-alpha"]})
print(f"Synchronized Firebase Custom Claims: {{'role': 'ADMIN', 'assigned_project_ids': ['proj-alpha']}}")
print(f"\nAdmin credentials ready:")
print(f"Email: {email}")
print(f"Password: {password}")
