import React, { useEffect } from "react";
import { ActionItem, GroupPulseMetric, MeetingRecord, MoMSummary } from "../api/adjudicationApi";
import { MeetingDoc } from "../types/domain";

export interface MeetingDetailsDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  meeting: MeetingRecord | MeetingDoc | null;
  onOpenAdjudication?: (meetingId: string) => void;
}

export const MeetingDetailsDrawer: React.FC<MeetingDetailsDrawerProps> = ({
  isOpen,
  onClose,
  meeting,
  onOpenAdjudication,
}) => {
  // ESC key listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen || !meeting) return null;

  const pulse = meeting.pulse_score ?? 50.0;
  const mom = meeting.mom_summary as MoMSummary | undefined;
  const groupScores = (meeting.group_scores || {}) as Record<
    string,
    GroupPulseMetric | { pulse_score: number; block_count?: number; top_liked_words?: string[]; top_disliked_words?: string[] }
  >;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="meeting-details-title"
      className="fixed inset-0 z-50 flex justify-end bg-black/75 backdrop-blur-sm transition-opacity"
      onClick={onClose}
    >
      <div
        className="flex h-full w-full max-w-2xl flex-col bg-slate-900 shadow-2xl border-l border-slate-800 text-slate-100 sm:max-w-xl md:max-w-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-5 bg-slate-950/90">
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded bg-sky-500/20 px-2 py-0.5 font-mono text-xs font-semibold text-sky-300 border border-sky-500/30">
                Meeting Drill-Down
              </span>
              <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-300">
                {meeting.meeting_id}
              </span>
            </div>
            <h2
              id="meeting-details-title"
              className="mt-1 text-base font-bold text-white tracking-tight"
            >
              {meeting.title || "Meeting Session Details"}
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              {new Date(meeting.meeting_date).toLocaleDateString(undefined, {
                weekday: "short",
                year: "numeric",
                month: "short",
                day: "numeric",
              })}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close meeting details drawer"
            className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg border border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
          >
            ✕
          </button>
        </div>

        {/* Scrollable Body */}
        <div className="flex-1 space-y-6 overflow-y-auto px-6 py-6">
          {/* Pulse Score Banner */}
          <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-800 bg-slate-950 p-4">
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Meeting Pulse Score
              </span>
              <div className="flex items-baseline gap-2 mt-1">
                <span className="text-2xl font-black text-white">{pulse}</span>
                <span className="text-xs text-slate-400">/ 100</span>
                <span
                  className={`ml-2 rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                    pulse >= 70
                      ? "bg-emerald-950 text-emerald-300 border border-emerald-500/40"
                      : pulse >= 40
                      ? "bg-amber-950 text-amber-300 border border-amber-500/40"
                      : "bg-rose-950 text-rose-300 border border-rose-500/40"
                  }`}
                >
                  {pulse >= 70
                    ? "Positive / Aligned"
                    : pulse >= 40
                    ? "Guarded / Neutral"
                    : "Critical / Negative"}
                </span>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span className="rounded bg-slate-800 px-3 py-1 font-mono text-xs text-slate-300">
                Status: {meeting.status}
              </span>
              {onOpenAdjudication && (
                <button
                  type="button"
                  onClick={() => onOpenAdjudication(meeting.meeting_id)}
                  className="min-h-[44px] rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                >
                  Open in HITL Workspace →
                </button>
              )}
            </div>
          </div>

          {/* AI Minutes of Meeting Summary */}
          <div className="rounded-xl border border-slate-800 bg-slate-950 p-5 space-y-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
              AI Minutes of Meeting (MoM)
            </h3>
            {mom ? (
              <div className="space-y-3 text-xs leading-relaxed text-slate-300">
                {mom.summary && (
                  <div>
                    <h4 className="font-semibold text-white mb-1">
                      Executive Summary
                    </h4>
                    <p className="bg-slate-900 rounded-lg p-3 text-slate-200 border border-slate-800">
                      {mom.summary}
                    </p>
                  </div>
                )}

                {mom.agenda && mom.agenda.length > 0 && (
                  <div>
                    <h4 className="font-semibold text-white mb-1">Agenda</h4>
                    <ul className="list-disc list-inside space-y-1 text-slate-300">
                      {mom.agenda.map((item, idx) => (
                        <li key={`agenda-${idx}`}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {mom.topics_of_discussion && mom.topics_of_discussion.length > 0 && (
                  <div>
                    <h4 className="font-semibold text-white mb-1">
                      Topics of Discussion
                    </h4>
                    <div className="flex flex-wrap gap-1.5">
                      {mom.topics_of_discussion.map((topic, idx) => (
                        <span
                          key={`topic-${idx}`}
                          className="rounded bg-slate-800 px-2.5 py-1 text-xs text-slate-200 border border-slate-700"
                        >
                          {topic}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-xs italic text-slate-400">
                No MoM summary generated for this meeting yet.
              </p>
            )}
          </div>

          {/* Group Sentiments & Keywords */}
          <div className="rounded-xl border border-slate-800 bg-slate-950 p-5 space-y-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
              Top Liked &amp; Disliked Words per Stakeholder Group
            </h3>
            {Object.keys(groupScores).length === 0 ? (
              <p className="text-xs italic text-slate-400">
                No group breakdown available.
              </p>
            ) : (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {Object.entries(groupScores).map(([grpName, metric]) => {
                  const grpPulse =
                    typeof metric === "object" && metric !== null
                      ? metric.pulse_score
                      : 50.0;
                  const liked =
                    typeof metric === "object" && metric !== null
                      ? metric.top_liked_words || []
                      : [];
                  const disliked =
                    typeof metric === "object" && metric !== null
                      ? metric.top_disliked_words || []
                      : [];

                  return (
                    <div
                      key={grpName}
                      className="rounded-lg border border-slate-800 bg-slate-900 p-3 space-y-2"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-xs text-white">
                          {grpName}
                        </span>
                        <span
                          className={`font-mono text-xs font-bold ${
                            grpPulse >= 70
                              ? "text-emerald-400"
                              : grpPulse >= 40
                              ? "text-amber-400"
                              : "text-rose-400"
                          }`}
                        >
                          {grpPulse} pts
                        </span>
                      </div>

                      {/* Top Liked */}
                      <div>
                        <span className="text-[11px] font-semibold text-emerald-400">
                          Top Liked:
                        </span>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {liked.length > 0 ? (
                            liked.map((w, idx) => (
                              <span
                                key={`liked-${idx}`}
                                className="rounded bg-emerald-950/70 border border-emerald-500/30 px-1.5 py-0.5 text-[11px] text-emerald-200"
                              >
                                {w}
                              </span>
                            ))
                          ) : (
                            <span className="text-[11px] text-slate-400 italic">
                              None
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Top Disliked */}
                      <div>
                        <span className="text-[11px] font-semibold text-rose-400">
                          Top Disliked:
                        </span>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {disliked.length > 0 ? (
                            disliked.map((w, idx) => (
                              <span
                                key={`disliked-${idx}`}
                                className="rounded bg-rose-950/70 border border-rose-500/30 px-1.5 py-0.5 text-[11px] text-rose-200"
                              >
                                {w}
                              </span>
                            ))
                          ) : (
                            <span className="text-[11px] text-slate-400 italic">
                              None
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Action Items */}
          <div className="rounded-xl border border-slate-800 bg-slate-950 p-5 space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
              Next Action Items ({mom?.action_items?.length || 0})
            </h3>
            {mom?.action_items && mom.action_items.length > 0 ? (
              <div className="space-y-2">
                {mom.action_items.map((item: ActionItem, idx: number) => (
                  <div
                    key={item.action_id || `act-${idx}`}
                    className="flex flex-wrap items-start justify-between gap-2 rounded-lg border border-slate-800 bg-slate-900 p-3 text-xs"
                  >
                    <div>
                      <p className="font-semibold text-white">
                        {item.description}
                      </p>
                      <span className="mt-1 inline-block rounded bg-indigo-950/60 border border-indigo-500/30 px-2 py-0.5 text-[11px] font-mono text-indigo-300">
                        Owner: {item.owner_group}
                      </span>
                    </div>
                    {item.due_date && (
                      <span className="font-mono text-[11px] text-slate-400">
                        Due: {item.due_date}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs italic text-slate-400">
                No action items recorded.
              </p>
            )}
          </div>

          {/* AI Recommended Mitigations */}
          <div className="rounded-xl border border-slate-800 bg-slate-950 p-5 space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
              AI Recommended Mitigations
            </h3>
            {mom?.recommended_mitigations &&
            mom.recommended_mitigations.length > 0 ? (
              <ul className="space-y-2 text-xs text-slate-300">
                {mom.recommended_mitigations.map((mitigation: string, idx: number) => (
                  <li
                    key={`mit-${idx}`}
                    className="flex items-start gap-2 rounded-lg border border-slate-800 bg-slate-900 p-3"
                  >
                    <span className="text-amber-400 font-bold">💡</span>
                    <span>{mitigation}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs italic text-slate-400">
                No recommended mitigations available.
              </p>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="border-t border-slate-800 bg-slate-950/90 px-6 py-4 flex justify-between items-center">
          <span className="text-xs text-slate-400">
            Platform: {meeting.platform || "Google Meet"}
          </span>
          <button
            type="button"
            onClick={onClose}
            className="min-h-[44px] rounded-lg bg-slate-800 px-5 py-2 text-xs font-semibold text-slate-100 hover:bg-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
          >
            Close Details
          </button>
        </div>
      </div>
    </div>
  );
};
