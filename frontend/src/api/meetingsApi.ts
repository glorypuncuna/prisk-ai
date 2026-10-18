import {
  MeetingDoc,
  ProjectVectorDiagnostics,
  PulseTrendsResponse,
} from "../types/domain";
import { apiRequest } from "./client";

export interface DispatchBotPayload {
  meeting_link: string;
  project_id: string;
  meeting_id?: string;
  title?: string;
  bot_name?: string;
  chat_consent_notice?: string;
}

export interface DispatchBotResponse {
  meeting_id: string;
  project_id: string;
  bot_id: string;
  transcript_id?: string | null;
  status: string;
  meeting_link: string;
  chat_consent_notice: string;
  dispatched_at: string;
}

export interface PostMeetingScoringResponse {
  status: string;
  pulse_score: number;
  group_scores: Record<string, unknown>;
  inference_mode: string;
  few_shot_count: number;
}

export async function listMeetings(
  idToken: string,
  projectId?: string
): Promise<MeetingDoc[]> {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return apiRequest<MeetingDoc[]>(`/meetings${query}`, idToken);
}

export async function getMeeting(
  idToken: string,
  meetingId: string
): Promise<MeetingDoc> {
  return apiRequest<MeetingDoc>(
    `/meetings/${encodeURIComponent(meetingId)}`,
    idToken
  );
}

export async function dispatchMeetingBot(
  idToken: string,
  payload: DispatchBotPayload
): Promise<DispatchBotResponse> {
  return apiRequest<DispatchBotResponse>("/meetings/dispatch-bot", idToken, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function analyzeMeetingSentiment(
  idToken: string,
  meetingId: string
): Promise<PostMeetingScoringResponse> {
  return apiRequest<PostMeetingScoringResponse>(
    `/meetings/${encodeURIComponent(meetingId)}/analyze`,
    idToken,
    {
      method: "POST",
    }
  );
}

export async function regenerateMeetingInsights(
  idToken: string,
  meetingId: string
): Promise<PostMeetingScoringResponse> {
  return apiRequest<PostMeetingScoringResponse>(
    `/meetings/${encodeURIComponent(meetingId)}/regenerate-insights`,
    idToken,
    {
      method: "POST",
    }
  );
}

export async function fetchProjectVectorDiagnostics(
  idToken: string,
  projectId: string
): Promise<ProjectVectorDiagnostics> {
  return apiRequest<ProjectVectorDiagnostics>(
    `/projects/${encodeURIComponent(projectId)}/vector-diagnostics`,
    idToken
  );
}

export async function fetchPulseTrends(
  idToken: string,
  params?: {
    projectId?: string;
    timeWindow?: string;
    startDate?: string;
    endDate?: string;
  }
): Promise<PulseTrendsResponse> {
  const query = new URLSearchParams();
  if (params?.projectId) query.append("project_id", params.projectId);
  if (params?.timeWindow) query.append("time_window", params.timeWindow);
  if (params?.startDate) query.append("start_date", params.startDate);
  if (params?.endDate) query.append("end_date", params.endDate);
  const qStr = query.toString() ? `?${query.toString()}` : "";
  return apiRequest<PulseTrendsResponse>(`/analytics/pulse-trends${qStr}`, idToken);
}

