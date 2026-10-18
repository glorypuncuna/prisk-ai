export interface RubricBreakdown {
  emotional_valence: number;
  delivery_alignment: number;
  relationship_trust: number;
  momentum_commitment: number;
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

export interface DialogueBlock {
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
  is_split: boolean;
  is_pinned: boolean;
  is_human_overridden: boolean;
  xai_attribution?: XAIExplanation | null;
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

export interface MeetingRecord {
  meeting_id: string;
  project_id: string;
  title: string;
  platform: string;
  meeting_date: string;
  status: string;
  pulse_score?: number | null;
  group_scores: Record<string, GroupPulseMetric>;
  mom_summary?: MoMSummary | null;
  participants: string[];
  ephemeral_speaker_map?: Record<string, string> | null;
  created_at: string;
  updated_at?: string | null;
}

export interface DraftRiskRecord {
  risk_id: string;
  project_id: string;
  meeting_id?: string | null;
  company_name?: string | null;
  associated_groups: string[];
  title: string;
  description: string;
  category: string;
  status: string;
  impact: number;
  probability: number;
  severity_score: number;
  owner_uid?: string | null;
  sla_escalation_tier: string;
}

export interface AdjudicationWorkspaceData {
  meeting: MeetingRecord;
  canonical_groups: string[];
  ephemeral_speaker_map: Record<string, string>;
  dialogue_blocks: DialogueBlock[];
  draft_risks: DraftRiskRecord[];
}

export interface BlockExplainResponse {
  meeting_id: string;
  block_id: string;
  scrubbed_text: string;
  pulse_score: number;
  rubric_breakdown: RubricBreakdown;
  attributions: XAIAttributionItem[];
  computed_at: string;
}

export interface CommitGoldenRecordResponse {
  meeting_id: string;
  project_id: string;
  status: string;
  pulse_score: number;
  group_scores: Record<string, GroupPulseMetric>;
  ephemeral_speaker_map: null;
  corrected_contexts_saved: number;
  promoted_risk_ids: string[];
  bigquery_rows_streamed: number;
  committed_at: string;
}

import { apiRequest } from "./client";

export async function fetchMeetingsList(
  idToken: string,
  projectId?: string
): Promise<MeetingRecord[]> {
  const qs = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return apiRequest<MeetingRecord[]>(`/meetings${qs}`, idToken);
}

export async function fetchAdjudicationWorkspace(
  idToken: string,
  meetingId: string
): Promise<AdjudicationWorkspaceData> {
  return apiRequest<AdjudicationWorkspaceData>(
    `/meetings/${encodeURIComponent(meetingId)}/adjudication`,
    idToken
  );
}

export async function splitDialogueBlock(
  idToken: string,
  meetingId: string,
  blockId: string,
  splitCharIndex: number
): Promise<{
  meeting_id: string;
  parent_block_id: string;
  child_blocks: DialogueBlock[];
  blocks: DialogueBlock[];
  pulse_score: number;
  group_scores: Record<string, GroupPulseMetric>;
}> {
  return apiRequest(
    `/meetings/${encodeURIComponent(meetingId)}/blocks/${encodeURIComponent(
      blockId
    )}/split`,
    idToken,
    {
      method: "POST",
      body: JSON.stringify({ split_char_index: splitCharIndex }),
    }
  );
}

export async function updateSessionSpeakerGrouping(
  idToken: string,
  meetingId: string,
  ephemeralSpeakerAccountId: string,
  groupName: string
): Promise<{
  meeting_id: string;
  ephemeral_speaker_map: Record<string, string>;
  updated_block_ids: string[];
  blocks: DialogueBlock[];
  pulse_score: number;
  group_scores: Record<string, GroupPulseMetric>;
}> {
  return apiRequest(
    `/meetings/${encodeURIComponent(meetingId)}/session-grouping`,
    idToken,
    {
      method: "PATCH",
      body: JSON.stringify({
        ephemeral_speaker_account_id: ephemeralSpeakerAccountId,
        group_name: groupName,
      }),
    }
  );
}

export async function updateDialogueBlockScoreOrGroup(
  idToken: string,
  meetingId: string,
  blockId: string,
  payload: {
    final_pulse_score?: number;
    group_name?: string;
    is_pinned?: boolean;
    text_scrubbed?: string;
  }
): Promise<{
  meeting_id: string;
  block: DialogueBlock;
  pulse_score: number;
  group_scores: Record<string, GroupPulseMetric>;
}> {
  return apiRequest(
    `/meetings/${encodeURIComponent(meetingId)}/blocks/${encodeURIComponent(
      blockId
    )}/score`,
    idToken,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    }
  );
}

export async function explainDialogueBlockRationale(
  idToken: string,
  meetingId: string,
  blockId: string
): Promise<BlockExplainResponse> {
  return apiRequest<BlockExplainResponse>(
    `/meetings/${encodeURIComponent(meetingId)}/blocks/${encodeURIComponent(
      blockId
    )}/explain`,
    idToken,
    {
      method: "POST",
    }
  );
}

export async function regenerateMeetingInsights(
  idToken: string,
  meetingId: string
): Promise<{
  status: string;
  pulse_score: number;
  group_scores: Record<string, GroupPulseMetric>;
  inference_mode: string;
  few_shot_count: number;
}> {
  return apiRequest(
    `/meetings/${encodeURIComponent(meetingId)}/regenerate-insights`,
    idToken,
    {
      method: "POST",
    }
  );
}

export async function commitGoldenRecord(
  idToken: string,
  meetingId: string,
  payload: {
    approved_risk_ids?: string[];
    dismissed_risk_ids?: string[];
    mom_summary?: MoMSummary | null;
    block_updates?: Array<{
      block_id: string;
      sentiment_score?: number | null;
      group_name?: string | null;
      is_human_overridden?: boolean;
      text_scrubbed?: string;
    }>;
  }
): Promise<CommitGoldenRecordResponse> {
  return apiRequest<CommitGoldenRecordResponse>(
    `/meetings/${encodeURIComponent(meetingId)}/commit-golden-record`,
    idToken,
    {
      method: "POST",
      body: JSON.stringify(payload),
    }
  );
}
