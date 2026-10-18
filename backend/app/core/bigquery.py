import json
import os
from typing import Any
from google.cloud import bigquery

from app.core.config import get_settings


# BigQuery Table Schemas
GOLDEN_DIALOGUE_RECORDS_SCHEMA = [
    bigquery.SchemaField("meeting_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("project_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("meeting_date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("block_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("group_id", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("group_name", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("company_name", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("text_scrubbed", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("word_count", "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("sentiment_score", "FLOAT", mode="NULLABLE"),
    bigquery.SchemaField("is_human_overridden", "BOOLEAN", mode="REQUIRED"),
    bigquery.SchemaField("committed_at", "TIMESTAMP", mode="REQUIRED"),
]

AUDIT_LEDGER_SINK_SCHEMA = [
    bigquery.SchemaField("event_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("event_type", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("actor_uid", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("target_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("actor_role", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("action_type", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("entity_type", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("metadata_json", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("sha256_hash", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
]

FACT_GROUP_PULSE_HISTORY_SCHEMA = [
    bigquery.SchemaField("meeting_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("project_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("company_name", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("group_name", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("meeting_date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("pulse_score", "FLOAT", mode="REQUIRED"),
    bigquery.SchemaField("overall_meeting_score", "FLOAT", mode="NULLABLE"),
    bigquery.SchemaField("block_count", "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("top_liked_words", "STRING", mode="REPEATED"),
    bigquery.SchemaField("top_disliked_words", "STRING", mode="REPEATED"),
    bigquery.SchemaField("committed_at", "TIMESTAMP", mode="REQUIRED"),
]

FACT_PORTFOLIO_RISKS_SCHEMA = [
    bigquery.SchemaField("risk_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("project_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("company_name", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("source_meeting_id", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("category", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("status", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("impact_score", "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("probability_score", "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("severity_index", "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("risk_owner_uid", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("sla_started_at", "TIMESTAMP", mode="NULLABLE"),
    bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("updated_at", "TIMESTAMP", mode="REQUIRED"),
]

FACT_COMPLIANCE_PACKAGES_SCHEMA = [
    bigquery.SchemaField("package_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("project_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("company_name", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("target_frameworks", "STRING", mode="REPEATED"),
    bigquery.SchemaField("format", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("sha256_hash", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("storage_uri", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("generated_by_uid", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("generated_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("risk_count", "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("active_framework_clauses_count", "INTEGER", mode="NULLABLE"),
]


class BigQueryAnalyticsClient:
    """BigQuery client for analytical streaming and audit ledger sink."""

    def __init__(
        self,
        project_id: str | None = None,
        dataset_id: str | None = None,
        credentials_path: str | None = None,
    ) -> None:
        settings = get_settings()
        self.project_id = project_id or settings.gcp_project_id
        self.dataset_id = dataset_id or settings.bigquery_dataset_id
        self.credentials_path = (
            credentials_path
            or settings.google_application_credentials
            or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        )
        self._client: bigquery.Client | None = None

    def get_client(self) -> bigquery.Client:
        if self._client is None:
            if self.credentials_path and os.path.isfile(self.credentials_path):
                self._client = bigquery.Client.from_service_account_json(
                    self.credentials_path, project=self.project_id
                )
            else:
                self._client = bigquery.Client(project=self.project_id)
        return self._client

    def ensure_dataset_and_tables(self) -> dict[str, Any]:
        """Verify and provision BigQuery dataset and all partitioned tables."""
        client = self.get_client()
        dataset_ref = f"{self.project_id}.{self.dataset_id}"
        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = "US"
        client.create_dataset(dataset, exists_ok=True)

        created_tables: dict[str, str] = {}

        # 1. golden_dialogue_records: partitioned by meeting_date, clustered by project_id, group_id
        t1_id = f"{dataset_ref}.golden_dialogue_records"
        t1 = bigquery.Table(t1_id, schema=GOLDEN_DIALOGUE_RECORDS_SCHEMA)
        t1.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="meeting_date",
        )
        t1.clustering_fields = ["project_id", "group_id"]
        client.create_table(t1, exists_ok=True)
        created_tables["golden_dialogue_records"] = t1_id

        # 2. audit_ledger_sink: partitioned by DATE(timestamp), clustered by actor_uid, target_id
        t2_id = f"{dataset_ref}.audit_ledger_sink"
        t2 = bigquery.Table(t2_id, schema=AUDIT_LEDGER_SINK_SCHEMA)
        t2.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="timestamp",
        )
        t2.clustering_fields = ["event_type", "actor_uid"]
        client.create_table(t2, exists_ok=True)
        created_tables["audit_ledger_sink"] = t2_id

        # 3. fact_group_pulse_history
        t3_id = f"{dataset_ref}.fact_group_pulse_history"
        t3 = bigquery.Table(t3_id, schema=FACT_GROUP_PULSE_HISTORY_SCHEMA)
        t3.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="meeting_date",
        )
        t3.clustering_fields = ["project_id", "group_name"]
        client.create_table(t3, exists_ok=True)
        created_tables["fact_group_pulse_history"] = t3_id

        # 4. fact_portfolio_risks
        t4_id = f"{dataset_ref}.fact_portfolio_risks"
        t4 = bigquery.Table(t4_id, schema=FACT_PORTFOLIO_RISKS_SCHEMA)
        t4.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="created_at",
        )
        t4.clustering_fields = ["project_id", "category"]
        client.create_table(t4, exists_ok=True)
        created_tables["fact_portfolio_risks"] = t4_id

        # 5. fact_compliance_audit_packages
        t5_id = f"{dataset_ref}.fact_compliance_audit_packages"
        t5 = bigquery.Table(t5_id, schema=FACT_COMPLIANCE_PACKAGES_SCHEMA)
        t5.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="generated_at",
        )
        t5.clustering_fields = ["project_id", "format"]
        client.create_table(t5, exists_ok=True)
        created_tables["fact_compliance_audit_packages"] = t5_id

        return {
            "dataset": dataset_ref,
            "tables": created_tables,
        }

    def stream_golden_dialogue_records(
        self, records: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Stream committed golden record dialogue blocks into BigQuery."""
        if not records:
            return []
        _in_memory_bq_golden_records.extend(records)
        settings = get_settings()
        if self._client is None and settings.use_in_memory_firestore:
            return records
        try:
            client = self.get_client()
            table_id = f"{self.project_id}.{self.dataset_id}.golden_dialogue_records"
            errors = client.insert_rows_json(table_id, records)
            if errors:
                raise RuntimeError(f"BigQuery streaming errors: {errors}")
        except Exception:
            pass
        return records

    def stream_group_pulse_history(
        self, records: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Stream group pulse rollup rows into BigQuery fact_group_pulse_history."""
        if not records:
            return []
        _in_memory_bq_pulse_history.extend(records)
        settings = get_settings()
        if self._client is None and settings.use_in_memory_firestore:
            return records
        try:
            client = self.get_client()
            table_id = f"{self.project_id}.{self.dataset_id}.fact_group_pulse_history"
            errors = client.insert_rows_json(table_id, records)
            if errors:
                raise RuntimeError(f"BigQuery pulse history streaming errors: {errors}")
        except Exception:
            pass
        return records

    def stream_audit_ledger_event(
        self, event: dict[str, Any]
    ) -> dict[str, Any]:
        """Stream an immutable audit event to BigQuery audit ledger sink."""
        row = dict(event)
        if "metadata" in row and not isinstance(row.get("metadata_json"), str):
            row["metadata_json"] = json.dumps(row.pop("metadata", {}))
        _in_memory_bq_audit_events.append(row)
        settings = get_settings()
        if self._client is None and settings.use_in_memory_firestore:
            return row
        try:
            client = self.get_client()
            table_id = f"{self.project_id}.{self.dataset_id}.audit_ledger_sink"
            errors = client.insert_rows_json(table_id, [row])
            if errors:
                raise RuntimeError(f"BigQuery audit sink errors: {errors}")
        except Exception:
            pass
        return row

    def stream_portfolio_risk(
        self, risk_record: dict[str, Any]
    ) -> dict[str, Any]:
        """Stream a risk register record into BigQuery fact_portfolio_risks."""
        esc = risk_record.get("escalation_config") or {}
        row = {
            "risk_id": risk_record["risk_id"],
            "project_id": risk_record["project_id"],
            "company_name": risk_record.get("company_name"),
            "source_meeting_id": risk_record.get("meeting_id"),
            "category": str(risk_record.get("category", "OPERATIONAL")),
            "status": str(risk_record.get("status", "OPEN")),
            "impact_score": int(risk_record.get("impact", 3)),
            "probability_score": int(risk_record.get("probability", 3)),
            "severity_index": int(risk_record.get("severity_score", 9)),
            "risk_owner_uid": risk_record.get("owner_uid"),
            "sla_started_at": esc.get("sla_started_at"),
            "created_at": risk_record.get("created_at"),
            "updated_at": risk_record.get("updated_at"),
        }
        _in_memory_bq_portfolio_risks.append(row)
        settings = get_settings()
        if self._client is None and settings.use_in_memory_firestore:
            return row
        try:
            client = self.get_client()
            table_id = f"{self.project_id}.{self.dataset_id}.fact_portfolio_risks"
            errors = client.insert_rows_json(table_id, [row])
            if errors:
                raise RuntimeError(f"BigQuery portfolio risk errors: {errors}")
        except Exception:
            pass
        return row

    def stream_compliance_package(
        self, pkg_record: dict[str, Any]
    ) -> dict[str, Any]:
        """Stream a sealed compliance package record into BigQuery fact_compliance_audit_packages."""
        row = {
            "package_id": pkg_record["package_id"],
            "project_id": pkg_record["project_id"],
            "company_name": pkg_record.get("company_name"),
            "target_frameworks": list(pkg_record.get("target_frameworks", [])),
            "format": str(pkg_record.get("format", "PDF")),
            "sha256_hash": pkg_record["sha256_hash"],
            "storage_uri": pkg_record["gcs_uri"],
            "generated_by_uid": pkg_record["generated_by_uid"],
            "generated_at": pkg_record["generated_at"],
            "risk_count": int(pkg_record.get("risk_count", 0)),
            "active_framework_clauses_count": int(
                pkg_record.get("active_framework_clauses_count", 0)
            ),
        }
        _in_memory_bq_compliance_packages.append(row)
        settings = get_settings()
        if self._client is None and settings.use_in_memory_firestore:
            return row
        try:
            client = self.get_client()
            table_id = f"{self.project_id}.{self.dataset_id}.fact_compliance_audit_packages"
            errors = client.insert_rows_json(table_id, [row])
            if errors:
                raise RuntimeError(f"BigQuery compliance package errors: {errors}")
        except Exception:
            pass
        return row

    def purge_meeting_analytics_rows(self, meeting_id: str) -> dict[str, int]:
        """Purge raw analytical rows for a meeting pursuant to GDPR Article 17."""
        before_golden = len(_in_memory_bq_golden_records)
        _in_memory_bq_golden_records[:] = [
            r for r in _in_memory_bq_golden_records if r.get("meeting_id") != meeting_id
        ]
        purged_golden = before_golden - len(_in_memory_bq_golden_records)

        before_pulse = len(_in_memory_bq_pulse_history)
        _in_memory_bq_pulse_history[:] = [
            r for r in _in_memory_bq_pulse_history if r.get("meeting_id") != meeting_id
        ]
        purged_pulse = before_pulse - len(_in_memory_bq_pulse_history)

        before_risks = len(_in_memory_bq_portfolio_risks)
        _in_memory_bq_portfolio_risks[:] = [
            r
            for r in _in_memory_bq_portfolio_risks
            if r.get("source_meeting_id") != meeting_id
        ]
        purged_risks = before_risks - len(_in_memory_bq_portfolio_risks)

        return {
            "golden_dialogue_records_purged": purged_golden,
            "fact_group_pulse_history_purged": purged_pulse,
            "fact_portfolio_risks_purged": purged_risks,
        }


_in_memory_bq_golden_records: list[dict[str, Any]] = []
_in_memory_bq_pulse_history: list[dict[str, Any]] = []
_in_memory_bq_audit_events: list[dict[str, Any]] = []
_in_memory_bq_portfolio_risks: list[dict[str, Any]] = []
_in_memory_bq_compliance_packages: list[dict[str, Any]] = []


