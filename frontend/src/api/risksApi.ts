import {
  AuditLedgerEntryDoc,
  RiskCategory,
  RiskRegisterDoc,
  RiskStatus as DomainRiskStatus,
} from "../types/domain";
import { apiRequest } from "./client";

export type { RiskCategory, RiskRegisterDoc };

export type RiskStatus =
  | DomainRiskStatus
  | "ACCEPTED"
  | "DRAFT_PENDING_ADJUDICATION"
  | "OPEN"
  | "MITIGATED"
  | "CLOSED"
  | "ESCALATED"
  | "DISMISSED";

export type SeverityBand = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

export interface QualitativeCommentaryItem {
  comment_id?: string;
  author_uid: string;
  author_role?: string;
  comment: string;
  timestamp: string;
  created_at?: string;
}

export interface RiskRegisterRecord extends Omit<RiskRegisterDoc, "severity_band"> {
  severity_band: SeverityBand;
  qualitative_commentary: QualitativeCommentaryItem[];
  commentary?: QualitativeCommentaryItem[];
  escalation_config?: {
    last_escalated_tier_hours?: number;
    [key: string]: unknown;
  } | null;
}

export interface HeatmapCellNode {
  impact: number;
  probability: number;
  severity_score: number;
  severity_band: SeverityBand;
  risk_count: number;
  risk_ids: string[];
  project_ids: string[];
}

export interface SystemicRiskSpikeStatus {
  is_active: boolean;
  triggered_by_critical_projects: boolean;
  triggered_by_velocity_surge: boolean;
  concurrent_critical_project_count: number;
  concurrent_critical_project_ids: string[];
  current_7d_avg_severity: number;
  previous_7d_avg_severity: number;
  velocity_surge_pct: number;
  evaluated_at: string;
  alert_message?: string | null;
}

export interface ProjectRiskSummary {
  project_id: string;
  risk_count: number;
  critical_count: number;
  max_severity: number;
  total_risks?: number;
  critical_risks?: number;
  average_severity?: number;
}

export interface PortfolioRisksAnalyticsResponse {
  total_risks: number;
  open_or_escalated_count: number;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  average_severity_score: number;
  heatmap_cells: HeatmapCellNode[];
  category_distribution: Record<string, number>;
  project_summaries: ProjectRiskSummary[];
  systemic_spike: SystemicRiskSpikeStatus;
  risks: RiskRegisterRecord[];
}

export interface RiskAuditTrailResponse {
  risk: RiskRegisterRecord;
  source_meeting?: {
    meeting_id: string;
    title: string;
    meeting_date: string;
    status: string;
    pulse_score?: number | null;
  } | null;
  audit_events: AuditLedgerEntryDoc[];
}

export interface RiskFilterOptions {
  project_id?: string;
  projectId?: string;
  category?: RiskCategory | string;
  status?: RiskStatus | string;
  severityBand?: string;
  impact?: number;
  probability?: number;
}

export interface RiskCreatePayload {
  risk_id?: string;
  project_id: string;
  meeting_id?: string | null;
  company_name?: string | null;
  associated_groups?: string[];
  title: string;
  description: string;
  category?: RiskCategory;
  status?: RiskStatus;
  impact: number;
  probability: number;
  owner_uid?: string | null;
  mitigation_plan?: Record<string, unknown> | null;
  escalation_config?: Record<string, unknown> | null;
}

export interface RiskUpdatePayload {
  title?: string;
  description?: string;
  category?: RiskCategory;
  status?: RiskStatus;
  impact?: number;
  probability?: number;
  owner_uid?: string | null;
  escalation_enabled?: boolean;
  comment?: string;
  mitigation_plan?: Record<string, unknown> | null;
  escalation_config?: Record<string, unknown> | null;
}

export interface SlaEscalationEvaluationResult {
  evaluated_at: string;
  total_risks_scanned?: number;
  notifications_dispatched?: number;
  escalated_24h_risk_ids: string[];
  escalated_48h_risk_ids: string[];
  escalated_72h_risk_ids: string[];
}

export async function listRisks(
  idToken: string,
  options: RiskFilterOptions = {}
): Promise<RiskRegisterRecord[]> {
  const params = new URLSearchParams();
  const pid = options.project_id || options.projectId;
  if (pid) params.set("project_id", pid);
  if (options.category) params.set("category", options.category);
  if (options.status) params.set("status", options.status);
  if (options.severityBand) params.set("severity_band", options.severityBand);
  if (options.impact !== undefined) params.set("impact", String(options.impact));
  if (options.probability !== undefined)
    params.set("probability", String(options.probability));

  const query = params.toString() ? `?${params.toString()}` : "";
  return apiRequest<RiskRegisterRecord[]>(`/risks${query}`, idToken);
}

export async function getRisk(
  idToken: string,
  riskId: string
): Promise<RiskRegisterRecord> {
  return apiRequest<RiskRegisterRecord>(
    `/risks/${encodeURIComponent(riskId)}`,
    idToken
  );
}

export async function createRisk(
  idToken: string,
  payload: RiskCreatePayload
): Promise<RiskRegisterRecord> {
  const finalPayload = {
    ...payload,
    risk_id: payload.risk_id || `RSK-${Date.now().toString(36).toUpperCase()}`,
  };
  return apiRequest<RiskRegisterRecord>("/risks", idToken, {
    method: "POST",
    body: JSON.stringify(finalPayload),
  });
}

export const createRiskRecord = createRisk;

export async function updateRisk(
  idToken: string,
  riskId: string,
  updates: RiskUpdatePayload
): Promise<RiskRegisterRecord> {
  return apiRequest<RiskRegisterRecord>(
    `/risks/${encodeURIComponent(riskId)}`,
    idToken,
    {
      method: "PATCH",
      body: JSON.stringify(updates),
    }
  );
}

export const updateRiskRecord = updateRisk;

export async function fetchRiskAuditTrail(
  idToken: string,
  riskId: string
): Promise<RiskAuditTrailResponse> {
  return apiRequest<RiskAuditTrailResponse>(
    `/risks/${encodeURIComponent(riskId)}/audit-trail`,
    idToken
  );
}

export async function fetchPortfolioRisksAnalytics(
  idToken: string,
  filterOrProjectId?: string | { project_id?: string; category?: string; status?: string }
): Promise<PortfolioRisksAnalyticsResponse> {
  const params = new URLSearchParams();
  if (typeof filterOrProjectId === "string") {
    if (filterOrProjectId) params.set("project_id", filterOrProjectId);
  } else if (filterOrProjectId) {
    if (filterOrProjectId.project_id) params.set("project_id", filterOrProjectId.project_id);
    if (filterOrProjectId.category) params.set("category", filterOrProjectId.category);
    if (filterOrProjectId.status) params.set("status", filterOrProjectId.status);
  }

  const query = params.toString() ? `?${params.toString()}` : "";
  return apiRequest<PortfolioRisksAnalyticsResponse>(`/risks/heatmap${query}`, idToken);
}

export async function triggerSlaEscalationsEvaluation(
  idToken: string
): Promise<SlaEscalationEvaluationResult> {
  return apiRequest<SlaEscalationEvaluationResult>(
    "/risks/evaluate-escalations",
    idToken,
    {
      method: "POST",
    }
  );
}

export interface DiscoveredRiskItem {
  risk_id?: string | null;
  project_id: string;
  meeting_id?: string | null;
  title: string;
  description: string;
  category: RiskCategory;
  impact: number;
  probability: number;
  severity_score: number;
  severity_band: SeverityBand;
  trigger_reason: string;
  mitigation_strategy: string;
  executive_brief: string;
  associated_groups: string[];
  status: RiskStatus;
}

export interface AiRiskDiscoverResponse {
  project_id?: string | null;
  discovered_risks: DiscoveredRiskItem[];
  pulse_drops_evaluated: number;
  total_risks_found: number;
  registered_count: number;
  summary: string;
}

export interface AiMitigationActionItem {
  action: string;
  owner_role?: string;
  timeline?: string;
  status?: string;
}

export interface AiMitigationResponse {
  risk_id: string;
  project_id: string;
  title: string;
  mitigation_strategy: string;
  suggested_action_items: AiMitigationActionItem[];
  executive_escalation_brief: string;
  residual_impact: number;
  residual_probability: number;
  residual_severity_score: number;
  applied: boolean;
  updated_risk?: RiskRegisterRecord | null;
}

export async function discoverAiRisks(
  idToken: string,
  payload: {
    project_id?: string;
    meeting_id?: string;
    lookback_window?: string;
    auto_register?: boolean;
  }
): Promise<AiRiskDiscoverResponse> {
  return apiRequest<AiRiskDiscoverResponse>("/risks/ai-discover", idToken, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function synthesizeAiMitigation(
  idToken: string,
  riskId: string,
  payload?: { apply_to_risk?: boolean; context_notes?: string }
): Promise<AiMitigationResponse> {
  return apiRequest<AiMitigationResponse>(
    `/risks/${encodeURIComponent(riskId)}/ai-mitigation`,
    idToken,
    {
      method: "POST",
      body: JSON.stringify(payload || {}),
    }
  );
}

