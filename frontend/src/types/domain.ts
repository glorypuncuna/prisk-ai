export type UserRole =
  | "ADMIN"
  | "EXECUTIVE"
  | "MANAGER"
  | "ADJUDICATOR"
  | "EXTERNAL_STAKEHOLDER";

export type AuthProvider = "password" | "google.com" | "microsoft.com";

export type OnboardingStatus =
  | "ACTIVE"
  | "QUARANTINED_PENDING_INVITATION";

export interface UserProfileDoc {
  uid: string;
  email: string;
  first_name: string;
  last_name: string;
  phone_number: string;
  role: UserRole;
  auth_provider: string;
  assigned_project_ids: string[];
  onboarding_status: OnboardingStatus | string;
  created_at: string;
  last_login_at: string;
}

export interface ProjectAlertThresholds {
  pulse_drop_delta: number;
  minimum_pulse_score: number;
  escalation_enabled: boolean;
  escalation_intervals_hours: number[];
}

export interface ProjectDoc {
  project_id: string;
  name: string;
  company_name?: string;
  description?: string;
  canonical_groups: string[];
  alert_thresholds: ProjectAlertThresholds;
  owner_uid: string;
  created_at: string;
  updated_at?: string | null;
}

export type InvitationStatus = "PENDING" | "ACCEPTED" | "REVOKED";

export interface ProjectInvitationDoc {
  invitation_id: string;
  project_id: string;
  project_name: string;
  invitee_email: string;
  invited_by_uid: string;
  status: InvitationStatus | string;
  created_at: string;
  accepted_at?: string | null;
}

export type MeetingStatus =
  | "SCHEDULED"
  | "LIVE"
  | "PROCESSING_POST_MEETING"
  | "PENDING_ADJUDICATION"
  | "COMMITTED"
  | "GOLDEN_RECORD"
  | "PURGED_CONSENT_REVOKED";

export interface RubricBreakdown {
  emotional_valence: number;
  delivery_alignment: number;
  relationship_trust: number;
  momentum_commitment: number;
}

export interface GroupPulseMetric {
  pulse_score: number;
  block_count: number;
  top_liked_words: string[];
  top_disliked_words: string[];
}

export interface ActionItem {
  action_id: string;
  description: string;
  owner_group: string;
  due_date?: string | null;
}

export interface MoMSummary {
  date_time?: string | null;
  location: string;
  title: string;
  agenda: string[];
  topics_of_discussion: string[];
  summary: string;
  action_items: ActionItem[];
  recommended_mitigations: string[];
}

export interface MeetingDoc {
  meeting_id: string;
  project_id: string;
  title: string;
  platform: string;
  meeting_date: string;
  status: MeetingStatus | string;
  pulse_score?: number | null;
  group_scores: Record<string, GroupPulseMetric>;
  mom_summary?: MoMSummary | null;
  participants: string[];
  ephemeral_speaker_map?: Record<string, string> | null;
  model_metadata?: Record<string, unknown> | null;
  meetstream_bot_id?: string | null;
  transcript_id?: string | null;
  created_at: string;
  updated_at?: string | null;
}

export interface XAIAttributionItem {
  verbatim_phrase: string;
  start_char: number;
  end_char: number;
  attribution_weight: number;
  rubric_dimension: string;
  rationale: string;
}

export interface XAIExplanation {
  computed_at: string;
  attributions: XAIAttributionItem[];
}

export interface DialogueBlockDoc {
  block_id: string;
  sequence_index: number;
  parent_block_id?: string | null;
  start_time_sec?: number | null;
  end_time_sec?: number | null;
  speaker_alias?: string | null;
  display_speaker_label?: string | null;
  ephemeral_speaker_account_id?: string | null;
  group_id?: string | null;
  group_name?: string | null;
  company_name?: string | null;
  optional_participant_name?: string | null;
  text_scrubbed: string;
  word_count: number;
  dlp_redaction_flags: string[];
  sentiment_score?: number | null;
  ai_initial_score?: number | null;
  ai_confidence?: number | null;
  rubric_scores?: RubricBreakdown | null;
  embedding?: number[] | null;
  is_split: boolean;
  is_pinned: boolean;
  is_human_overridden: boolean;
  xai_attribution?: XAIExplanation | null;
}

export interface SentimentCalibrationDoc {
  calibration_id: string;
  project_id?: string | null;
  group_name?: string | null;
  dialogue_text: string;
  benchmark_score: number;
  rubric_breakdown: RubricBreakdown | Record<string, number>;
  embedding?: number[] | null;
  adjudicator_uid?: string | null;
  created_at: string;
}

export interface CorrectedContextDoc {
  correction_id: string;
  project_id: string;
  group_name?: string | null;
  scrubbed_text: string;
  embedding?: number[] | null;
  ai_initial_score: number;
  human_adjusted_score: number;
  rubric_breakdown: RubricBreakdown | Record<string, number>;
  adjudicator_uid?: string | null;
  created_at: string;
}

export type RiskCategory =
  | "FINANCIAL"
  | "OPERATIONAL"
  | "COMPLIANCE"
  | "STRATEGIC"
  | "RELATIONSHIP";

export type RiskStatus =
  | "DRAFT_PENDING_ADJUDICATION"
  | "OPEN"
  | "MITIGATED"
  | "CLOSED"
  | "ESCALATED"
  | "DISMISSED";

export type EscalationTier = "24h" | "48h" | "72h";

export interface RiskRegisterDoc {
  risk_id: string;
  project_id: string;
  meeting_id?: string | null;
  company_name?: string | null;
  associated_groups: string[];
  title: string;
  description: string;
  category: RiskCategory;
  status: RiskStatus;
  impact: number;
  probability: number;
  severity_score: number;
  owner_uid?: string | null;
  sla_escalation_tier: EscalationTier | string;
  mitigation_plan?: { strategy?: string } | Record<string, unknown> | null;
  escalation_config?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export type ComplianceFramework =
  | "ISO_31000"
  | "COSO"
  | "SOC_2"
  | "HIPAA"
  | "GDPR";

export type ComplianceFormat = "PDF" | "CSV" | "JSON";

export type CompliancePackageStatus =
  | "PENDING"
  | "SEALED_WORM"
  | "COMPLETED";

export interface CompliancePackageDoc {
  package_id: string;
  project_id: string;
  company_name?: string | null;
  framework?: string | null;
  target_frameworks: ComplianceFramework[] | string[];
  format: ComplianceFormat | string;
  sha256_hash: string;
  gcs_uri: string;
  status: CompliancePackageStatus | string;
  generated_by_uid: string;
  generated_at: string;
  sections?: Record<string, unknown> | null;
  created_at: string;
}

export type AuditActionType =
  | "BUBBLE_SPLIT"
  | "GROUP_TAG_CHANGE"
  | "SLIDER_OVERRIDE"
  | "XAI_INVOKED"
  | "GOLDEN_RECORD_COMMIT"
  | "RISK_OVERRIDE"
  | "CONSENT_REVOKED"
  | "COMPLIANCE_PACKAGE_EXPORTED"
  | "GDPR_ARTICLE_17_ERASURE_TOMBSTONE"
  | "USER_PROVISIONED"
  | "USER_DELETED"
  | "ROLE_CHANGED"
  | "SYSTEM_INITIALIZED";

export type AuditEntityType =
  | "USER"
  | "PROJECT"
  | "MEETING"
  | "DIALOGUE_BLOCK"
  | "RISK"
  | "COMPLIANCE_PACKAGE"
  | "SYSTEM";

export interface AuditLedgerEntryDoc {
  event_id: string;
  event_type: string;
  actor_uid: string;
  target_id: string;
  actor_role?: string | null;
  action_type?: AuditActionType | string | null;
  entity_type?: AuditEntityType | string | null;
  metadata: Record<string, unknown>;
  sha256_hash?: string | null;
  previous_state_json?: string | null;
  new_state_json?: string | null;
  model_version?: string | null;
  timestamp: string;
}

export interface ProjectVectorDiagnostics {
  project_id: string;
  embedding_model: string;
  embedding_dimension: number;
  total_exemplars: number;
  group_coverage: Record<string, number>;
  inference_mode: "FEW_SHOT" | "ZERO_SHOT" | string;
  nearest_neighbor_readiness: boolean;
  recent_exemplars: Array<{
    calibration_id: string;
    group_name?: string | null;
    benchmark_score: number;
    has_embedding: boolean;
    embedding_dimension: number;
    created_at: string;
  }>;
  checked_at: string;
}

export interface PulseTrendPoint {
  meeting_id: string;
  project_id: string;
  title: string;
  meeting_date: string;
  pulse_score: number;
  group_scores: Record<string, GroupPulseMetric | { pulse_score: number; block_count: number }>;
  status: string;
}

export interface AiPulseCommentary {
  headline: string;
  trajectory_summary: string;
  key_drivers_of_shifts: string[];
  group_trends: Record<string, string>;
  risk_warning?: string | null;
  recommended_interventions: string[];
}

export interface PulseTrendsAggregate {
  total_meetings: number;
  average_pulse: number;
  pulse_change: number;
  lowest_pulse_meeting?: {
    meeting_id: string;
    title: string;
    meeting_date: string;
    pulse_score: number;
  } | null;
  highest_pulse_meeting?: {
    meeting_id: string;
    title: string;
    meeting_date: string;
    pulse_score: number;
  } | null;
  group_averages: Record<string, number>;
}

export interface PulseTrendsResponse {
  time_window: string;
  start_date: string;
  end_date: string;
  project_ids: string[];
  trajectory_points: PulseTrendPoint[];
  ai_commentary: AiPulseCommentary;
  aggregate_metrics: PulseTrendsAggregate;
  generated_at: string;
}

export interface ValidatedSpanAttribution {
  verbatim_phrase: string;
  start_char: number;
  end_char: number;
  attribution_weight: number;
  rubric_dimension: string;
  rationale: string;
}

export interface BlockExplainResponse {
  meeting_id: string;
  block_id: string;
  scrubbed_text: string;
  pulse_score: number;
  rubric_breakdown: RubricBreakdown;
  attributions: ValidatedSpanAttribution[];
  computed_at: string;
}

