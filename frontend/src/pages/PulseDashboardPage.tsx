import React, { useCallback, useEffect, useMemo, useState } from "react";
import { fetchMeetingsList } from "../api/adjudicationApi";
import { fetchPulseTrends } from "../api/meetingsApi";
import { MeetingDetailsDrawer } from "../components/MeetingDetailsDrawer";
import { XaiRationaleDrawer } from "../components/XaiRationaleDrawer";
import {
  MeetingDoc,
  PulseTrendPoint,
  PulseTrendsResponse,
} from "../types/domain";

export interface PulseDashboardPageProps {
  idToken: string;
  onBackToWorkspace: () => void;
  onOpenAdjudication?: (meetingId: string) => void;
}

type TimeWindowOption = "7D" | "30D" | "QTD" | "Custom";

interface WidgetVisibility {
  metrics: boolean;
  aiCommentary: boolean;
  chart: boolean;
  groupBreakdown: boolean;
  table: boolean;
}

export const PulseDashboardPage: React.FC<PulseDashboardPageProps> = ({
  idToken,
  onBackToWorkspace,
  onOpenAdjudication,
}) => {
  // Filters state
  const [timeWindow, setTimeWindow] = useState<TimeWindowOption>("30D");
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");
  const [selectedProjectId, setSelectedProjectId] = useState<string>("ALL");
  const [availableProjects, setAvailableProjects] = useState<string[]>([
    "proj-alpha",
  ]);

  // Data state
  const [trendsData, setTrendsData] = useState<PulseTrendsResponse | null>(null);
  const [meetings, setMeetings] = useState<MeetingDoc[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Widget customizer state
  const [widgets, setWidgets] = useState<WidgetVisibility>({
    metrics: true,
    aiCommentary: true,
    chart: true,
    groupBreakdown: true,
    table: true,
  });
  const [showWidgetSettings, setShowWidgetSettings] = useState<boolean>(false);

  // Drill-down drawers state
  const [selectedMeeting, setSelectedMeeting] = useState<MeetingDoc | null>(
    null
  );
  const [isDetailsDrawerOpen, setIsDetailsDrawerOpen] = useState<boolean>(false);
  const [isXaiDrawerOpen, setIsXaiDrawerOpen] = useState<boolean>(false);
  const [activeXaiBlockText] = useState<string>(
    "The regulatory compliance audit was approved by legal with zero critical defects, but deployment schedules remain tight."
  );

  // Chart hover state
  const [hoveredPoint, setHoveredPoint] = useState<PulseTrendPoint | null>(null);

  // Load trends & meetings
  const loadDashboardData = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const mtgList = await fetchMeetingsList(idToken).catch(() => []);
      setMeetings(mtgList as MeetingDoc[]);

      const pids = Array.from(
        new Set(mtgList.map((m) => m.project_id || "proj-alpha"))
      );
      if (pids.length > 0) {
        setAvailableProjects(pids);
      }

      const res = await fetchPulseTrends(idToken, {
        projectId: selectedProjectId === "ALL" ? undefined : selectedProjectId,
        timeWindow,
        startDate: timeWindow === "Custom" ? startDate : undefined,
        endDate: timeWindow === "Custom" ? endDate : undefined,
      });
      setTrendsData(res);
    } catch (err) {
      setErrorMessage(
        err instanceof Error
          ? err.message
          : "Failed to load Pulse & Health analytics"
      );
    } finally {
      setIsLoading(false);
    }
  }, [idToken, selectedProjectId, timeWindow, startDate, endDate]);

  useEffect(() => {
    void loadDashboardData();
  }, [loadDashboardData]);

  // Points filtered by project if user toggles overlay
  const filteredPoints = useMemo(() => {
    if (!trendsData) return [];
    if (selectedProjectId === "ALL") return trendsData.trajectory_points;
    return trendsData.trajectory_points.filter(
      (p) => p.project_id === selectedProjectId
    );
  }, [trendsData, selectedProjectId]);

  // Export CSV
  const handleExportCsv = () => {
    if (!filteredPoints.length) return;
    const headers = [
      "Meeting ID",
      "Project ID",
      "Title",
      "Meeting Date",
      "Pulse Score",
      "Status",
    ];
    const rows = filteredPoints.map((p) => [
      `"${p.meeting_id}"`,
      `"${p.project_id}"`,
      `"${p.title.replace(/"/g, '""')}"`,
      `"${p.meeting_date}"`,
      p.pulse_score,
      `"${p.status}"`,
    ]);
    const csvContent =
      "data:text/csv;charset=utf-8," +
      [headers.join(","), ...rows.map((e) => e.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute(
      "download",
      `prisk_pulse_trends_${timeWindow}_${new Date()
        .toISOString()
        .slice(0, 10)}.csv`
    );
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Export PDF via Print View
  const handleExportPdf = () => {
    window.print();
  };

  // Export PNG snapshot placeholder
  const handleExportPng = () => {
    const chartSvg = document.getElementById("pulse-trajectory-svg");
    if (!chartSvg) return;
    const svgData = new XMLSerializer().serializeToString(chartSvg);
    const canvas = document.createElement("canvas");
    canvas.width = 1000;
    canvas.height = 400;
    const ctx = canvas.getContext("2d");
    const img = new Image();
    img.setAttribute(
      "src",
      "data:image/svg+xml;base64," + btoa(unescape(encodeURIComponent(svgData)))
    );
    img.onload = () => {
      if (ctx) {
        ctx.fillStyle = "#020617";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0);
        const pngUrl = canvas.toDataURL("image/png");
        const downloadLink = document.createElement("a");
        downloadLink.download = `prisk_pulse_chart_${new Date()
          .toISOString()
          .slice(0, 10)}.png`;
        downloadLink.href = pngUrl;
        downloadLink.click();
      }
    };
  };

  const handleNodeClick = (meetingId: string) => {
    const found = meetings.find((m) => m.meeting_id === meetingId);
    if (found) {
      setSelectedMeeting(found);
    } else {
      setSelectedMeeting({
        meeting_id: meetingId,
        project_id: selectedProjectId === "ALL" ? "proj-alpha" : selectedProjectId,
        title: `Meeting ${meetingId}`,
        meeting_date: new Date().toISOString(),
        platform: "google_meet",
        status: "GOLDEN_RECORD",
        pulse_score: 65.0,
        group_scores: {},
        participants: [],
        created_at: new Date().toISOString(),
      });
    }
    setIsDetailsDrawerOpen(true);
  };

  // Interactive SVG Multi-Series Line Chart Dimensions
  const chartWidth = 900;
  const chartHeight = 280;
  const padding = { top: 20, right: 30, bottom: 40, left: 50 };
  const innerWidth = chartWidth - padding.left - padding.right;
  const innerHeight = chartHeight - padding.top - padding.bottom;

  const pointsCount = filteredPoints.length;
  const coordinates = useMemo(() => {
    if (pointsCount === 0) return [];
    return filteredPoints.map((pt, idx) => {
      const x =
        padding.left +
        (pointsCount === 1 ? innerWidth / 2 : (idx / (pointsCount - 1)) * innerWidth);
      const y =
        padding.top +
        innerHeight -
        (Math.max(0, Math.min(100, pt.pulse_score)) / 100) * innerHeight;
      return { x, y, point: pt };
    });
  }, [filteredPoints, pointsCount, innerWidth, innerHeight, padding]);

  const polylinePoints = coordinates.map((c) => `${c.x},${c.y}`).join(" ");

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 pb-16">
      {/* Top Header */}
      <header className="border-b border-slate-800 bg-slate-900/80 px-6 py-4 sticky top-0 z-40 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onBackToWorkspace}
              className="min-h-[44px] rounded-lg border border-slate-700 bg-slate-800 px-3.5 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
            >
              ← Workspace
            </button>
            <div>
              <h1 className="text-lg font-bold text-white flex items-center gap-2">
                Pulse &amp; Health Analytics Dashboard
                <span className="rounded bg-indigo-500/20 px-2 py-0.5 text-xs font-mono font-semibold text-indigo-300 border border-indigo-500/30">
                  TRD §10.4
                </span>
              </h1>
              <p className="text-xs text-slate-400">
                Longitudinal group sentiment trajectories, AI drop explainer &amp; interactive drill-down drawers
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            {/* Export Controls */}
            <div className="flex items-center rounded-lg border border-slate-700 bg-slate-800 p-1">
              <button
                type="button"
                onClick={handleExportCsv}
                disabled={isLoading || !filteredPoints.length}
                title="Export trajectory data as CSV"
                className="min-h-[38px] rounded px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700 hover:text-white disabled:opacity-50"
              >
                CSV
              </button>
              <button
                type="button"
                onClick={handleExportPdf}
                disabled={isLoading}
                title="Print / Save as PDF"
                className="min-h-[38px] rounded px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700 hover:text-white disabled:opacity-50"
              >
                PDF
              </button>
              <button
                type="button"
                onClick={handleExportPng}
                disabled={isLoading || !filteredPoints.length}
                title="Download SVG Chart as PNG"
                className="min-h-[38px] rounded px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700 hover:text-white disabled:opacity-50"
              >
                PNG
              </button>
            </div>

            {/* Widget layout toggle */}
            <button
              type="button"
              onClick={() => setShowWidgetSettings(!showWidgetSettings)}
              className="min-h-[44px] rounded-lg border border-slate-700 bg-slate-800 px-3.5 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
            >
              ⚙ Customize Widgets
            </button>

            {/* Test XAI Button */}
            <button
              type="button"
              onClick={() => setIsXaiDrawerOpen(true)}
              className="min-h-[44px] rounded-lg border border-indigo-500/40 bg-indigo-950/60 px-4 py-2 text-xs font-semibold text-indigo-200 hover:bg-indigo-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
            >
              Inline XAI Highlighter
            </button>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="mx-auto max-w-7xl px-6 py-8 space-y-6">
        {/* Widget Customizer Modal / Drawer */}
        {showWidgetSettings && (
          <div className="rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold uppercase tracking-wider text-white">
                Customize Dashboard Widgets (Layout Grid)
              </h3>
              <button
                type="button"
                onClick={() => setShowWidgetSettings(false)}
                className="text-xs text-slate-400 hover:text-white"
              >
                ✕ Close
              </button>
            </div>
            <div className="flex flex-wrap gap-4 text-xs">
              <label className="flex items-center gap-2 cursor-pointer text-slate-200">
                <input
                  type="checkbox"
                  checked={widgets.metrics}
                  onChange={(e) =>
                    setWidgets({ ...widgets, metrics: e.target.checked })
                  }
                  className="rounded border-slate-700 bg-slate-800 text-indigo-500"
                />
                Aggregate Metrics
              </label>
              <label className="flex items-center gap-2 cursor-pointer text-slate-200">
                <input
                  type="checkbox"
                  checked={widgets.aiCommentary}
                  onChange={(e) =>
                    setWidgets({ ...widgets, aiCommentary: e.target.checked })
                  }
                  className="rounded border-slate-700 bg-slate-800 text-indigo-500"
                />
                AI Trajectory Commentary
              </label>
              <label className="flex items-center gap-2 cursor-pointer text-slate-200">
                <input
                  type="checkbox"
                  checked={widgets.chart}
                  onChange={(e) =>
                    setWidgets({ ...widgets, chart: e.target.checked })
                  }
                  className="rounded border-slate-700 bg-slate-800 text-indigo-500"
                />
                Trajectory Multi-Series Line Chart
              </label>
              <label className="flex items-center gap-2 cursor-pointer text-slate-200">
                <input
                  type="checkbox"
                  checked={widgets.groupBreakdown}
                  onChange={(e) =>
                    setWidgets({ ...widgets, groupBreakdown: e.target.checked })
                  }
                  className="rounded border-slate-700 bg-slate-800 text-indigo-500"
                />
                Stakeholder Group Breakdown
              </label>
              <label className="flex items-center gap-2 cursor-pointer text-slate-200">
                <input
                  type="checkbox"
                  checked={widgets.table}
                  onChange={(e) =>
                    setWidgets({ ...widgets, table: e.target.checked })
                  }
                  className="rounded border-slate-700 bg-slate-800 text-indigo-500"
                />
                Session Trajectory Table
              </label>
            </div>
          </div>
        )}

        {/* Filter Controls Bar */}
        <section className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-800 bg-slate-900 p-4">
          {/* Time Window Buttons */}
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-400">Window:</span>
            {(["7D", "30D", "QTD", "Custom"] as TimeWindowOption[]).map(
              (opt) => (
                <button
                  key={opt}
                  type="button"
                  onClick={() => setTimeWindow(opt)}
                  className={`min-h-[44px] rounded-lg px-3.5 py-2 text-xs font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 ${
                    timeWindow === opt
                      ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/30"
                      : "bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white"
                  }`}
                >
                  {opt}
                </button>
              )
            )}
          </div>

          {/* Custom Date Pickers */}
          {timeWindow === "Custom" && (
            <div className="flex items-center gap-2 text-xs">
              <div>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="min-h-[44px] rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                />
              </div>
              <span className="text-slate-400">to</span>
              <div>
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="min-h-[44px] rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                />
              </div>
            </div>
          )}

          {/* Project Overlay Selector */}
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-400">
              Project Overlay:
            </span>
            <select
              value={selectedProjectId}
              onChange={(e) => setSelectedProjectId(e.target.value)}
              aria-label="Filter project workspace overlay"
              className="min-h-[44px] rounded-lg border border-slate-700 bg-slate-950 px-3.5 py-2 text-xs font-semibold text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
            >
              <option value="ALL">All Projects (Portfolio Overlay)</option>
              {availableProjects.map((pid) => (
                <option key={pid} value={pid}>
                  {pid}
                </option>
              ))}
            </select>
          </div>
        </section>

        {errorMessage && (
          <div
            role="alert"
            className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 rounded-xl border border-rose-500/40 bg-rose-950/40 p-4 text-xs text-rose-200"
          >
            <div>
              <p className="font-semibold text-rose-100">Analytics Service Notice</p>
              <p className="mt-0.5 text-rose-300">{errorMessage}</p>
            </div>
            <button
              type="button"
              onClick={() => void loadDashboardData()}
              className="min-h-[38px] shrink-0 rounded-lg border border-rose-500/50 bg-rose-900/60 px-3.5 py-1.5 font-semibold text-rose-100 hover:bg-rose-800 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400"
            >
              Retry
            </button>
          </div>
        )}

        {/* Widget 1: Aggregate Metrics */}
        {widgets.metrics && trendsData && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Average Pulse ({timeWindow})
              </span>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-3xl font-black text-white">
                  {trendsData.aggregate_metrics.average_pulse}
                </span>
                <span className="text-xs text-slate-400">/ 100</span>
              </div>
              <p className="mt-1 text-[11px] text-slate-400">
                Calculated across {trendsData.aggregate_metrics.total_meetings}{" "}
                session(s)
              </p>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Net Trajectory Shift
              </span>
              <div className="mt-2 flex items-baseline gap-2">
                <span
                  className={`text-3xl font-black ${
                    trendsData.aggregate_metrics.pulse_change >= 0
                      ? "text-emerald-400"
                      : "text-rose-400"
                  }`}
                >
                  {trendsData.aggregate_metrics.pulse_change >= 0 ? "+" : ""}
                  {trendsData.aggregate_metrics.pulse_change}
                </span>
                <span className="text-xs text-slate-400">pts</span>
              </div>
              <p className="mt-1 text-[11px] text-slate-400">
                {trendsData.aggregate_metrics.pulse_change >= 0
                  ? "Strengthening cross-group alignment"
                  : "Deteriorating group sentiment"}
              </p>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Lowest Session Pulse
              </span>
              {trendsData.aggregate_metrics.lowest_pulse_meeting ? (
                <div className="mt-2">
                  <div className="flex items-baseline gap-2">
                    <span className="text-3xl font-black text-rose-400">
                      {trendsData.aggregate_metrics.lowest_pulse_meeting.pulse_score}
                    </span>
                    <span className="text-xs text-slate-400">pts</span>
                  </div>
                  <p className="mt-1 text-[11px] text-slate-300 truncate font-semibold">
                    {trendsData.aggregate_metrics.lowest_pulse_meeting.title}
                  </p>
                </div>
              ) : (
                <p className="mt-2 text-xs text-slate-400 italic">None</p>
              )}
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Peak Alignment Pulse
              </span>
              {trendsData.aggregate_metrics.highest_pulse_meeting ? (
                <div className="mt-2">
                  <div className="flex items-baseline gap-2">
                    <span className="text-3xl font-black text-emerald-400">
                      {trendsData.aggregate_metrics.highest_pulse_meeting.pulse_score}
                    </span>
                    <span className="text-xs text-slate-400">pts</span>
                  </div>
                  <p className="mt-1 text-[11px] text-slate-300 truncate font-semibold">
                    {trendsData.aggregate_metrics.highest_pulse_meeting.title}
                  </p>
                </div>
              ) : (
                <p className="mt-2 text-xs text-slate-400 italic">None</p>
              )}
            </div>
          </div>
        )}

        {/* Widget 2: AI Longitudinal Commentary */}
        {widgets.aiCommentary && trendsData?.ai_commentary && (
          <div className="rounded-xl border border-indigo-500/30 bg-slate-900 p-6 space-y-4 shadow-xl">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="rounded bg-indigo-500/20 px-2.5 py-0.5 text-xs font-bold text-indigo-300 border border-indigo-500/30">
                  ✨ Gemini 2.5 Flash Longitudinal Synthesis
                </span>
                <span className="text-xs text-slate-400 font-mono">
                  Window: {trendsData.time_window}
                </span>
              </div>
            </div>

            <h2 className="text-base font-bold text-white tracking-tight">
              {trendsData.ai_commentary.headline}
            </h2>

            <p className="text-xs leading-relaxed text-slate-300">
              {trendsData.ai_commentary.trajectory_summary}
            </p>

            {trendsData.ai_commentary.risk_warning && (
              <div className="rounded-lg border border-rose-500/60 bg-rose-950/70 p-3 text-xs text-rose-200 flex items-start gap-2">
                <span className="text-rose-400 font-bold">⚠️</span>
                <span>{trendsData.ai_commentary.risk_warning}</span>
              </div>
            )}

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 pt-2 border-t border-slate-800">
              {/* Key Drivers */}
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
                  Key Drivers of Pulse Shifts
                </h4>
                <ul className="space-y-1.5 text-xs text-slate-300">
                  {trendsData.ai_commentary.key_drivers_of_shifts.map(
                    (driver, idx) => (
                      <li key={`driver-${idx}`} className="flex items-start gap-2">
                        <span className="text-indigo-400 font-bold">›</span>
                        <span>{driver}</span>
                      </li>
                    )
                  )}
                </ul>
              </div>

              {/* Recommended Interventions */}
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
                  Actionable Interventions
                </h4>
                <ul className="space-y-1.5 text-xs text-slate-300">
                  {trendsData.ai_commentary.recommended_interventions.map(
                    (rec, idx) => (
                      <li key={`rec-${idx}`} className="flex items-start gap-2">
                        <span className="text-emerald-400 font-bold">✓</span>
                        <span>{rec}</span>
                      </li>
                    )
                  )}
                </ul>
              </div>
            </div>
          </div>
        )}

        {/* Widget 3: Multi-Series Pulse Trajectory Line Chart */}
        {widgets.chart && (
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="text-base font-bold text-white">
                  Multi-Series Pulse Trajectory Line Chart
                </h3>
                <p className="text-xs text-slate-400">
                  Click any meeting node to open the drill-down details drawer
                </p>
              </div>

              {/* Legend */}
              <div className="flex items-center gap-4 text-xs font-medium">
                <span className="flex items-center gap-1.5 text-emerald-400">
                  <span className="inline-block h-3 w-3 rounded-full bg-emerald-500" />
                  Positive (&gt;= 70)
                </span>
                <span className="flex items-center gap-1.5 text-amber-400">
                  <span className="inline-block h-3 w-3 rounded-full bg-amber-500" />
                  Neutral (40–69)
                </span>
                <span className="flex items-center gap-1.5 text-rose-400">
                  <span className="inline-block h-3 w-3 rounded-full bg-rose-500" />
                  Critical (&lt; 40)
                </span>
              </div>
            </div>

            {/* SVG Chart */}
            <div className="w-full overflow-x-auto">
              {filteredPoints.length === 0 ? (
                <div className="flex h-56 flex-col items-center justify-center text-xs text-slate-400">
                  No meeting trajectory points found in this time horizon.
                </div>
              ) : (
                <div className="relative">
                  <svg
                    id="pulse-trajectory-svg"
                    viewBox={`0 0 ${chartWidth} ${chartHeight}`}
                    className="w-full h-auto min-w-[700px] select-none"
                  >
                    {/* Gridlines */}
                    {[0, 25, 50, 75, 100].map((level) => {
                      const y =
                        padding.top +
                        innerHeight -
                        (level / 100) * innerHeight;
                      return (
                        <g key={`grid-${level}`}>
                          <line
                            x1={padding.left}
                            y1={y}
                            x2={chartWidth - padding.right}
                            y2={y}
                            stroke="#334155"
                            strokeDasharray="4,4"
                            strokeWidth="1"
                          />
                          <text
                            x={padding.left - 10}
                            y={y + 4}
                            textAnchor="end"
                            fontSize="11"
                            fill="#94a3b8"
                            fontFamily="monospace"
                          >
                            {level}
                          </text>
                        </g>
                      );
                    })}

                    {/* Threshold Alert Line (Score 40) */}
                    <line
                      x1={padding.left}
                      y1={
                        padding.top +
                        innerHeight -
                        (40 / 100) * innerHeight
                      }
                      x2={chartWidth - padding.right}
                      y2={
                        padding.top +
                        innerHeight -
                        (40 / 100) * innerHeight
                      }
                      stroke="#f43f5e"
                      strokeWidth="1.5"
                      strokeOpacity="0.8"
                    />
                    <text
                      x={chartWidth - padding.right}
                      y={
                        padding.top +
                        innerHeight -
                        (40 / 100) * innerHeight -
                        4
                      }
                      textAnchor="end"
                      fontSize="10"
                      fill="#f43f5e"
                      fontFamily="monospace"
                    >
                      Threshold (40 pts)
                    </text>

                    {/* Trajectory Polyline */}
                    {polylinePoints && (
                      <polyline
                        fill="none"
                        stroke="#6366f1"
                        strokeWidth="3"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        points={polylinePoints}
                      />
                    )}

                    {/* Data Node Circles */}
                    {coordinates.map((c, idx) => {
                      const score = c.point.pulse_score;
                      const fillColor =
                        score >= 70
                          ? "#10b981"
                          : score >= 40
                          ? "#f59e0b"
                          : "#f43f5e";
                      const isHovered =
                        hoveredPoint?.meeting_id === c.point.meeting_id;

                      return (
                        <g
                          key={`node-${c.point.meeting_id}-${idx}`}
                          onClick={() => handleNodeClick(c.point.meeting_id)}
                          onMouseEnter={() => setHoveredPoint(c.point)}
                          onMouseLeave={() => setHoveredPoint(null)}
                          className="cursor-pointer transition-transform"
                        >
                          <circle
                            cx={c.x}
                            cy={c.y}
                            r={isHovered ? 8 : 6}
                            fill={fillColor}
                            stroke="#0f172a"
                            strokeWidth="2.5"
                          />
                          {/* Label below axis */}
                          <text
                            x={c.x}
                            y={chartHeight - 12}
                            textAnchor="middle"
                            fontSize="10"
                            fill="#94a3b8"
                            fontFamily="monospace"
                          >
                            {c.point.meeting_date.slice(5, 10)}
                          </text>
                        </g>
                      );
                    })}
                  </svg>

                  {/* Node Hover Tooltip Card */}
                  {hoveredPoint && (
                    <div className="absolute top-2 right-4 rounded-xl border border-slate-700 bg-slate-900/95 p-3 text-xs shadow-2xl backdrop-blur max-w-xs pointer-events-none">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-bold text-white">
                          {hoveredPoint.title}
                        </span>
                        <span className="font-mono text-emerald-300 font-bold">
                          {hoveredPoint.pulse_score} pts
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400 mt-0.5">
                        {hoveredPoint.meeting_date.slice(0, 10)} | Project:{" "}
                        {hoveredPoint.project_id}
                      </p>
                      <p className="text-[11px] text-indigo-300 mt-1 font-semibold">
                        Click node for full MoM &amp; Group breakdown →
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Widget 4: Group Sentiment Breakdown */}
        {widgets.groupBreakdown && trendsData && (
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4">
            <h3 className="text-base font-bold text-white">
              Longitudinal Group Trends &amp; Sentiment Averages
            </h3>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {Object.entries(trendsData.aggregate_metrics.group_averages).map(
                ([grpName, avgScore]) => {
                  const trendComment =
                    trendsData.ai_commentary.group_trends[grpName] ||
                    `Average pulse score: ${avgScore} pts`;
                  return (
                    <div
                      key={grpName}
                      className="rounded-xl border border-slate-800 bg-slate-950 p-4 space-y-2"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-xs text-white">
                          {grpName}
                        </span>
                        <span
                          className={`font-mono text-xs font-bold ${
                            avgScore >= 70
                              ? "text-emerald-400"
                              : avgScore >= 40
                              ? "text-amber-400"
                              : "text-rose-400"
                          }`}
                        >
                          {avgScore} pts
                        </span>
                      </div>
                      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
                        <div
                          className={`h-full ${
                            avgScore >= 70
                              ? "bg-emerald-500"
                              : avgScore >= 40
                              ? "bg-amber-500"
                              : "bg-rose-500"
                          }`}
                          style={{ width: `${Math.min(100, avgScore)}%` }}
                        />
                      </div>
                      <p className="text-xs text-slate-300 leading-relaxed">
                        {trendComment}
                      </p>
                    </div>
                  );
                }
              )}
            </div>
          </div>
        )}

        {/* Widget 5: Trajectory Data Table */}
        {widgets.table && (
          <div className="rounded-xl border border-slate-800 bg-slate-900 overflow-hidden shadow-xl">
            <div className="px-6 py-4 border-b border-slate-800 bg-slate-950/60 flex items-center justify-between">
              <h3 className="text-xs font-bold uppercase tracking-wider text-white">
                Meeting Trajectory History ({filteredPoints.length})
              </h3>
              <span className="text-xs text-slate-400">
                Sorted chronologically
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-200">
                <thead className="bg-slate-950 text-slate-400 border-b border-slate-800">
                  <tr>
                    <th className="px-6 py-3 font-semibold">Date</th>
                    <th className="px-6 py-3 font-semibold">Meeting Title</th>
                    <th className="px-6 py-3 font-semibold">Project</th>
                    <th className="px-6 py-3 font-semibold">Pulse Score</th>
                    <th className="px-6 py-3 font-semibold">Status</th>
                    <th className="px-6 py-3 font-semibold text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {filteredPoints.length === 0 ? (
                    <tr>
                      <td
                        colSpan={6}
                        className="px-6 py-8 text-center italic text-slate-400"
                      >
                        No meetings recorded in the selected period.
                      </td>
                    </tr>
                  ) : (
                    filteredPoints.map((pt) => (
                      <tr
                        key={pt.meeting_id}
                        className="hover:bg-slate-800/40 transition-colors"
                      >
                        <td className="px-6 py-3.5 font-mono text-slate-300 whitespace-nowrap">
                          {pt.meeting_date.slice(0, 10)}
                        </td>
                        <td className="px-6 py-3.5 font-semibold text-white">
                          {pt.title}
                        </td>
                        <td className="px-6 py-3.5 font-mono text-slate-400">
                          {pt.project_id}
                        </td>
                        <td className="px-6 py-3.5">
                          <span
                            className={`rounded-full px-2.5 py-0.5 text-xs font-mono font-bold ${
                              pt.pulse_score >= 70
                                ? "bg-emerald-950 text-emerald-300 border border-emerald-500/40"
                                : pt.pulse_score >= 40
                                ? "bg-amber-950 text-amber-300 border border-amber-500/40"
                                : "bg-rose-950 text-rose-300 border border-rose-500/40"
                            }`}
                          >
                            {pt.pulse_score}
                          </span>
                        </td>
                        <td className="px-6 py-3.5">
                          <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-[11px] text-slate-300">
                            {pt.status}
                          </span>
                        </td>
                        <td className="px-6 py-3.5 text-right whitespace-nowrap">
                          <button
                            type="button"
                            onClick={() => handleNodeClick(pt.meeting_id)}
                            className="min-h-[36px] rounded bg-indigo-600/30 border border-indigo-500/50 px-3 py-1.5 text-xs font-semibold text-indigo-200 hover:bg-indigo-600 hover:text-white transition-all"
                          >
                            View MoM &amp; Drill-Down
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>

      {/* Meeting Details Drill-Down Drawer */}
      <MeetingDetailsDrawer
        isOpen={isDetailsDrawerOpen}
        onClose={() => setIsDetailsDrawerOpen(false)}
        meeting={selectedMeeting}
        onOpenAdjudication={(mid) => {
          setIsDetailsDrawerOpen(false);
          if (onOpenAdjudication) onOpenAdjudication(mid);
        }}
      />

      {/* Inline XAI Rationale Drawer */}
      <XaiRationaleDrawer
        isOpen={isXaiDrawerOpen}
        onClose={() => setIsXaiDrawerOpen(false)}
        blockText={activeXaiBlockText}
        blockId="blk-demo-xai-01"
        pulseScore={72.0}
        rubricScores={{
          emotional_valence: 18,
          delivery_alignment: 19,
          relationship_trust: 17,
          momentum_commitment: 18,
        }}
        attributions={[
          {
            verbatim_phrase: "audit was approved by legal with zero critical defects",
            start_char: 26,
            end_char: 81,
            attribution_weight: 0.85,
            rubric_dimension: "Delivery Alignment",
            rationale: "Unambiguous compliance verification and zero defect sign-off directly improves delivery confidence.",
          },
          {
            verbatim_phrase: "deployment schedules remain tight",
            start_char: 87,
            end_char: 120,
            attribution_weight: -0.35,
            rubric_dimension: "Momentum & Commitment",
            rationale: "Schedule pressure introduces operational friction and delivery risk.",
          },
        ]}
        computedAt={new Date().toISOString()}
      />
    </div>
  );
};
