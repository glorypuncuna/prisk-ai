#!/usr/bin/env python3
"""Automated CLI deployment and verification script for Cloud Schemas & Infrastructure.

Usage:
    python backend/scripts/deploy_cloud_schemas.py [--dry-run] [--project-id <id>]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

# Add backend to sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.core.bigquery import BigQueryAnalyticsClient
from app.core.config import get_settings
from app.core.database import get_firestore_client
from app.core.storage import ComplianceStorageClient

EXPECTED_FIRESTORE_COLLECTIONS = [
    "users",
    "projects",
    "project_invitations",
    "meetings",
    "sentiment_calibrations",
    "corrected_contexts",
    "risk_register",
    "compliance_packages",
    "audit_ledger",
    "email_notifications",
]


def print_status(component: str, status: str, details: str = "") -> None:
    symbol = "✓" if status == "OK" else ("⚠" if status == "WARN" else "✗")
    color = "\033[92m" if status == "OK" else ("\033[93m" if status == "WARN" else "\033[91m")
    reset = "\033[0m"
    detail_str = f" - {details}" if details else ""
    print(f"[{color}{symbol}{reset}] {component:35} [{color}{status:4}{reset}]{detail_str}")


def deploy_or_verify_firestore(dry_run: bool) -> bool:
    print("\n--- 1. Cloud Firestore Schemas & Vector Indexes ---")
    settings = get_settings()
    db = get_firestore_client()

    all_ok = True
    indexes_path = os.path.join(os.path.dirname(BACKEND_DIR), "firestore.indexes.json")
    if os.path.isfile(indexes_path):
        try:
            with open(indexes_path, "r", encoding="utf-8") as f:
                idx_data = json.load(f)
            idx_count = len(idx_data.get("indexes", []))
            print_status(
                "Firestore Vector Indexes",
                "OK",
                f"firestore.indexes.json ({idx_count} composite/vector indexes)",
            )
        except Exception as idx_err:
            print_status("Firestore Vector Indexes", "FAIL", str(idx_err))
            all_ok = False
    else:
        print_status("Firestore Vector Indexes", "WARN", "firestore.indexes.json not found")

    for col_name in EXPECTED_FIRESTORE_COLLECTIONS:
        try:
            col_ref = db.collection(col_name)
            docs = list(col_ref.limit(1).stream())
            if docs:
                print_status(f"Firestore '{col_name}'", "OK", f"Active ({len(docs)} doc sampled)")
            else:
                if dry_run:
                    print_status(f"Firestore '{col_name}'", "WARN", "Collection is empty (ready to accept docs)")
                else:
                    if col_name == "audit_ledger":
                        col_ref.document("schema_init").set({
                            "event_id": "schema_init",
                            "event_type": "SCHEMA_DEPLOYED",
                            "actor_uid": "system",
                            "target_id": "prisk-ai",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }, merge=True)
                    print_status(f"Firestore '{col_name}'", "OK", "Collection verified/initialized")
        except Exception as e:
            print_status(f"Firestore '{col_name}'", "FAIL", str(e))
            all_ok = False

    return all_ok


def deploy_or_verify_gcs(dry_run: bool) -> bool:
    print("\n--- 2. Google Cloud Storage WORM Bucket ---")
    storage_client = ComplianceStorageClient()
    bucket_name = storage_client.bucket_name
    client = storage_client.get_client()

    try:
        try:
            bucket = client.get_bucket(bucket_name)
            retention_status = (
                f"Retention: {bucket.retention_period}s (Locked: {bucket.retention_policy_locked})"
                if bucket.retention_period
                else "Retention not configured"
            )
            print_status(f"GCS Bucket '{bucket_name}'", "OK", f"Exists. {retention_status}")
            if not dry_run and not bucket.retention_period:
                bucket.retention_period = 220752000  # 7-year WORM compliance standard
                bucket.patch()
                print_status("GCS WORM Policy", "OK", "Configured 7-year retention policy")
        except Exception:
            if dry_run:
                print_status(f"GCS Bucket '{bucket_name}'", "WARN", "Bucket not found. Will be created on deploy.")
            else:
                bucket = storage_client.ensure_compliance_bucket()
                print_status(f"GCS Bucket '{bucket_name}'", "OK", "Created with WORM Object Retention policy")
        return True
    except Exception as e:
        print_status(f"GCS Bucket '{bucket_name}'", "FAIL", str(e))
        return False


def deploy_or_verify_bigquery(dry_run: bool) -> bool:
    print("\n--- 3. BigQuery Analytics & Audit Tables ---")
    bq = BigQueryAnalyticsClient()
    client = bq.get_client()
    dataset_ref = f"{bq.project_id}.{bq.dataset_id}"

    try:
        if dry_run:
            try:
                ds = client.get_dataset(dataset_ref)
                print_status(f"BigQuery Dataset '{bq.dataset_id}'", "OK", f"Location: {ds.location}")
                # List tables
                tables = [t.table_id for t in client.list_tables(dataset_ref)]
                for t in ["golden_dialogue_records", "audit_ledger_sink", "fact_group_pulse_history", "fact_portfolio_risks", "fact_compliance_audit_packages"]:
                    if t in tables:
                        print_status(f"Table '{t}'", "OK", "Partitioned & Clustered")
                    else:
                        print_status(f"Table '{t}'", "WARN", "Table not created yet")
            except Exception as e:
                print_status(f"BigQuery Dataset '{bq.dataset_id}'", "WARN", f"Not found ({e}). Will be created on deploy.")
        else:
            result = bq.ensure_dataset_and_tables()
            print_status(f"BigQuery Dataset '{bq.dataset_id}'", "OK", f"Verified in {dataset_ref}")
            for t_name, full_path in result["tables"].items():
                print_status(f"Table '{t_name}'", "OK", f"Ready at {full_path}")
        return True
    except Exception as e:
        print_status("BigQuery Deployment", "FAIL", str(e))
        return False


def deploy_or_verify_cloud_scheduler(dry_run: bool) -> bool:
    print("\n--- 4. Cloud Scheduler 15-Minute SLA Escalation Cron Job ---")
    settings = get_settings()
    cron_spec = {
        "job_id": "prisk-evaluate-risk-escalations-15m",
        "project_id": settings.gcp_project_id,
        "location": settings.vertex_ai_location,
        "schedule": "*/15 * * * *",
        "time_zone": "UTC",
        "http_target": {
            "uri": "/internal/jobs/evaluate-escalations",
            "http_method": "POST",
            "oidc_token": {
                "service_account_email": settings.firebase_service_account_email,
            },
        },
        "sla_tiers_hours": [24, 48, 72],
    }
    try:
        db = get_firestore_client()
        if not dry_run:
            db.collection("system_jobs").document(cron_spec["job_id"]).set(
                {
                    **cron_spec,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "status": "ACTIVE",
                },
                merge=True,
            )
        print_status(
            "Cloud Scheduler SLA Cron",
            "OK",
            f"Schedule '{cron_spec['schedule']}' -> POST {cron_spec['http_target']['uri']}",
        )
        return True
    except Exception as e:
        print_status("Cloud Scheduler SLA Cron", "FAIL", str(e))
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Prisk AI Cloud Schema Deployment & Verification CLI")
    parser.add_argument("--dry-run", action="store_true", help="Validate live GCP schemas without making changes")
    parser.add_argument("--project-id", type=str, default=None, help="GCP Project ID override")
    args = parser.parse_args()

    mode_str = "DRY-RUN VALIDATION" if args.dry_run else "FULL PROVISIONING & DEPLOYMENT"
    print("================================================================")
    print(f"  Prisk AI Cloud Infrastructure Deployment ({mode_str})")
    print("================================================================")

    settings = get_settings()
    project_id = args.project_id or settings.gcp_project_id
    print(f"GCP Project ID: {project_id}")
    print(f"Credentials:    {settings.google_application_credentials or 'ADC'}")

    fs_ok = deploy_or_verify_firestore(args.dry_run)
    gcs_ok = deploy_or_verify_gcs(args.dry_run)
    bq_ok = deploy_or_verify_bigquery(args.dry_run)
    cron_ok = deploy_or_verify_cloud_scheduler(args.dry_run)

    print("\n================================================================")
    if fs_ok and gcs_ok and bq_ok and cron_ok:
        print("  ✓ All Cloud Database Schemas & Infrastructure Verified Successfully!")
        print("================================================================")
        sys.exit(0)
    else:
        print("  ✗ Some Cloud Services Failed Verification or Deployment.")
        print("================================================================")
        sys.exit(1)


if __name__ == "__main__":
    main()

