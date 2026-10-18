import React, { useCallback, useEffect, useMemo, useState } from "react";
import { fetchProjects, ProjectWorkspace, UserRole } from "../api/authApi";
import { listMeetings } from "../api/meetingsApi";
import { MeetingDoc } from "../types/domain";

interface CalendarArchivePageProps {
  idToken: string;
  userRole: UserRole;
  onBackToWorkspace: () => void;
  onOpenAdjudication?: (meetingId: string) => void;
  onOpenCapture?: () => void;
}

const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

const DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export const CalendarArchivePage: React.FC<CalendarArchivePageProps> = ({
  idToken,
  userRole,
  onBackToWorkspace,
  onOpenAdjudication,
  onOpenCapture,
}) => {
  const [projects, setProjects] = useState<ProjectWorkspace[]>([]);
  const [meetings, setMeetings] = useState<MeetingDoc[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");

  const [currentDate, setCurrentDate] = useState<Date>(() => new Date());
  const [viewMode, setViewMode] = useState<"month" | "week">("month");

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [selectedMeetingId, setSelectedMeetingId] = useState<string | null>(null);
  const [compareMeetingIds, setCompareMeetingIds] = useState<string[]>([]);

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
          : "Failed to load calendar meetings."
      );
    } finally {
      setIsLoading(false);
    }
  }, [idToken, selectedProjectId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  // Calendar calculations
  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();

  const prevMonth = () => {
    setCurrentDate(new Date(year, month - 1, 1));
  };

  const nextMonth = () => {
    setCurrentDate(new Date(year, month + 1, 1));
  };

  const todayMonth = () => {
    setCurrentDate(new Date());
  };

  // Group meetings by date string (YYYY-MM-DD)
  const meetingsByDate = useMemo(() => {
    const map: Record<string, MeetingDoc[]> = {};
    for (const m of meetings) {
      if (!m.meeting_date) continue;
      const dateKey = m.meeting_date.slice(0, 10);
      if (!map[dateKey]) map[dateKey] = [];
      map[dateKey].push(m);
    }
    return map;
  }, [meetings]);

  // Days in month
  const calendarDays = useMemo(() => {
    const firstDay = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const days = [];

    // Leading empty days
    for (let i = 0; i < firstDay; i++) {
      days.push(null);
    }
    // Days in current month
    for (let d = 1; d <= daysInMonth; d++) {
      const dayStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(
        d
      ).padStart(2, "0")}`;
      days.push({ day: d, dateStr: dayStr });
    }
    return days;
  }, [year, month]);

  const selectedMeeting = useMemo(() => {
    return meetings.find((m) => m.meeting_id === selectedMeetingId) || null;
  }, [meetings, selectedMeetingId]);

  const comparedMeetings = useMemo(() => {
    return meetings.filter((m) => compareMeetingIds.includes(m.meeting_id));
  }, [meetings, compareMeetingIds]);

  const toggleCompareMeeting = (meetingId: string) => {
    setCompareMeetingIds((prev) =>
      prev.includes(meetingId)
        ? prev.filter((id) => id !== meetingId)
        : [...prev, meetingId]
    );
  };

  // Canonical groups union across compared meetings
  const comparisonGroups = useMemo(() => {
    const groupsSet = new Set<string>();
    for (const m of comparedMeetings) {
      if (m.group_scores) {
        for (const grp of Object.keys(m.group_scores)) {
          groupsSet.add(grp);
        }
      }
    }
    return Array.from(groupsSet);
  }, [comparedMeetings]);

  const getPulseBadge = (score?: number | null) => {
    if (score === null || score === undefined) {
      return {
        badgeClass: "bg-slate-800/80 text-slate-300 border-slate-700",
        dotClass: "bg-slate-500",
        label: "Unscored",
      };
    }
    if (score >= 70) {
      return {
        badgeClass: "bg-emerald-950/60 text-emerald-300 border-emerald-500/30",
        dotClass: "bg-emerald-400",
        label: `${score}/100`,
      };
    }
    if (score >= 40) {
      return {
        badgeClass: "bg-amber-950/60 text-amber-300 border-amber-500/30",
        dotClass: "bg-amber-400",
        label: `${score}/100`,
      };
    }
    return {
      badgeClass: "bg-rose-950/60 text-rose-300 border-rose-500/30",
      dotClass: "bg-rose-400",
      label: `${score}/100`,
    };
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-900/80 px-6 py-4">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4">
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
                Historical Meeting Calendar &amp; Longitudinal Archive
              </h1>
            </div>
            <p className="mt-1 text-xs text-slate-300">
              Browse past Google Meet sessions color-coded by sentiment pulse and compare group trajectories date-to-date.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {onOpenCapture && (
              <button
                type="button"
                onClick={onOpenCapture}
                className="min-h-[44px] rounded-lg border border-indigo-500/50 bg-indigo-950/50 px-4 py-2 text-xs font-semibold text-indigo-200 hover:bg-indigo-900/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              >
                Capture New Meeting
              </button>
            )}
            <span className="rounded-full bg-slate-800 px-3 py-1 font-mono text-xs text-slate-300">
              Role: {userRole}
            </span>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-6 px-6 py-8">
        {/* Controls Bar: Project Filter, Month Nav, View Toggle */}
        <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-800 bg-slate-900 p-4">
          <div className="flex flex-wrap items-center gap-3">
            <label htmlFor="calendar-project-select" className="text-xs font-semibold text-slate-300">
              Workspace:
            </label>
            <select
              id="calendar-project-select"
              value={selectedProjectId}
              onChange={(e) => setSelectedProjectId(e.target.value)}
              className="min-h-[44px] rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
            >
              <option value="">All Projects</option>
              {projects.map((p) => (
                <option key={p.project_id} value={p.project_id}>
                  {p.name} ({p.project_id})
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={prevMonth}
              className="min-h-[44px] rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
            >
              Previous
            </button>
            <span className="px-3 text-sm font-bold text-white">
              {MONTH_NAMES[month]} {year}
            </span>
            <button
              type="button"
              onClick={nextMonth}
              className="min-h-[44px] rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
            >
              Next
            </button>
            <button
              type="button"
              onClick={todayMonth}
              className="min-h-[44px] rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
            >
              Today
            </button>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setViewMode("month")}
              className={`min-h-[44px] rounded-lg px-3 py-1.5 text-xs font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 ${
                viewMode === "month"
                  ? "bg-indigo-600 text-white"
                  : "border border-slate-700 bg-slate-950 text-slate-300 hover:bg-slate-800"
              }`}
            >
              Month Grid
            </button>
            <button
              type="button"
              onClick={() => setViewMode("week")}
              className={`min-h-[44px] rounded-lg px-3 py-1.5 text-xs font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 ${
                viewMode === "week"
                  ? "bg-indigo-600 text-white"
                  : "border border-slate-700 bg-slate-950 text-slate-300 hover:bg-slate-800"
              }`}
            >
              Recent Week
            </button>
          </div>
        </div>

        {/* Legend */}
        <div className="flex flex-wrap items-center gap-4 text-xs text-slate-300">
          <span className="font-semibold text-slate-200">Pulse Health Legend:</span>
          <div className="flex items-center gap-1.5">
            <span className="h-3 w-3 rounded-full bg-emerald-500" />
            <span>Positive (&gt;= 70)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="h-3 w-3 rounded-full bg-amber-500" />
            <span>Neutral (40 to 69)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="h-3 w-3 rounded-full bg-rose-500" />
            <span>Alert / Friction (&lt; 40)</span>
          </div>
        </div>

        {/* Main Calendar Grid */}
        {isLoading ? (
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-12 text-center text-xs text-slate-400">
            Loading historical calendar records...
          </div>
        ) : loadError ? (
          <div className="rounded-xl border border-rose-500/40 bg-rose-950/40 p-6 text-xs text-rose-200">
            <p className="font-semibold">Unable to load calendar</p>
            <p className="mt-1">{loadError}</p>
          </div>
        ) : (
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
            {/* Header Row: Days of Week */}
            <div className="grid grid-cols-7 gap-2 border-b border-slate-800 pb-2 text-center text-xs font-bold text-slate-400">
              {DAY_NAMES.map((d) => (
                <div key={d}>{d}</div>
              ))}
            </div>

            {/* Days Grid */}
            <div className="mt-2 grid grid-cols-7 gap-2">
              {calendarDays.map((dayItem, idx) => {
                if (!dayItem) {
                  return (
                    <div
                      key={`empty-${idx}`}
                      className="min-h-[100px] rounded-lg bg-slate-950/30 p-2"
                    />
                  );
                }

                const dayMeetings = meetingsByDate[dayItem.dateStr] || [];
                const isSelectedDay = dayMeetings.some(
                  (m) => m.meeting_id === selectedMeetingId
                );

                return (
                  <div
                    key={dayItem.dateStr}
                    className={`min-h-[110px] rounded-lg border p-2 transition-colors ${
                      isSelectedDay
                        ? "border-indigo-500 bg-slate-900/90"
                        : "border-slate-800 bg-slate-950/60 hover:border-slate-700"
                    }`}
                  >
                    <div className="text-right text-xs font-bold text-slate-400">
                      {dayItem.day}
                    </div>

                    <div className="mt-1 space-y-1">
                      {dayMeetings.map((mtg) => {
                        const pulse = getPulseBadge(mtg.pulse_score);
                        const isCompared = compareMeetingIds.includes(
                          mtg.meeting_id
                        );

                        return (
                          <div
                            key={mtg.meeting_id}
                            className="group relative rounded-lg border border-slate-800 bg-slate-900/90 p-2 text-left text-xs transition-colors hover:border-slate-700 hover:bg-slate-900"
                          >
                            <div className="flex items-start justify-between gap-1.5">
                              <button
                                type="button"
                                onClick={() => setSelectedMeetingId(mtg.meeting_id)}
                                className="flex-1 truncate text-left font-medium text-slate-200 transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-indigo-400"
                                title={mtg.title}
                              >
                                {mtg.title}
                              </button>
                              <label
                                className="inline-flex shrink-0 cursor-pointer items-center"
                                title="Compare meeting date-to-date"
                              >
                                <input
                                  type="checkbox"
                                  checked={isCompared}
                                  onChange={() => toggleCompareMeeting(mtg.meeting_id)}
                                  aria-label={`Compare ${mtg.title}`}
                                  className="h-3.5 w-3.5 rounded border-slate-700 bg-slate-950 text-indigo-500 focus:ring-1 focus:ring-indigo-400 cursor-pointer"
                                />
                              </label>
                            </div>
                            <div className="mt-1.5 flex items-center justify-between font-mono text-[10px]">
                              <span
                                className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-medium ${pulse.badgeClass}`}
                              >
                                <span className={`h-1.5 w-1.5 rounded-full ${pulse.dotClass}`} />
                                {pulse.label}
                              </span>
                              <span className="text-slate-400">
                                {mtg.meeting_date?.slice(11, 16) || ""}
                              </span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Section 3: Selected Meeting Drill-Down Card */}
        {selectedMeeting && (
          <section className="rounded-xl border border-indigo-500/40 bg-slate-900 p-6 space-y-4">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <span className="text-xs font-semibold text-indigo-400 uppercase tracking-wider">
                  Inspected Meeting Details
                </span>
                <h3 className="mt-1 text-base font-bold text-white">
                  {selectedMeeting.title}
                </h3>
                <p className="font-mono text-xs text-slate-400">
                  ID: {selectedMeeting.meeting_id} | Project: {selectedMeeting.project_id} | Date: {selectedMeeting.meeting_date}
                </p>
              </div>

              <div className="flex items-center gap-3">
                <div className="text-right">
                  <div className="text-xs text-slate-400">Meeting Pulse</div>
                  <div
                    className={`font-mono text-base font-bold ${
                      (selectedMeeting.pulse_score ?? 0) >= 70
                        ? "text-emerald-400"
                        : (selectedMeeting.pulse_score ?? 0) >= 40
                        ? "text-amber-400"
                        : "text-rose-400"
                    }`}
                  >
                    {selectedMeeting.pulse_score !== null && selectedMeeting.pulse_score !== undefined
                      ? `${selectedMeeting.pulse_score} / 100`
                      : "Unscored"}
                  </div>
                </div>

                {onOpenAdjudication && (
                  <button
                    type="button"
                    onClick={() => onOpenAdjudication(selectedMeeting.meeting_id)}
                    className="min-h-[44px] rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                  >
                    Open Adjudication
                  </button>
                )}
              </div>
            </div>

            {/* Canonical Groups Pulse Breakdown */}
            {selectedMeeting.group_scores && Object.keys(selectedMeeting.group_scores).length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-slate-300">
                  Group Pulse Breakdown
                </h4>
                <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
                  {Object.entries(selectedMeeting.group_scores).map(([grp, metric]) => (
                    <div
                      key={grp}
                      className="rounded-lg border border-slate-800 bg-slate-950 p-3"
                    >
                      <div className="text-xs font-semibold text-slate-200">{grp}</div>
                      <div className="mt-1 font-mono text-sm font-bold text-indigo-300">
                        {metric.pulse_score} / 100
                      </div>
                      <div className="mt-1 text-[11px] text-slate-400">
                        {metric.block_count} dialogue blocks
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* MoM Executive Summary */}
            {selectedMeeting.mom_summary && (
              <div className="rounded-lg border border-slate-800 bg-slate-950 p-4">
                <h4 className="text-xs font-semibold text-slate-300">
                  Minutes of Meeting Summary
                </h4>
                <p className="mt-1 text-xs text-slate-300 leading-relaxed">
                  {typeof selectedMeeting.mom_summary === "string"
                    ? selectedMeeting.mom_summary
                    : selectedMeeting.mom_summary.summary || "No executive summary available."}
                </p>
              </div>
            )}
          </section>
        )}

        {/* Section 4: Longitudinal Group Pulse Comparison (FR-6.2) */}
        {comparedMeetings.length >= 2 && (
          <section className="rounded-xl border border-emerald-500/40 bg-slate-900 p-6 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h3 className="text-sm font-bold text-white">
                  Longitudinal Group Pulse Comparison ({comparedMeetings.length} Meetings Selected)
                </h3>
                <p className="text-xs text-slate-300">
                  Date-to-date group sentiment trajectory comparison as specified in FR-6.2.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setCompareMeetingIds([])}
                className="min-h-[44px] rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              >
                Clear Selection
              </button>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400">
                    <th className="py-2 pr-4 font-semibold">Stakeholder Group</th>
                    {comparedMeetings.map((m) => (
                      <th key={m.meeting_id} className="px-3 py-2 font-semibold">
                        <div className="truncate max-w-[140px] text-white" title={m.title}>
                          {m.title}
                        </div>
                        <div className="font-mono text-[10px] text-slate-400">
                          {m.meeting_date?.slice(0, 10)}
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  <tr className="font-bold text-white">
                    <td className="py-2.5 pr-4 text-indigo-300">Overall Meeting Pulse</td>
                    {comparedMeetings.map((m) => (
                      <td key={m.meeting_id} className="px-3 py-2.5 font-mono">
                        {m.pulse_score !== null && m.pulse_score !== undefined
                          ? `${m.pulse_score}`
                          : "Unscored"}
                      </td>
                    ))}
                  </tr>
                  {comparisonGroups.map((grp) => (
                    <tr key={grp} className="text-slate-300">
                      <td className="py-2 pr-4 font-semibold text-slate-200">{grp}</td>
                      {comparedMeetings.map((m) => {
                        const score = m.group_scores?.[grp]?.pulse_score;
                        return (
                          <td key={m.meeting_id} className="px-3 py-2 font-mono">
                            {score !== undefined ? (
                              <span
                                className={`rounded px-1.5 py-0.5 text-xs font-bold ${
                                  score >= 70
                                    ? "bg-emerald-950 text-emerald-300"
                                    : score >= 40
                                    ? "bg-amber-950 text-amber-300"
                                    : "bg-rose-950 text-rose-300"
                                }`}
                              >
                                {score}
                              </span>
                            ) : (
                              <span className="text-slate-500">N/A</span>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </main>
    </div>
  );
};
