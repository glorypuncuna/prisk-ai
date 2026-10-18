import {
  ComplianceFormat,
  ComplianceFramework,
  CompliancePackageDoc,
} from "../types/domain";
import { apiRequest } from "./client";

export type {
  ComplianceFormat,
  ComplianceFramework,
  CompliancePackageDoc,
};

export interface ComplianceExportPayload {
  project_id: string;
  target_frameworks: ComplianceFramework[] | string[];
  format: ComplianceFormat | string;
  start_date?: string | null;
  end_date?: string | null;
}

export interface ComplianceIntegrityCheck {
  package_id: string;
  stored_sha256: string;
  computed_sha256: string;
  integrity_valid: boolean;
  checked_at: string;
}

export interface ComplianceDownloadResponse {
  package_id: string;
  download_url: string;
  sha256_hash: string;
  expires_in_seconds: number;
}

export async function listCompliancePackages(
  idToken: string,
  projectId?: string
): Promise<CompliancePackageDoc[]> {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return apiRequest<CompliancePackageDoc[]>(`/compliance/packages${query}`, idToken);
}

export async function getCompliancePackage(
  idToken: string,
  packageId: string
): Promise<CompliancePackageDoc> {
  return apiRequest<CompliancePackageDoc>(
    `/compliance/packages/${encodeURIComponent(packageId)}`,
    idToken
  );
}

export async function exportCompliancePackage(
  idToken: string,
  payload: ComplianceExportPayload
): Promise<CompliancePackageDoc> {
  return apiRequest<CompliancePackageDoc>("/compliance/export", idToken, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function verifyCompliancePackageIntegrity(
  idToken: string,
  packageId: string
): Promise<ComplianceIntegrityCheck> {
  return apiRequest<ComplianceIntegrityCheck>(
    `/compliance/packages/${encodeURIComponent(packageId)}/verify`,
    idToken
  );
}

export async function getComplianceDownloadUrl(
  idToken: string,
  packageId: string
): Promise<ComplianceDownloadResponse> {
  return apiRequest<ComplianceDownloadResponse>(
    `/compliance/packages/${encodeURIComponent(packageId)}/download-url`,
    idToken
  );
}

export async function fetchComplianceFrameworkMatrix(
  idToken: string
): Promise<Record<string, unknown>> {
  return apiRequest<Record<string, unknown>>("/compliance/frameworks", idToken);
}

export interface ComplianceNarrativeResponse {
  project_id: string;
  company_name: string;
  target_frameworks: string[];
  executive_summary: string;
  framework_treatment_summaries: Record<string, string>;
  continuous_monitoring_attestation: string;
  zero_audio_privacy_statement: string;
  zero_verbatim_quotes_verified: boolean;
  generated_at: string;
}

export interface GdprPurgeResponse {
  meeting_id: string;
  project_id: string;
  status: string;
  purged_dialogue_blocks_count: number;
  purged_calibrations_count: number;
  purged_risks_count: number;
  purged_bigquery_rows: Record<string, number>;
  redacted_compliance_packages_count: number;
  tombstone_audit_event_id: string;
  purged_at: string;
}

export async function fetchAiComplianceNarrative(
  idToken: string,
  payload: {
    project_id: string;
    company_name?: string;
    target_frameworks: string[];
  }
): Promise<ComplianceNarrativeResponse> {
  return apiRequest<ComplianceNarrativeResponse>(
    "/compliance/ai-narrative",
    idToken,
    {
      method: "POST",
      body: JSON.stringify(payload),
    }
  );
}

export async function purgeMeetingGdpr(
  idToken: string,
  meetingId: string,
  reason?: string
): Promise<GdprPurgeResponse> {
  return apiRequest<GdprPurgeResponse>(
    "/compliance/gdpr-purge",
    idToken,
    {
      method: "POST",
      body: JSON.stringify({ meeting_id: meetingId, reason }),
    }
  );
}

