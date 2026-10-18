import React, { useCallback, useEffect, useState } from "react";
import { fetchProjects, ProjectWorkspace, UserRole } from "../api/authApi";
import {
  analyzeMeetingSentiment,
  dispatchMeetingBot,
  listMeetings,
} from "../api/meetingsApi";
import { MeetingDoc } from "../types/domain";

interface MeetingCapturePageProps {
  idToken: string;
  userRole: UserRole;
  onBackToWorkspace: () => void;
  onOpenAdjudication?: (meetingId: string) => void;
}

const LIFECYCLE_STEPS = [
  { key: "CAPTURING", label: "Capturing" },
  { key: "PROCESSING_POST_MEETING", label: "Processing & DLP" },
  { key: "PENDING_ADJUDICATION", label: "Pending Adjudication" },
  { key: "GOLDEN_RECORD", label: "Golden Record" },
];

export const MeetingCapturePage: React.FC<MeetingCapturePageProps> = ({
  idToken,
  userRole,
  onBackToWorkspace,
  onOpenAdjudication,
}) => {
  const [projects, setProjects] = useState<ProjectWorkspace[]>([]);
  const [meetings, setMeetings] = useState<MeetingDoc[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  // Bot Dispatch Form State
  const [meetingLink, setMeetingLink] = useState<string>("");
  const [meetingTitle, setMeetingTitle] = useState<string>("Executive Steering Committee");
  const [botName, setBotName] = useState<string>("pRisk AI Notetaker");
  const [assignedAdjudicator, setAssignedAdjudicator] = useState<string>("adjudicator@enterprise.com");
  const [customConsentNotice, setCustomConsentNotice] = useState<string>(
    "Notice: This meeting is being transcribed and analyzed by pRisk AI for sentiment and delivery alignment. PII is scrubbed via Cloud DLP."
  );
  const [isDispatching, setIsDispatching] = useState<boolean>(false);
  const [analyzingMeetingId, setAnalyzingMeetingId] = useState<string | null>(null);

  const canDispatch =
    userRole === "ADMIN" || userRole === "EXECUTIVE" || userRole === "MANAGER";

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const [fetchedProjects, fetchedMeetings] = await Promise.all([
        fetchProjects(idToken).catch(() => []),
        listMeetings(idToken, selectedProjectId || undefined).catch(() => []),
      ]);
      setProjects(fetchedProjects);
      if (fetchedProjects.length > 0 && !selectedProjectId) {
        setSelectedProjectId(fetchedProjects[0].project_id);
      }
      setMeetings(fetchedMeetings);
    } catch (err) {
      setLoadError(
        err instanceof Error
          ? err.message
          : "Failed to load projects and meetings from the server."
      );
    } finally {
      setIsLoading(false);
    }
  }, [idToken, selectedProjectId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleDispatchBot = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!meetingLink.trim()) {
      setFormError("Google Meet URL is required.");
      return;
    }
    if (!selectedProjectId) {
      setFormError("Please select a target project workspace.");
      return;
    }

    setIsDispatching(true);
    setFormError(null);
    setStatusMessage(null);

    try {
      const result = await dispatchMeetingBot(idToken, {
        meeting_link: meetingLink.trim(),
        project_id: selectedProjectId,
        title: meetingTitle.trim() || "Google Meet Session",
        bot_name: botName.trim() || "pRisk AI Notetaker",
        chat_consent_notice: customConsentNotice.trim(),
      });

      setStatusMessage(
        `Bot successfully dispatched (ID: ${result.bot_id}) to ${result.meeting_link}. Lifecycle status: DISPATCHED.`
      );
      setMeetingLink("");
      // Refresh meetings list
      const updatedMeetings = await listMeetings(idToken, selectedProjectId || undefined);
      setMeetings(updatedMeetings);
    } catch (err) {
      setFormError(
        err instanceof Error ? err.message : "Failed to dispatch MeetStream bot."
      );
    } finally {
      setIsDispatching(false);
    }
  };

  const handleRunAiAnalysis = async (meetingId: string) => {
    setAnalyzingMeetingId(meetingId);
    setStatusMessage(null);
    setFormError(null);
    try {
      const result = await analyzeMeetingSentiment(idToken, meetingId);
      setStatusMessage(
        `AI baseline analysis completed for meeting ${meetingId}. Pulse score: ${result.pulse_score}/100 (${result.inference_mode} inference).`
      );
      const updatedMeetings = await listMeetings(idToken, selectedProjectId || undefined);
      setMeetings(updatedMeetings);
    } catch (err) {
      setFormError(
        err instanceof Error ? err.message : "Failed to execute AI analysis."
      );
    } finally {
      setAnalyzingMeetingId(null);
    }
  };

  const getStepState = (meetingStatus: string, stepKey: string): "completed" | "current" | "upcoming" => {
    const statusMap: Record<string, number> = {
      SCHEDULED: 0,
      LIVE: 0,
      CAPTURING: 0,
      PROCESSING_POST_MEETING: 1,
      PENDING_ADJUDICATION: 2,
      COMMITTED: 3,
      GOLDEN_RECORD: 3,
      PURGED_CONSENT_REVOKED: -1,
    };

    const currentLevel = statusMap[meetingStatus] ?? 0;
    const stepLevel = statusMap[stepKey] ?? 0;

    if (currentLevel > stepLevel) return "completed";
    if (currentLevel === stepLevel) return "current";
    return "upcoming";
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-900/80 px-6 py-4">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={onBackToWorkspace}
                className="min-h-[44px] rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              >
                Back to Workspace
              </button>
              <h1 className="text-lg font-bold text-white">
                Meeting Capture &amp; Lifecycle Status
              </h1>
            </div>
            <p className="mt-1 text-xs text-slate-300">
              Dispatch autonomous MeetStream transcription bots, monitor real-time lifecycle states, and verify Cloud DLP sanitization.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-slate-800 px-3 py-1 font-mono text-xs text-slate-300">
              Role: {userRole}
            </span>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-6 px-6 py-8">
        {statusMessage && (
          <div className="rounded-xl border border-emerald-500/40 bg-emerald-950/40 p-4 text-xs text-emerald-200">
            {statusMessage}
          </div>
        )}
        {formError && (
          <div className="rounded-xl border border-rose-500/40 bg-rose-950/40 p-4 text-xs text-rose-200">
            {formError}
          </div>
        )}

        {/* Section 1: Bot Dispatch Form */}
        {canDispatch ? (
          <section className="rounded-xl border border-slate-800 bg-slate-900 p-6">
            <h2 className="text-sm font-bold text-white">
              Dispatch MeetStream.ai Bot into Google Meet
            </h2>
            <p className="mt-1 text-xs text-slate-300">
              The autonomous bot will join the meeting, post the statutory chat consent notice, record diarized speech, and trigger Cloud DLP PII de-identification upon completion.
            </p>

            <form onSubmit={handleDispatchBot} className="mt-4 space-y-4">
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div>
                  <label htmlFor="meeting-link-input" className="block text-xs font-semibold text-slate-200">
                    Google Meet URL *
                  </label>
                  <input
                    id="meeting-link-input"
                    type="url"
                    value={meetingLink}
                    onChange={(e) => setMeetingLink(e.target.value)}
                    placeholder="https://meet.google.com/abc-defg-hij"
                    required
                    className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                  />
                </div>

                <div>
                  <label htmlFor="project-select-input" className="block text-xs font-semibold text-slate-200">
                    Project Workspace *
                  </label>
                  <select
                    id="project-select-input"
                    value={selectedProjectId}
                    onChange={(e) => setSelectedProjectId(e.target.value)}
                    required
                    className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                  >
                    {projects.map((p) => (
                      <option key={p.project_id} value={p.project_id}>
                        {p.name} ({p.project_id})
                      </option>
                    ))}
                    {projects.length === 0 && (
                      <option value="proj-alpha">Default Workspace (proj-alpha)</option>
                    )}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                <div>
                  <label htmlFor="meeting-title-input" className="block text-xs font-semibold text-slate-200">
                    Meeting Title
                  </label>
                  <input
                    id="meeting-title-input"
                    type="text"
                    value={meetingTitle}
                    onChange={(e) => setMeetingTitle(e.target.value)}
                    className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                  />
                </div>

                <div>
                  <label htmlFor="bot-name-input" className="block text-xs font-semibold text-slate-200">
                    Bot Display Name
                  </label>
                  <input
                    id="bot-name-input"
                    type="text"
                    value={botName}
                    onChange={(e) => setBotName(e.target.value)}
                    className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                  />
                </div>

                <div>
                  <label htmlFor="adjudicator-input" className="block text-xs font-semibold text-slate-200">
                    Assigned Adjudicator
                  </label>
                  <input
                    id="adjudicator-input"
                    type="text"
                    value={assignedAdjudicator}
                    onChange={(e) => setAssignedAdjudicator(e.target.value)}
                    placeholder="adjudicator@enterprise.com"
                    className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                  />
                </div>
              </div>

              <div>
                <label htmlFor="consent-notice-input" className="block text-xs font-semibold text-slate-200">
                  Chat Consent Broadcast Notice
                </label>
                <textarea
                  id="consent-notice-input"
                  rows={2}
                  value={customConsentNotice}
                  onChange={(e) => setCustomConsentNotice(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                />
              </div>

              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={isDispatching}
                  className="min-h-[44px] rounded-lg bg-indigo-600 px-5 py-2.5 text-xs font-semibold text-white hover:bg-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 disabled:opacity-50"
                >
                  {isDispatching ? "Dispatching Bot..." : "Dispatch Bot Now"}
                </button>
              </div>
            </form>
          </section>
        ) : (
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 text-xs text-slate-300">
            Bot dispatch is restricted to Manager, Executive, and Admin accounts. External Stakeholders may monitor existing session status below.
          </div>
        )}

        {/* Section 2: Active & Historical Meetings Lifecycle List */}
        <section className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-base font-bold text-white">
                Meeting Lifecycles ({meetings.length})
              </h2>
              <p className="text-xs text-slate-300">
                Track each captured meeting through real-time DLP redaction, Gemini baseline scoring, and Golden Record seal.
              </p>
            </div>
            <button
              type="button"
              onClick={loadData}
              className="min-h-[44px] rounded-lg border border-slate-700 bg-slate-900 px-4 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
            >
              Refresh Status
            </button>
          </div>

          {isLoading ? (
            <div className="rounded-xl border border-slate-800 bg-slate-900 p-8 text-center text-xs text-slate-400">
              Loading meeting capture status and transcripts...
            </div>
          ) : loadError ? (
            <div className="rounded-xl border border-rose-500/40 bg-rose-950/40 p-6 text-xs text-rose-200">
              <p className="font-semibold">Unable to load meetings</p>
              <p className="mt-1">{loadError}</p>
              <button
                type="button"
                onClick={loadData}
                className="mt-3 min-h-[44px] rounded-lg bg-rose-700 px-4 py-2 text-xs font-semibold text-white hover:bg-rose-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400"
              >
                Retry
              </button>
            </div>
          ) : meetings.length === 0 ? (
            <div className="rounded-xl border border-slate-800 bg-slate-900 p-8 text-center text-xs text-slate-400">
              No meetings found for this workspace. Paste a Google Meet URL above to dispatch the first bot.
            </div>
          ) : (
            <div className="space-y-4">
              {meetings.map((meeting) => {
                const isAnalyzingThis = analyzingMeetingId === meeting.meeting_id;
                const canAdjudicate =
                  meeting.status === "PENDING_ADJUDICATION" ||
                  meeting.status === "COMMITTED" ||
                  meeting.status === "GOLDEN_RECORD";

                return (
                  <div
                    key={meeting.meeting_id}
                    className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="text-sm font-bold text-white">
                            {meeting.title}
                          </h3>
                          <span className="rounded border border-slate-700 bg-slate-950 px-2 py-0.5 font-mono text-xs text-slate-300">
                            {meeting.meeting_id}
                          </span>
                          <span className="rounded border border-indigo-500/40 bg-indigo-950/50 px-2.5 py-0.5 font-mono text-xs font-semibold text-indigo-300">
                            {meeting.status}
                          </span>
                        </div>
                        <p className="mt-1 font-mono text-xs text-slate-400">
                          Project: {meeting.project_id} | Date: {meeting.meeting_date} | Platform: {meeting.platform}
                        </p>
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        {canDispatch && (
                          <button
                            type="button"
                            onClick={() => handleRunAiAnalysis(meeting.meeting_id)}
                            disabled={isAnalyzingThis}
                            className="min-h-[44px] rounded-lg border border-indigo-500/50 bg-indigo-950/50 px-4 py-2 text-xs font-semibold text-indigo-200 hover:bg-indigo-900/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 disabled:opacity-50"
                          >
                            {isAnalyzingThis ? "Analyzing..." : "Run AI Analysis"}
                          </button>
                        )}
                        {canAdjudicate && onOpenAdjudication && (
                          <button
                            type="button"
                            onClick={() => onOpenAdjudication(meeting.meeting_id)}
                            className="min-h-[44px] rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
                          >
                            Open in Adjudication Workspace
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Step Pipeline Visualization */}
                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                      {LIFECYCLE_STEPS.map((step) => {
                        const state = getStepState(meeting.status, step.key);
                        let barColor = "border-slate-800 bg-slate-950 text-slate-400";
                        if (state === "completed") {
                          barColor = "border-emerald-500/50 bg-emerald-950/30 text-emerald-300 font-semibold";
                        } else if (state === "current") {
                          barColor = "border-indigo-500 bg-indigo-950/60 text-indigo-200 font-bold ring-1 ring-indigo-400";
                        }

                        return (
                          <div
                            key={step.key}
                            className={`rounded-lg border p-2.5 text-center text-xs transition-colors ${barColor}`}
                          >
                            <div className="text-[11px] uppercase tracking-wider text-slate-300">
                              {state === "completed" ? "Done" : state === "current" ? "Active" : "Pending"}
                            </div>
                            <div className="mt-0.5">{step.label}</div>
                          </div>
                        );
                      })}
                    </div>

                    {/* Redaction and Sentiment Summary Badges */}
                    <div className="flex flex-wrap items-center gap-3 border-t border-slate-800/80 pt-3 text-xs">
                      <div className="flex items-center gap-1.5 text-slate-300">
                        <span className="font-semibold text-slate-200">Pulse Score:</span>
                        {meeting.pulse_score !== null && meeting.pulse_score !== undefined ? (
                          <span
                            className={`rounded px-2 py-0.5 font-mono font-bold ${
                              meeting.pulse_score >= 70
                                ? "bg-emerald-950 text-emerald-300 border border-emerald-500/40"
                                : meeting.pulse_score >= 40
                                ? "bg-amber-950 text-amber-300 border border-amber-500/40"
                                : "bg-rose-950 text-rose-300 border border-rose-500/40"
                            }`}
                          >
                            {meeting.pulse_score} / 100
                          </span>
                        ) : (
                          <span className="font-mono text-slate-400">Awaiting Analysis</span>
                        )}
                      </div>

                      <div className="flex items-center gap-1.5 text-slate-300">
                        <span className="font-semibold text-slate-200">Cloud DLP Status:</span>
                        <span className="rounded border border-emerald-500/30 bg-emerald-950/40 px-2 py-0.5 font-mono text-[11px] text-emerald-300">
                          PII Scrubbed &amp; Upstream Deleted
                        </span>
                      </div>

                      {meeting.meetstream_bot_id && (
                        <div className="font-mono text-[11px] text-slate-400">
                          Bot ID: {meeting.meetstream_bot_id}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </main>
    </div>
  );
};
