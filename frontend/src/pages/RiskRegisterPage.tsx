import React, { useCallback, useEffect, useMemo, useState } from "react";
import { UserRole } from "../api/authApi";
import {
  AiMitigationResponse,
  createRiskRecord,
  discoverAiRisks,
  DiscoveredRiskItem,
  fetchPortfolioRisksAnalytics,
  fetchRiskAuditTrail,
  HeatmapCellNode,
  PortfolioRisksAnalyticsResponse,
  RiskAuditTrailResponse,
  RiskCategory,
  RiskRegisterRecord,
  RiskStatus,
  SeverityBand,
  synthesizeAiMitigation,
  triggerSlaEscalationsEvaluation,
  updateRiskRecord,
} from "../api/risksApi";

interface RiskRegisterPageProps {
  idToken: string;
  userRole: UserRole;
  onBackToWorkspace: () => void;
  onOpenAdjudication?: (meetingId: string) => void;
}

function getSlaCountdown(risk: RiskRegisterRecord): { text: string; isBreached: boolean; color: string } {
  const tierStr = risk.sla_escalation_tier || "72h";
  const tierHours = tierStr === "24h" ? 24 : tierStr === "48h" ? 48 : 72;
  const startedAt = (risk.escalation_config?.sla_started_at as string | undefined) || risk.created_at;
  if (!startedAt) return { text: `${tierStr} SLA Target`, isBreached: false, color: "text-slate-300 border-slate-700 bg-slate-900" };

  const startMs = new Date(startedAt).getTime();
  if (isNaN(startMs)) return { text: `${tierStr} SLA Target`, isBreached: false, color: "text-slate-300 border-slate-700 bg-slate-900" };

  const nowMs = Date.now();
  const elapsedHours = (nowMs - startMs) / (1000 * 60 * 60);
  const remainingHours = Math.round(tierHours - elapsedHours);

  if (remainingHours <= 0) {
    const overdue = Math.abs(remainingHours);
    return {
      text: `${tierStr} SLA Breached (+${overdue}h)`,
      isBreached: true,
      color: "text-rose-200 border-rose-500/70 bg-rose-950",
    };
  }
  if (remainingHours <= 6) {
    return {
      text: `${tierStr} SLA • ${remainingHours}h left`,
      isBreached: false,
      color: "text-amber-200 border-amber-500/70 bg-amber-950",
    };
  }
  return {
    text: `${tierStr} SLA • ${remainingHours}h left`,
    isBreached: false,
    color: "text-emerald-200 border-emerald-500/70 bg-emerald-950",
  };
}

const CATEGORIES: RiskCategory[] = [

  "FINANCIAL",
  "OPERATIONAL",
  "COMPLIANCE",
  "STRATEGIC",
  "RELATIONSHIP",
];

const STATUSES: RiskStatus[] = [
  "OPEN",
  "ESCALATED",
  "MITIGATED",
  "CLOSED",
  "ACCEPTED",
  "DRAFT_PENDING_ADJUDICATION",
  "DISMISSED",
];

function getSeverityBandFromScore(score: number): SeverityBand {
  if (score >= 20) return "CRITICAL";
  if (score >= 12) return "HIGH";
  if (score >= 6) return "MEDIUM";
  return "LOW";
}

function getSeverityBadgeStyle(band: SeverityBand): {
  container: string;
  label: string;
} {
  switch (band) {
    case "CRITICAL":
      return {
        container: "border-rose-500/70 bg-rose-950 text-rose-100",
        label: "CRITICAL",
      };
    case "HIGH":
      return {
        container: "border-amber-500/70 bg-amber-950 text-amber-100",
        label: "HIGH",
      };
    case "MEDIUM":
      return {
        container: "border-indigo-500/70 bg-indigo-950 text-indigo-100",
        label: "MEDIUM",
      };
    default:
      return {
        container: "border-emerald-500/70 bg-emerald-950 text-emerald-100",
        label: "LOW",
      };
  }
}

function getHeatmapCellClasses(
  band: SeverityBand,
  hasRisks: boolean,
  isSelected: boolean
): string {
  const ring = isSelected
    ? "ring-2 ring-white border-white"
    : "border-slate-700/90 hover:border-slate-400";

  if (!hasRisks) {
    return `bg-slate-900/90 text-slate-300 ${ring}`;
  }

  switch (band) {
    case "CRITICAL":
      return `bg-rose-950 text-rose-100 ${ring}`;
    case "HIGH":
      return `bg-amber-950 text-amber-100 ${ring}`;
    case "MEDIUM":
      return `bg-indigo-950 text-indigo-100 ${ring}`;
    default:
      return `bg-emerald-950 text-emerald-100 ${ring}`;
  }
}

export const RiskRegisterPage: React.FC<RiskRegisterPageProps> = ({
  idToken,
  userRole,
  onBackToWorkspace,
  onOpenAdjudication,
}) => {
  const canEditRisks =
    userRole === "ADMIN" ||
    userRole === "EXECUTIVE" ||
    userRole === "MANAGER" ||
    userRole === "ADJUDICATOR";

  const [analytics, setAnalytics] =
    useState<PortfolioRisksAnalyticsResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionBanner, setActionBanner] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Filters & interactive heatmap drill-down state
  const [projectFilter, setProjectFilter] = useState<string>("");
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [selectedCell, setSelectedCell] = useState<{
    impact: number;
    probability: number;
  } | null>(null);

  // New Risk Registration Modal / Drawer
  const [showCreateForm, setShowCreateForm] = useState<boolean>(false);
  const [newProjectId, setNewProjectId] = useState<string>("proj-alpha");
  const [newCompanyName, setNewCompanyName] = useState<string>(
    "Acme Financial Corp"
  );
  const [newTitle, setNewTitle] = useState<string>("");
  const [newDescription, setNewDescription] = useState<string>("");
  const [newCategory, setNewCategory] = useState<RiskCategory>("OPERATIONAL");
  const [newImpact, setNewImpact] = useState<number>(4);
  const [newProbability, setNewProbability] = useState<number>(4);
  const [newOwnerUid, setNewOwnerUid] = useState<string>(
    "uid_manager_enterprise_com"
  );
  const [newMitigationStrategy, setNewMitigationStrategy] =
    useState<string>("");
  const [isSubmittingCreate, setIsSubmittingCreate] = useState<boolean>(false);

  // Inline Edit Modal / Drawer state for a selected risk
  const [editingRisk, setEditingRisk] = useState<RiskRegisterRecord | null>(
    null
  );
  const [editStatus, setEditStatus] = useState<RiskStatus>("OPEN");
  const [editCategory, setEditCategory] = useState<RiskCategory>("OPERATIONAL");
  const [editImpact, setEditImpact] = useState<number>(3);
  const [editProbability, setEditProbability] = useState<number>(3);
  const [editOwnerUid, setEditOwnerUid] = useState<string>("");
  const [editEscalationEnabled, setEditEscalationEnabled] =
    useState<boolean>(true);
  const [editMitigationStrategy, setEditMitigationStrategy] =
    useState<string>("");
  const [editComment, setEditComment] = useState<string>("");
  const [isSavingEdit, setIsSavingEdit] = useState<boolean>(false);

  // Immutable Audit Trail Drawer state
  const [auditDrawerData, setAuditDrawerData] =
    useState<RiskAuditTrailResponse | null>(null);
  const [isLoadingAudit, setIsLoadingAudit] = useState<boolean>(false);
  const [isRunningSlaJob, setIsRunningSlaJob] = useState<boolean>(false);

  // AI Risk Discovery modal state
  const [showAiDiscoveryModal, setShowAiDiscoveryModal] = useState<boolean>(false);
  const [isDiscoveringAi, setIsDiscoveringAi] = useState<boolean>(false);
  const [aiDiscoveredRisks, setAiDiscoveredRisks] = useState<DiscoveredRiskItem[]>([]);
  const [aiDiscoverySummary, setAiDiscoverySummary] = useState<string | null>(null);
  const [registeringRiskIdx, setRegisteringRiskIdx] = useState<number | null>(null);

  // AI Mitigation Strategy modal/drawer state
  const [selectedMitigationRisk, setSelectedMitigationRisk] = useState<RiskRegisterRecord | null>(null);
  const [aiMitigationPlan, setAiMitigationPlan] = useState<AiMitigationResponse | null>(null);
  const [isLoadingMitigation, setIsLoadingMitigation] = useState<boolean>(false);
  const [isApplyingMitigation, setIsApplyingMitigation] = useState<boolean>(false);
  const [inlineUpdatingRiskId, setInlineUpdatingRiskId] = useState<string | null>(null);

  const loadPortfolioData = useCallback(async () => {

    setIsLoading(true);
    setLoadError(null);
    try {
      const data = await fetchPortfolioRisksAnalytics(idToken, {
        project_id: projectFilter || undefined,
        category: categoryFilter || undefined,
        status: statusFilter || undefined,
      });
      setAnalytics(data);
    } catch (err) {
      setLoadError(
        err instanceof Error
          ? err.message
          : "Unable to load portfolio risk heatmap and register."
      );
    } finally {
      setIsLoading(false);
    }
  }, [idToken, projectFilter, categoryFilter, statusFilter]);

  useEffect(() => {
    void loadPortfolioData();
  }, [loadPortfolioData]);

  // Close drawers/modals on Escape key for WCAG 2.1 AA keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (auditDrawerData) setAuditDrawerData(null);
        else if (editingRisk) setEditingRisk(null);
        else if (showCreateForm) setShowCreateForm(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [auditDrawerData, editingRisk, showCreateForm]);

  const displayedRisks = useMemo(() => {
    if (!analytics) return [];
    if (!selectedCell) return analytics.risks;
    return analytics.risks.filter(
      (r) =>
        r.impact === selectedCell.impact &&
        r.probability === selectedCell.probability
    );
  }, [analytics, selectedCell]);

  const handleCellClick = (cell: HeatmapCellNode) => {
    if (
      selectedCell &&
      selectedCell.impact === cell.impact &&
      selectedCell.probability === cell.probability
    ) {
      setSelectedCell(null);
    } else {
      setSelectedCell({ impact: cell.impact, probability: cell.probability });
    }
  };

  const handleOpenEditModal = (risk: RiskRegisterRecord) => {
    setEditingRisk(risk);
    setEditStatus(risk.status);
    setEditCategory(risk.category);
    setEditImpact(risk.impact);
    setEditProbability(risk.probability);
    setEditOwnerUid(risk.owner_uid || "");
    setEditEscalationEnabled(risk.escalation_config?.enabled !== false);
    const currentStrat =
      typeof risk.mitigation_plan?.strategy === "string"
        ? risk.mitigation_plan.strategy
        : "";
    setEditMitigationStrategy(currentStrat);
    setEditComment("");
    setActionError(null);
  };

  const handleSaveRiskOverride = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingRisk) return;
    setIsSavingEdit(true);
    setActionError(null);
    setActionBanner(null);
    try {
      const updated = await updateRiskRecord(idToken, editingRisk.risk_id, {
        status: editStatus,
        category: editCategory,
        impact: editImpact,
        probability: editProbability,
        owner_uid: editOwnerUid.trim() || undefined,
        escalation_enabled: editEscalationEnabled,
        mitigation_plan: editMitigationStrategy.trim()
          ? { strategy: editMitigationStrategy.trim() }
          : undefined,
        comment: editComment.trim() || undefined,
      });
      setActionBanner(
        `Updated risk ${updated.risk_id} (Severity ${updated.severity_score}/25 ${updated.severity_band}, Status: ${updated.status}) and recorded immutable audit trail.`
      );
      setEditingRisk(null);
      await loadPortfolioData();
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Failed to save risk override."
      );
    } finally {
      setIsSavingEdit(false);
    }
  };

  const handleCreateRisk = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim() || !newDescription.trim()) {
      setActionError("Risk title and contextual description are required.");
      return;
    }
    setIsSubmittingCreate(true);
    setActionError(null);
    setActionBanner(null);
    try {
      const created = await createRiskRecord(idToken, {
        project_id: newProjectId.trim() || "proj-alpha",
        company_name: newCompanyName.trim() || undefined,
        title: newTitle.trim(),
        description: newDescription.trim(),
        category: newCategory,
        status: "OPEN",
        impact: newImpact,
        probability: newProbability,
        owner_uid: newOwnerUid.trim() || undefined,
        mitigation_plan: newMitigationStrategy.trim()
          ? { strategy: newMitigationStrategy.trim() }
          : undefined,
      });
      setActionBanner(
        `Registered risk ${created.risk_id} with COSO Severity Index ${created.severity_score}/25 (${created.severity_band}).`
      );
      setNewTitle("");
      setNewDescription("");
      setNewMitigationStrategy("");
      setShowCreateForm(false);
      await loadPortfolioData();
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Failed to register risk."
      );
    } finally {
      setIsSubmittingCreate(false);
    }
  };

  const handleOpenAuditDrawer = async (riskId: string) => {
    setIsLoadingAudit(true);
    setActionError(null);
    try {
      const trail = await fetchRiskAuditTrail(idToken, riskId);
      setAuditDrawerData(trail);
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Failed to fetch risk audit trail."
      );
    } finally {
      setIsLoadingAudit(false);
    }
  };

  const handleRunSlaEvaluation = async () => {
    setIsRunningSlaJob(true);
    setActionError(null);
    setActionBanner(null);
    try {
      const result = await triggerSlaEscalationsEvaluation(idToken);
      const totalEscalated =
        result.escalated_24h_risk_ids.length +
        result.escalated_48h_risk_ids.length +
        result.escalated_72h_risk_ids.length;
      setActionBanner(
        `Evaluated ${result.total_risks_scanned} risks: ${totalEscalated} SLA tier transition(s) triggered (${result.notifications_dispatched} alert email(s) sent).`
      );
      await loadPortfolioData();
    } catch (err) {
      setActionError(
        err instanceof Error
          ? err.message
          : "Failed to run SLA escalation check."
      );
    } finally {
      setIsRunningSlaJob(false);
    }
  };

  const handleRunAiDiscovery = async () => {
    setIsDiscoveringAi(true);
    setActionError(null);
    try {
      const res = await discoverAiRisks(idToken, {
        project_id: projectFilter || undefined,
        lookback_window: "30D",
        auto_register: false,
      });
      setAiDiscoveredRisks(res.discovered_risks);
      setAiDiscoverySummary(res.summary);
      setShowAiDiscoveryModal(true);
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Failed to run AI risk discovery."
      );
    } finally {
      setIsDiscoveringAi(false);
    }
  };

  const handleRegisterDiscoveredRisk = async (
    item: DiscoveredRiskItem,
    idx: number
  ) => {
    setRegisteringRiskIdx(idx);
    setActionError(null);
    try {
      await createRiskRecord(idToken, {
        project_id: item.project_id,
        meeting_id: item.meeting_id,
        title: item.title,
        description: item.description,
        category: item.category,
        impact: item.impact,
        probability: item.probability,
        status: "OPEN",
        associated_groups: item.associated_groups,
        mitigation_plan: {
          mitigation_strategy: item.mitigation_strategy,
          executive_escalation_brief: item.executive_brief,
        },
      });
      setActionBanner(`Successfully registered risk: ${item.title}`);
      setAiDiscoveredRisks((prev) => prev.filter((_, i) => i !== idx));
      await loadPortfolioData();
    } catch (err) {
      setActionError(
        err instanceof Error
          ? err.message
          : "Failed to register discovered risk."
      );
    } finally {
      setRegisteringRiskIdx(null);
    }
  };

  const handleOpenAiMitigation = async (risk: RiskRegisterRecord) => {
    setSelectedMitigationRisk(risk);
    setAiMitigationPlan(null);
    setIsLoadingMitigation(true);
    setActionError(null);
    try {
      const plan = await synthesizeAiMitigation(idToken, risk.risk_id);
      setAiMitigationPlan(plan);
    } catch (err) {
      setActionError(
        err instanceof Error
          ? err.message
          : "Failed to synthesize AI mitigation."
      );
    } finally {
      setIsLoadingMitigation(false);
    }
  };

  const handleApplyAiMitigation = async () => {
    if (!selectedMitigationRisk) return;
    setIsApplyingMitigation(true);
    setActionError(null);
    try {
      const res = await synthesizeAiMitigation(
        idToken,
        selectedMitigationRisk.risk_id,
        { apply_to_risk: true }
      );
      setActionBanner(
        `Applied AI Proactive Mitigation Strategy to ${selectedMitigationRisk.risk_id}!`
      );
      if (res.updated_risk) {
        setAnalytics((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            risks: prev.risks.map((r) =>
              r.risk_id === selectedMitigationRisk.risk_id
                ? (res.updated_risk as RiskRegisterRecord)
                : r
            ),
          };
        });
      }
      setSelectedMitigationRisk(null);
      await loadPortfolioData();
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Failed to apply AI mitigation."
      );
    } finally {
      setIsApplyingMitigation(false);
    }
  };

  const handleInlineFieldChange = async (
    risk: RiskRegisterRecord,
    field: "impact" | "probability" | "status" | "owner_uid",
    value: string | number
  ) => {
    setInlineUpdatingRiskId(risk.risk_id);
    try {
      const updates: Record<string, unknown> = { [field]: value };
      const updated = await updateRiskRecord(idToken, risk.risk_id, updates);
      setAnalytics((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          risks: prev.risks.map((r) =>
            r.risk_id === risk.risk_id ? updated : r
          ),
        };
      });
      setActionBanner(`Updated ${field} for risk ${risk.risk_id}.`);
    } catch (err) {
      setActionError(
        err instanceof Error
          ? err.message
          : `Failed to update ${field} for ${risk.risk_id}.`
      );
    } finally {
      setInlineUpdatingRiskId(null);
    }
  };


  const handleExportCsv = () => {
    if (!displayedRisks.length) return;
    const headers = [
      "Risk ID",
      "Project ID",
      "Title",
      "Category",
      "Status",
      "Impact (1-5)",
      "Probability (1-5)",
      "Severity Score (1-25)",
      "Severity Band",
      "SLA Tier",
      "Owner UID",
      "Updated At",
    ];
    const rows = displayedRisks.map((r) => [
      r.risk_id,
      r.project_id,
      `"${r.title.replace(/"/g, '""')}"`,
      r.category,
      r.status,
      String(r.impact),
      String(r.probability),
      String(r.severity_score),
      r.severity_band,
      r.sla_escalation_tier,
      r.owner_uid || "",
      r.updated_at,
    ]);
    const csvContent = [headers.join(","), ...rows.map((r) => r.join(","))].join(
      "\n"
    );
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `prisk_register_${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const previewNewSeverity = newImpact * newProbability;
  const previewNewBand = getSeverityBandFromScore(previewNewSeverity);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-900 px-4 py-4 sm:px-6">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-lg font-bold text-slate-50 sm:text-xl">
              Enterprise Risk Register &amp; 5x5 COSO / ISO 31000 Heatmap
            </h1>
            <p className="mt-1 text-xs text-slate-300">
              Quantitative Impact (1 to 5) and Probability (1 to 5) severity
              scoring, 24h / 48h / 72h SLA escalations, and immutable audit
              trails.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2.5">
            {canEditRisks && (
              <button
                type="button"
                onClick={handleRunAiDiscovery}
                disabled={isDiscoveringAi}
                className="min-h-[44px] rounded-lg border border-slate-700 bg-slate-800 px-3.5 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 disabled:opacity-50"
              >
                {isDiscoveringAi
                  ? "AI Scanning Pulse Drops..."
                  : "Discover Emerging Risks with AI"}
              </button>
            )}
            {canEditRisks && (
              <button
                type="button"
                onClick={() => setShowCreateForm((prev) => !prev)}
                className="min-h-[44px] rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              >
                {showCreateForm ? "Close New Risk Form" : "Register New Risk"}
              </button>
            )}

            {canEditRisks && (
              <button
                type="button"
                onClick={handleRunSlaEvaluation}
                disabled={isRunningSlaJob}
                className="min-h-[44px] rounded-lg border border-slate-700 bg-slate-800 px-3.5 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 disabled:opacity-50"
              >
                {isRunningSlaJob
                  ? "Evaluating SLAs..."
                  : "Evaluate 24h/48h/72h SLAs"}
              </button>
            )}
            <button
              type="button"
              onClick={handleExportCsv}
              disabled={!displayedRisks.length}
              className="min-h-[44px] rounded-lg border border-slate-750 bg-slate-900 px-3.5 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-800 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 disabled:opacity-50"
            >
              Export Register CSV
            </button>
            <button
              type="button"
              onClick={onBackToWorkspace}
              className="min-h-[44px] rounded-lg border border-slate-750 bg-slate-900 px-3.5 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-800 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
            >
              Back to Workspace
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
        {/* Systemic Risk Spike Alert Banner (FR-7.4c) */}
        {analytics?.systemic_spike?.is_active && (
          <section
            role="alert"
            className="rounded-xl border-2 border-rose-500 bg-rose-950 p-4 text-rose-100"
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-bold uppercase tracking-wide text-rose-100">
                  Systemic Portfolio Risk Spike Warning (FR-7.4c)
                </h2>
                <p className="mt-1 text-xs text-rose-100">
                  {analytics.systemic_spike.alert_message}
                </p>
              </div>
              <div className="flex flex-wrap gap-2 text-xs font-mono">
                <span className="rounded border border-rose-400/60 bg-slate-950 px-2.5 py-1 text-rose-100">
                  Critical Projects:{" "}
                  {analytics.systemic_spike.concurrent_critical_project_count}
                </span>
                <span className="rounded border border-rose-400/60 bg-slate-950 px-2.5 py-1 text-rose-100">
                  7D Velocity:{" "}
                  {analytics.systemic_spike.velocity_surge_pct >= 0 ? "+" : ""}
                  {analytics.systemic_spike.velocity_surge_pct}%
                </span>
              </div>
            </div>
          </section>
        )}

        {actionBanner && (
          <div
            role="status"
            className="rounded-lg border border-emerald-500/60 bg-emerald-950 px-4 py-3 text-xs text-emerald-100"
          >
            {actionBanner}
          </div>
        )}

        {actionError && (
          <div
            role="alert"
            className="rounded-lg border border-rose-500/60 bg-rose-950 px-4 py-3 text-xs text-rose-100"
          >
            {actionError}
          </div>
        )}

        {/* Collapsible Register New Risk Form */}
        {showCreateForm && canEditRisks && (
          <section className="rounded-xl border border-slate-700 bg-slate-900 p-5">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h2 className="text-sm font-bold text-white">
                Register New Project Risk (COSO / ISO 31000)
              </h2>
              <span className="rounded border border-indigo-500/60 bg-indigo-950 px-2.5 py-1 font-mono text-xs font-semibold text-indigo-100">
                Preview Severity: {previewNewSeverity}/25 ({previewNewBand})
              </span>
            </div>
            <form
              onSubmit={handleCreateRisk}
              className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3"
            >
              <div>
                <label
                  htmlFor="new-risk-project"
                  className="block text-xs font-medium text-slate-200"
                >
                  Project ID
                </label>
                <input
                  id="new-risk-project"
                  type="text"
                  value={newProjectId}
                  onChange={(e) => setNewProjectId(e.target.value)}
                  required
                  className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                />
              </div>
              <div>
                <label
                  htmlFor="new-risk-company"
                  className="block text-xs font-medium text-slate-200"
                >
                  Company / Account Name
                </label>
                <input
                  id="new-risk-company"
                  type="text"
                  value={newCompanyName}
                  onChange={(e) => setNewCompanyName(e.target.value)}
                  placeholder="Acme Financial Corp"
                  className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                />
              </div>
              <div>
                <label
                  htmlFor="new-risk-category"
                  className="block text-xs font-medium text-slate-200"
                >
                  Risk Category
                </label>
                <select
                  id="new-risk-category"
                  value={newCategory}
                  onChange={(e) =>
                    setNewCategory(e.target.value as RiskCategory)
                  }
                  className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                >
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>
              <div className="md:col-span-2">
                <label
                  htmlFor="new-risk-title"
                  className="block text-xs font-medium text-slate-200"
                >
                  Risk Title
                </label>
                <input
                  id="new-risk-title"
                  type="text"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  placeholder="Delayed audit log schema sign-off blocking UAT cutover"
                  required
                  className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                />
              </div>
              <div>
                <label
                  htmlFor="new-risk-owner"
                  className="block text-xs font-medium text-slate-200"
                >
                  Assigned Risk Owner UID
                </label>
                <input
                  id="new-risk-owner"
                  type="text"
                  value={newOwnerUid}
                  onChange={(e) => setNewOwnerUid(e.target.value)}
                  placeholder="uid_manager_enterprise_com"
                  className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                />
              </div>
              <div>
                <label
                  htmlFor="new-risk-impact"
                  className="block text-xs font-medium text-slate-200"
                >
                  COSO Impact Scale (1 to 5)
                </label>
                <select
                  id="new-risk-impact"
                  value={newImpact}
                  onChange={(e) => setNewImpact(Number(e.target.value))}
                  className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                >
                  {[1, 2, 3, 4, 5].map((n) => (
                    <option key={n} value={n}>
                      {n} {n === 5 ? "(Severe)" : n === 1 ? "(Minimal)" : ""}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label
                  htmlFor="new-risk-probability"
                  className="block text-xs font-medium text-slate-200"
                >
                  COSO Probability Scale (1 to 5)
                </label>
                <select
                  id="new-risk-probability"
                  value={newProbability}
                  onChange={(e) => setNewProbability(Number(e.target.value))}
                  className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                >
                  {[1, 2, 3, 4, 5].map((n) => (
                    <option key={n} value={n}>
                      {n}{" "}
                      {n === 5 ? "(Almost Certain)" : n === 1 ? "(Rare)" : ""}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label
                  htmlFor="new-risk-mitigation"
                  className="block text-xs font-medium text-slate-200"
                >
                  Initial Mitigation Strategy
                </label>
                <input
                  id="new-risk-mitigation"
                  type="text"
                  value={newMitigationStrategy}
                  onChange={(e) => setNewMitigationStrategy(e.target.value)}
                  placeholder="Schedule daily technical checkpoint with legal..."
                  className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                />
              </div>
              <div className="md:col-span-2 lg:col-span-3">
                <label
                  htmlFor="new-risk-description"
                  className="block text-xs font-medium text-slate-200"
                >
                  Contextual Description
                </label>
                <textarea
                  id="new-risk-description"
                  rows={2}
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  placeholder="Describe the operational, financial, or compliance exposure..."
                  required
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                />
              </div>
              <div className="flex justify-end gap-2 md:col-span-2 lg:col-span-3">
                <button
                  type="button"
                  onClick={() => setShowCreateForm(false)}
                  className="min-h-[44px] rounded-lg border border-slate-700 px-4 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmittingCreate}
                  className="min-h-[44px] rounded-lg bg-indigo-600 px-5 py-2 text-xs font-semibold text-white hover:bg-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 disabled:opacity-50"
                >
                  {isSubmittingCreate ? "Saving..." : "Submit Risk to Register"}
                </button>
              </div>
            </form>
          </section>
        )}

        {/* Filter Bar */}
        <section className="rounded-xl border border-slate-800 bg-slate-900 p-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <label
                htmlFor="filter-project"
                className="block text-xs font-medium text-slate-300"
              >
                Filter by Project ID
              </label>
              <input
                id="filter-project"
                type="text"
                value={projectFilter}
                onChange={(e) => setProjectFilter(e.target.value)}
                placeholder="All accessible projects"
                className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              />
            </div>
            <div>
              <label
                htmlFor="filter-category"
                className="block text-xs font-medium text-slate-300"
              >
                COSO Category
              </label>
              <select
                id="filter-category"
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value)}
                className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              >
                <option value="">All Categories</option>
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label
                htmlFor="filter-status"
                className="block text-xs font-medium text-slate-300"
              >
                Lifecycle Status
              </label>
              <select
                id="filter-status"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              >
                <option value="">All Statuses</option>
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-end gap-2">
              {selectedCell && (
                <button
                  type="button"
                  onClick={() => setSelectedCell(null)}
                  className="min-h-[44px] w-full rounded-lg border border-indigo-500/60 bg-indigo-950 px-3 py-2 text-xs font-semibold text-indigo-100 hover:bg-indigo-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                >
                  Clear Cell Drill-Down (I:{selectedCell.impact} x P:
                  {selectedCell.probability})
                </button>
              )}
              {(projectFilter || categoryFilter || statusFilter) && (
                <button
                  type="button"
                  onClick={() => {
                    setProjectFilter("");
                    setCategoryFilter("");
                    setStatusFilter("");
                    setSelectedCell(null);
                  }}
                  className="min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                >
                  Reset Filters
                </button>
              )}
            </div>
          </div>
        </section>

        {/* Loading and Error States (R-27) */}
        {isLoading ? (
          <section className="rounded-xl border border-slate-800 bg-slate-900 p-8 text-center">
            <p className="text-sm font-semibold text-slate-100">
              Loading portfolio risk register and 5x5 COSO heatmap matrix...
            </p>
            <p className="mt-1 text-xs text-slate-300">
              Aggregating Impact and Probability coordinates across authorized
              projects.
            </p>
          </section>
        ) : loadError ? (
          <section
            role="alert"
            className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 rounded-xl border border-rose-500/40 bg-rose-950/30 p-5 text-rose-200"
          >
            <div>
              <h2 className="text-sm font-semibold text-rose-100">
                Risk Register Connection Notice
              </h2>
              <p className="mt-1 text-xs text-rose-300">{loadError}</p>
            </div>
            <button
              type="button"
              onClick={() => void loadPortfolioData()}
              className="min-h-[40px] shrink-0 rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
            >
              Retry Loading Risk Register
            </button>
          </section>
        ) : (
          analytics && (
            <>
              {/* 5x5 Matrix + Portfolio Breakdown Grid */}
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                {/* 5x5 COSO / ISO 31000 Heatmap Matrix */}
                <section className="rounded-xl border border-slate-800 bg-slate-900 p-5 lg:col-span-7">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <h2 className="text-base font-bold text-white">
                        5x5 COSO / ISO 31000 Impact x Probability Heatmap
                      </h2>
                      <p className="mt-0.5 text-xs text-slate-300">
                        Select any matrix coordinate to drill down into the
                        underlying risks for that cell.
                      </p>
                    </div>
                    <span className="rounded border border-slate-700 bg-slate-950 px-2.5 py-1 font-mono text-xs text-slate-200">
                      Avg Severity: {analytics.average_severity_score}/25
                    </span>
                  </div>

                  <div className="mt-4 overflow-x-auto pb-2">
                    <div className="min-w-[420px]">
                      <div className="grid grid-cols-6 gap-2 text-center text-xs font-semibold text-slate-300">
                        <div className="flex items-center justify-center rounded border border-slate-800 bg-slate-950 p-2 font-mono text-[11px] text-slate-300">
                          Impact \ Prob
                        </div>
                        {[1, 2, 3, 4, 5].map((prob) => (
                          <div
                            key={prob}
                            className="flex items-center justify-center rounded border border-slate-800 bg-slate-950 p-2 font-mono"
                          >
                            P = {prob}
                          </div>
                        ))}
                      </div>

                      {[5, 4, 3, 2, 1].map((impactLevel) => {
                        const rowCells = analytics.heatmap_cells.filter(
                          (c) => c.impact === impactLevel
                        );
                        return (
                          <div
                            key={impactLevel}
                            className="mt-2 grid grid-cols-6 gap-2"
                          >
                            <div className="flex items-center justify-center rounded border border-slate-800 bg-slate-950 p-2 font-mono text-xs font-semibold text-slate-200">
                              I = {impactLevel}
                            </div>
                            {rowCells.map((cell) => {
                              const isSelected =
                                selectedCell?.impact === cell.impact &&
                                selectedCell?.probability === cell.probability;
                              const cellStyle = getHeatmapCellClasses(
                                cell.severity_band,
                                cell.risk_count > 0,
                                isSelected
                              );
                              return (
                                <button
                                  key={`${cell.impact}-${cell.probability}`}
                                  type="button"
                                  aria-pressed={isSelected}
                                  aria-label={`Impact ${cell.impact}, Probability ${cell.probability}, Severity ${cell.severity_score} (${cell.severity_band}), ${cell.risk_count} risks`}
                                  onClick={() => handleCellClick(cell)}
                                  className={`flex min-h-[60px] flex-col items-center justify-center rounded-lg border p-2 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 ${cellStyle}`}
                                >
                                  <span className="font-mono text-xs font-bold">
                                    S:{cell.severity_score} ({cell.risk_count})
                                  </span>
                                  <span className="mt-0.5 text-[10px] font-semibold uppercase tracking-wider">
                                    {cell.severity_band}
                                  </span>
                                </button>
                              );
                            })}
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Severity Band Legend */}
                  <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-slate-800 pt-3 text-xs text-slate-200">
                    <span className="rounded border border-rose-500/70 bg-rose-950 px-2.5 py-1 font-mono text-rose-100">
                      Critical (20-25): {analytics.critical_count}
                    </span>
                    <span className="rounded border border-amber-500/70 bg-amber-950 px-2.5 py-1 font-mono text-amber-100">
                      High (12-19): {analytics.high_count}
                    </span>
                    <span className="rounded border border-indigo-500/70 bg-indigo-950 px-2.5 py-1 font-mono text-indigo-100">
                      Medium (6-11): {analytics.medium_count}
                    </span>
                    <span className="rounded border border-emerald-500/70 bg-emerald-950 px-2.5 py-1 font-mono text-emerald-100">
                      Low (1-5): {analytics.low_count}
                    </span>
                  </div>
                </section>

                {/* Portfolio Project & Category Breakdown */}
                <section className="space-y-4 rounded-xl border border-slate-800 bg-slate-900 p-5 lg:col-span-5">
                  <div>
                    <h2 className="text-base font-bold text-white">
                      Portfolio Exposure &amp; SLA Summary
                    </h2>
                    <p className="mt-0.5 text-xs text-slate-300">
                      Distribution across COSO dimensions and active project
                      workspaces.
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                      <span className="block text-xs text-slate-300">
                        Total Registered Risks
                      </span>
                      <span className="mt-1 block font-mono text-lg font-bold text-white">
                        {analytics.total_risks}
                      </span>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                      <span className="block text-xs text-slate-300">
                        Active (Open / Escalated)
                      </span>
                      <span className="mt-1 block font-mono text-lg font-bold text-amber-200">
                        {analytics.open_or_escalated_count}
                      </span>
                    </div>
                  </div>

                  <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                      COSO Risk Categories
                    </h3>
                    <div className="mt-2 space-y-2">
                      {CATEGORIES.map((cat) => {
                        const count =
                          analytics.category_distribution[cat] ?? 0;
                        const isCatSelected = categoryFilter === cat;
                        return (
                          <button
                            key={cat}
                            type="button"
                            onClick={() =>
                              setCategoryFilter(isCatSelected ? "" : cat)
                            }
                            className={`flex min-h-[44px] w-full items-center justify-between rounded-lg border px-3 py-2 text-left text-xs transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 ${
                              isCatSelected
                                ? "border-indigo-500 bg-indigo-950 text-indigo-100"
                                : "border-slate-800 bg-slate-950 text-slate-200 hover:border-slate-700"
                            }`}
                          >
                            <span className="font-semibold">{cat}</span>
                            <span className="font-mono font-bold">
                              {count} risk{count === 1 ? "" : "s"}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {analytics.project_summaries.length > 0 && (
                    <div>
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                        Projects by Peak Severity
                      </h3>
                      <div className="mt-2 space-y-2">
                        {analytics.project_summaries.map((proj) => (
                          <button
                            key={proj.project_id}
                            type="button"
                            onClick={() =>
                              setProjectFilter(
                                projectFilter === proj.project_id
                                  ? ""
                                  : proj.project_id
                              )
                            }
                            className={`flex min-h-[44px] w-full items-center justify-between rounded-lg border px-3 py-2 text-left text-xs transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 ${
                              projectFilter === proj.project_id
                                ? "border-emerald-500 bg-emerald-950 text-emerald-100"
                                : "border-slate-800 bg-slate-950 text-slate-200 hover:border-slate-700"
                            }`}
                          >
                            <div>
                              <span className="font-mono font-semibold">
                                {proj.project_id}
                              </span>
                              <span className="ml-2 text-slate-300">
                                ({proj.risk_count} total, {proj.critical_count}{" "}
                                critical)
                              </span>
                            </div>
                            <span className="font-mono text-xs font-bold">
                              Max {proj.max_severity}/25
                            </span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </section>
              </div>

              {/* Risk Register Table */}
              <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                <div className="flex flex-wrap items-center justify-between gap-2 pb-4">
                  <div>
                    <h2 className="text-base font-bold text-white">
                      Centralized Risk Register ({displayedRisks.length})
                    </h2>
                    <p className="mt-0.5 text-xs text-slate-300">
                      {selectedCell
                        ? `Filtered to Heatmap Node: Impact ${selectedCell.impact} x Probability ${selectedCell.probability} (Severity ${selectedCell.impact * selectedCell.probability}/25)`
                        : "Showing all risks matching active workspace filters."}
                    </p>
                  </div>
                </div>

                {displayedRisks.length === 0 ? (
                  <div className="rounded-lg border border-slate-800 bg-slate-950 p-8 text-center">
                    <p className="text-sm font-semibold text-slate-100">
                      No risk records match the selected coordinates or filters.
                    </p>
                    <p className="mt-1 text-xs text-slate-300">
                      Clear the active heatmap cell filter or register a new
                      project risk above.
                    </p>
                    {selectedCell && (
                      <button
                        type="button"
                        onClick={() => setSelectedCell(null)}
                        className="mt-4 min-h-[44px] rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                      >
                        Show All Portfolio Risks
                      </button>
                    )}
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full border-collapse text-left text-xs">
                      <thead>
                        <tr className="border-b border-slate-800 bg-slate-950 text-slate-200">
                          <th className="px-3 py-3 font-semibold">
                            Severity &amp; ID
                          </th>
                          <th className="px-3 py-3 font-semibold">
                            Risk Title &amp; Groups
                          </th>
                          <th className="px-3 py-3 font-semibold">Category</th>
                          <th className="px-3 py-3 font-semibold">
                            Status &amp; SLA Tier
                          </th>
                          <th className="px-3 py-3 font-semibold">Owner UID</th>
                          <th className="px-3 py-3 font-semibold">
                            Actions &amp; Audit
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800">
                        {displayedRisks.map((risk) => {
                          const badge = getSeverityBadgeStyle(
                            risk.severity_band
                          );
                          const slaInfo = getSlaCountdown(risk);
                          return (
                            <tr
                              key={risk.risk_id}
                              className="bg-slate-900/60 hover:bg-slate-800/50"
                            >
                              <td className="px-3 py-3 align-top">
                                <span
                                  className={`inline-block rounded border px-2.5 py-1 font-mono text-xs font-bold ${badge.container}`}
                                >
                                  {badge.label} {risk.severity_score}/25
                                </span>
                                {canEditRisks ? (
                                  <div className="mt-1.5 flex items-center gap-1 font-mono text-[11px] text-slate-300">
                                    <span>I:</span>
                                    <select
                                      aria-label={`Impact for ${risk.risk_id}`}
                                      value={risk.impact}
                                      disabled={inlineUpdatingRiskId === risk.risk_id}
                                      onChange={(e) =>
                                        void handleInlineFieldChange(
                                          risk,
                                          "impact",
                                          Number(e.target.value)
                                        )
                                      }
                                      className="rounded border border-slate-700 bg-slate-950 px-1 py-0.5 text-xs text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-indigo-400"
                                    >
                                      {[1, 2, 3, 4, 5].map((v) => (
                                        <option key={v} value={v}>
                                          {v}
                                        </option>
                                      ))}
                                    </select>
                                    <span>x P:</span>
                                    <select
                                      aria-label={`Probability for ${risk.risk_id}`}
                                      value={risk.probability}
                                      disabled={inlineUpdatingRiskId === risk.risk_id}
                                      onChange={(e) =>
                                        void handleInlineFieldChange(
                                          risk,
                                          "probability",
                                          Number(e.target.value)
                                        )
                                      }
                                      className="rounded border border-slate-700 bg-slate-950 px-1 py-0.5 text-xs text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-indigo-400"
                                    >
                                      {[1, 2, 3, 4, 5].map((v) => (
                                        <option key={v} value={v}>
                                          {v}
                                        </option>
                                      ))}
                                    </select>
                                  </div>
                                ) : (
                                  <div className="mt-1 font-mono text-[11px] text-slate-300">
                                    {risk.risk_id} (I:{risk.impact} x P:
                                    {risk.probability})
                                  </div>
                                )}
                                <div className="mt-0.5 font-mono text-[11px] text-emerald-300">
                                  {risk.project_id}
                                </div>
                              </td>
                              <td className="max-w-md px-3 py-3 align-top">
                                <div className="font-semibold text-white">
                                  {risk.title}
                                </div>
                                <p className="mt-1 text-slate-300">
                                  {risk.description}
                                </p>
                                {risk.associated_groups.length > 0 && (
                                  <div className="mt-2 flex flex-wrap gap-1.5">
                                    {risk.associated_groups.map((grp) => (
                                      <span
                                        key={grp}
                                        className="rounded border border-slate-700 bg-slate-950 px-2 py-0.5 text-[11px] text-slate-200"
                                      >
                                        {grp}
                                      </span>
                                    ))}
                                  </div>
                                )}
                              </td>
                              <td className="px-3 py-3 align-top font-mono text-slate-200">
                                {risk.category}
                              </td>
                              <td className="px-3 py-3 align-top">
                                {canEditRisks ? (
                                  <select
                                    aria-label={`Status for ${risk.risk_id}`}
                                    value={risk.status}
                                    disabled={inlineUpdatingRiskId === risk.risk_id}
                                    onChange={(e) =>
                                      void handleInlineFieldChange(
                                        risk,
                                        "status",
                                        e.target.value
                                      )
                                    }
                                    className="rounded border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-xs font-semibold text-slate-100 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-indigo-400"
                                  >
                                    {STATUSES.map((s) => (
                                      <option key={s} value={s}>
                                        {s}
                                      </option>
                                    ))}
                                  </select>
                                ) : (
                                  <span className="inline-block rounded border border-slate-700 bg-slate-950 px-2.5 py-1 font-mono font-semibold text-slate-100">
                                    {risk.status}
                                  </span>
                                )}
                                <div className="mt-2">
                                  <span
                                    className={`inline-block rounded border px-2 py-0.5 font-mono text-[11px] font-semibold ${slaInfo.color}`}
                                  >
                                    {slaInfo.text}
                                  </span>
                                </div>
                              </td>
                              <td className="px-3 py-3 align-top font-mono text-slate-200">
                                {risk.owner_uid || "Unassigned"}
                              </td>
                              <td className="px-3 py-3 align-top">
                                <div className="flex flex-wrap gap-2">
                                  <button
                                    type="button"
                                    onClick={() =>
                                      void handleOpenAiMitigation(risk)
                                    }
                                    className="min-h-[44px] rounded-lg border border-purple-500/60 bg-purple-950 px-3 py-1.5 text-xs font-semibold text-purple-100 hover:bg-purple-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400"
                                  >
                                    AI Mitigation
                                  </button>
                                  {canEditRisks && (
                                    <button
                                      type="button"
                                      onClick={() => handleOpenEditModal(risk)}
                                      className="min-h-[44px] rounded-lg border border-indigo-500/60 bg-indigo-950 px-3 py-1.5 text-xs font-semibold text-indigo-100 hover:bg-indigo-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                                    >
                                      Edit / Override
                                    </button>
                                  )}
                                  <button
                                    type="button"
                                    onClick={() =>
                                      void handleOpenAuditDrawer(risk.risk_id)
                                    }
                                    disabled={isLoadingAudit}
                                    className="min-h-[44px] rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs font-semibold text-slate-100 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                                  >
                                    Audit Drawer
                                  </button>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </>
          )
        )}


        {/* HITL Risk Override Modal */}
        {editingRisk && (
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="edit-risk-dialog-title"
            className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/80 p-4"
          >
            <div className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 p-6 shadow-2xl">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <h2
                  id="edit-risk-dialog-title"
                  className="text-base font-bold text-white"
                >
                  Override Risk {editingRisk.risk_id}
                </h2>
                <button
                  type="button"
                  onClick={() => setEditingRisk(null)}
                  className="min-h-[44px] min-w-[44px] rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                >
                  Close
                </button>
              </div>
              <form onSubmit={handleSaveRiskOverride} className="mt-4 space-y-4">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div>
                    <label
                      htmlFor="edit-risk-status"
                      className="block text-xs font-medium text-slate-200"
                    >
                      Lifecycle Status
                    </label>
                    <select
                      id="edit-risk-status"
                      value={editStatus}
                      onChange={(e) =>
                        setEditStatus(e.target.value as RiskStatus)
                      }
                      className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                    >
                      {STATUSES.map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label
                      htmlFor="edit-risk-category"
                      className="block text-xs font-medium text-slate-200"
                    >
                      COSO Category
                    </label>
                    <select
                      id="edit-risk-category"
                      value={editCategory}
                      onChange={(e) =>
                        setEditCategory(e.target.value as RiskCategory)
                      }
                      className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                    >
                      {CATEGORIES.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label
                      htmlFor="edit-risk-impact"
                      className="block text-xs font-medium text-slate-200"
                    >
                      Impact Score (1 to 5)
                    </label>
                    <select
                      id="edit-risk-impact"
                      value={editImpact}
                      onChange={(e) => setEditImpact(Number(e.target.value))}
                      className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                    >
                      {[1, 2, 3, 4, 5].map((n) => (
                        <option key={n} value={n}>
                          {n}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label
                      htmlFor="edit-risk-prob"
                      className="block text-xs font-medium text-slate-200"
                    >
                      Probability Score (1 to 5)
                    </label>
                    <select
                      id="edit-risk-prob"
                      value={editProbability}
                      onChange={(e) =>
                        setEditProbability(Number(e.target.value))
                      }
                      className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                    >
                      {[1, 2, 3, 4, 5].map((n) => (
                        <option key={n} value={n}>
                          {n}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="rounded-lg border border-slate-800 bg-slate-950 p-3 font-mono text-xs text-slate-200">
                  Recalculated Severity Index: {editImpact * editProbability}/25
                  ({getSeverityBandFromScore(editImpact * editProbability)})
                </div>

                <div>
                  <label
                    htmlFor="edit-risk-owner"
                    className="block text-xs font-medium text-slate-200"
                  >
                    Assigned Risk Owner UID
                  </label>
                  <input
                    id="edit-risk-owner"
                    type="text"
                    value={editOwnerUid}
                    onChange={(e) => setEditOwnerUid(e.target.value)}
                    className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                  />
                </div>

                <div>
                  <label
                    htmlFor="edit-risk-strategy"
                    className="block text-xs font-medium text-slate-200"
                  >
                    Mitigation Strategy Plan
                  </label>
                  <input
                    id="edit-risk-strategy"
                    type="text"
                    value={editMitigationStrategy}
                    onChange={(e) => setEditMitigationStrategy(e.target.value)}
                    className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                  />
                </div>

                <div className="flex items-center gap-3">
                  <input
                    id="edit-escalation-enabled"
                    type="checkbox"
                    checked={editEscalationEnabled}
                    onChange={(e) => setEditEscalationEnabled(e.target.checked)}
                    className="h-5 w-5 rounded border-slate-700 bg-slate-950 text-indigo-600 focus-visible:ring-2 focus-visible:ring-indigo-400"
                  />
                  <label
                    htmlFor="edit-escalation-enabled"
                    className="text-xs text-slate-200"
                  >
                    Enable automated 24h / 48h / 72h SLA escalation alerts
                  </label>
                </div>

                <div>
                  <label
                    htmlFor="edit-risk-comment"
                    className="block text-xs font-medium text-slate-200"
                  >
                    Append Qualitative Audit Commentary
                  </label>
                  <textarea
                    id="edit-risk-comment"
                    rows={2}
                    value={editComment}
                    onChange={(e) => setEditComment(e.target.value)}
                    placeholder="Document reason for severity or status adjustment..."
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                  />
                </div>

                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setEditingRisk(null)}
                    className="min-h-[44px] rounded-lg border border-slate-700 px-4 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSavingEdit}
                    className="min-h-[44px] rounded-lg bg-indigo-600 px-5 py-2 text-xs font-semibold text-white hover:bg-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 disabled:opacity-50"
                  >
                    {isSavingEdit
                      ? "Saving Override..."
                      : "Save Override & Log Audit Event"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Immutable Audit Trail & Source Meeting Drawer */}
        {auditDrawerData && (
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="audit-drawer-title"
            className="fixed inset-0 z-50 flex justify-end bg-slate-950/80"
          >
            <div className="flex h-full w-full max-w-2xl flex-col overflow-y-auto border-l border-slate-700 bg-slate-900 p-6 shadow-2xl">
              <div className="flex items-center justify-between border-b border-slate-800 pb-4">
                <div>
                  <h2
                    id="audit-drawer-title"
                    className="text-base font-bold text-white"
                  >
                    Immutable Audit Trail: {auditDrawerData.risk.risk_id}
                  </h2>
                  <p className="mt-0.5 text-xs text-slate-300">
                    {auditDrawerData.risk.title}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setAuditDrawerData(null)}
                  className="min-h-[44px] rounded-lg border border-slate-700 px-4 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                >
                  Close Drawer
                </button>
              </div>

              <div className="mt-5 space-y-5">
                {/* Source Meeting Linkage */}
                <div className="rounded-lg border border-slate-800 bg-slate-950 p-4">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                    Source Golden Record Meeting Artifact
                  </h3>
                  {auditDrawerData.source_meeting ? (
                    <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="text-xs font-semibold text-white">
                          {auditDrawerData.source_meeting.title} (
                          {auditDrawerData.source_meeting.meeting_id})
                        </p>
                        <p className="mt-0.5 text-xs text-slate-300">
                          Status: {auditDrawerData.source_meeting.status} |
                          Pulse Score:{" "}
                          {auditDrawerData.source_meeting.pulse_score ?? "N/A"}
                        </p>
                      </div>
                      {onOpenAdjudication && (
                        <button
                          type="button"
                          onClick={() => {
                            const mId =
                              auditDrawerData.source_meeting?.meeting_id;
                            setAuditDrawerData(null);
                            if (mId) onOpenAdjudication(mId);
                          }}
                          className="min-h-[44px] rounded-lg bg-indigo-600 px-3.5 py-2 text-xs font-semibold text-white hover:bg-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                        >
                          Inspect Source Meeting
                        </button>
                      )}
                    </div>
                  ) : (
                    <p className="mt-2 text-xs text-slate-300">
                      Registered manually at portfolio/project level (no source
                      meeting linked).
                    </p>
                  )}
                </div>

                {/* Mitigation Plan & Commentary */}
                <div className="rounded-lg border border-slate-800 bg-slate-950 p-4">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                    Active Mitigation Strategy &amp; Internal Commentary
                  </h3>
                  <p className="mt-2 text-xs text-slate-100">
                    Strategy:{" "}
                    {typeof auditDrawerData.risk.mitigation_plan?.strategy ===
                    "string"
                      ? auditDrawerData.risk.mitigation_plan.strategy
                      : "Pending formal treatment plan."}
                  </p>
                  {auditDrawerData.risk.qualitative_commentary.length > 0 && (
                    <div className="mt-3 space-y-2 border-t border-slate-800 pt-3">
                      {auditDrawerData.risk.qualitative_commentary.map(
                        (cmt) => (
                          <div
                            key={cmt.comment_id}
                            className="rounded border border-slate-800 bg-slate-900 p-2.5 text-xs"
                          >
                            <div className="flex justify-between font-mono text-[11px] text-slate-300">
                              <span>
                                {cmt.author_uid} ({cmt.author_role || "USER"})
                              </span>
                              <span>{cmt.created_at}</span>
                            </div>
                            <p className="mt-1 text-slate-100">{cmt.comment}</p>
                          </div>
                        )
                      )}
                    </div>
                  )}
                </div>

                {/* Chronological Audit Ledger Events */}
                <div>
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                    Immutable Governance Ledger Events (
                    {auditDrawerData.audit_events.length})
                  </h3>
                  {auditDrawerData.audit_events.length === 0 ? (
                    <p className="mt-2 rounded-lg border border-slate-800 bg-slate-950 p-4 text-xs text-slate-300">
                      No override or escalation ledger events recorded yet for
                      this risk.
                    </p>
                  ) : (
                    <div className="mt-2 space-y-3">
                      {auditDrawerData.audit_events.map((ev) => (
                        <div
                          key={ev.event_id}
                          className="rounded-lg border border-slate-800 bg-slate-950 p-3.5 text-xs"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="rounded border border-indigo-500/50 bg-indigo-950 px-2 py-0.5 font-mono font-semibold text-indigo-100">
                              {ev.event_type}
                            </span>
                            <span className="font-mono text-[11px] text-slate-300">
                              {ev.timestamp}
                            </span>
                          </div>
                          <p className="mt-1.5 font-mono text-[11px] text-slate-300">
                            Actor: {ev.actor_uid}{" "}
                            {ev.actor_role ? `(${ev.actor_role})` : ""}
                          </p>
                          <pre className="mt-2 overflow-x-auto rounded border border-slate-800 bg-slate-900 p-2 font-mono text-[11px] text-slate-200">
                            {JSON.stringify(ev.metadata, null, 2)}
                          </pre>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* AI Mitigation Strategy Recommendation Drawer/Modal */}

        {selectedMitigationRisk && (
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="ai-mitigation-dialog-title"
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4"
          >
            <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-purple-500/50 bg-slate-900 p-6 shadow-2xl">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div>
                  <span className="rounded border border-purple-500/60 bg-purple-950 px-2 py-0.5 font-mono text-[11px] font-semibold text-purple-200">
                    Vertex AI Gemini 2.5 Flash
                  </span>
                  <h2
                    id="ai-mitigation-dialog-title"
                    className="mt-1 text-base font-bold text-white"
                  >
                    AI Proactive Mitigation: {selectedMitigationRisk.title}
                  </h2>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedMitigationRisk(null)}
                  className="min-h-[44px] min-w-[44px] rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400"
                >
                  Close
                </button>
              </div>

              {isLoadingMitigation ? (
                <div className="py-12 text-center">
                  <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-purple-500 border-t-transparent" />
                  <p className="mt-3 text-xs text-purple-200">
                    Synthesizing multi-phase proactive mitigation plan and C-suite escalation brief...
                  </p>
                </div>
              ) : aiMitigationPlan ? (
                <div className="mt-4 space-y-4 text-xs">
                  {/* Current vs Residual Severity */}
                  <div className="grid grid-cols-2 gap-3 rounded-lg border border-slate-800 bg-slate-950 p-3">
                    <div>
                      <div className="text-[11px] text-slate-400">Current Assessment</div>
                      <div className="mt-0.5 font-mono text-xs font-bold text-rose-300">
                        Severity: {selectedMitigationRisk.severity_score}/25 (Impact {selectedMitigationRisk.impact} x Prob {selectedMitigationRisk.probability})
                      </div>
                    </div>
                    <div>
                      <div className="text-[11px] text-slate-400">Projected Residual Target</div>
                      <div className="mt-0.5 font-mono text-xs font-bold text-emerald-300">
                        Severity: {aiMitigationPlan.residual_severity_score}/25 (Impact {aiMitigationPlan.residual_impact} x Prob {aiMitigationPlan.residual_probability})
                      </div>
                    </div>
                  </div>

                  {/* Proactive Mitigation Strategy */}
                  <div>
                    <h3 className="font-semibold uppercase tracking-wider text-purple-200">
                      Multi-Phase Proactive Treatment Strategy
                    </h3>
                    <div className="mt-1.5 whitespace-pre-line rounded-lg border border-slate-800 bg-slate-950 p-3 text-slate-200 leading-relaxed">
                      {aiMitigationPlan.mitigation_strategy}
                    </div>
                  </div>

                  {/* Suggested SLA Action Items */}
                  {aiMitigationPlan.suggested_action_items.length > 0 && (
                    <div>
                      <h3 className="font-semibold uppercase tracking-wider text-purple-200">
                        Recommended Action Items &amp; SLA Milestones
                      </h3>
                      <div className="mt-1.5 space-y-2">
                        {aiMitigationPlan.suggested_action_items.map((item, idx) => (
                          <div
                            key={idx}
                            className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-800 bg-slate-950 p-2.5 text-xs"
                          >
                            <span className="font-medium text-slate-100">{item.action}</span>
                            <div className="flex items-center gap-2 font-mono text-[11px]">
                              {item.owner_role && (
                                <span className="rounded bg-slate-800 px-2 py-0.5 text-slate-300">
                                  {item.owner_role}
                                </span>
                              )}
                              {item.timeline && (
                                <span className="rounded border border-amber-500/60 bg-amber-950 px-2 py-0.5 text-amber-200">
                                  {item.timeline}
                                </span>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Executive Escalation Brief */}
                  <div>
                    <h3 className="font-semibold uppercase tracking-wider text-purple-200">
                      Executive Steering Committee Escalation Brief
                    </h3>
                    <div className="mt-1.5 rounded-lg border border-slate-800 bg-slate-950 p-3 text-slate-200 leading-relaxed">
                      {aiMitigationPlan.executive_escalation_brief}
                    </div>
                  </div>

                  {/* One-Click Apply */}
                  <div className="flex justify-end gap-2 pt-3 border-t border-slate-800">
                    <button
                      type="button"
                      onClick={() => setSelectedMitigationRisk(null)}
                      className="min-h-[44px] rounded-lg border border-slate-700 px-4 py-2 font-semibold text-slate-200 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400"
                    >
                      Dismiss
                    </button>
                    {canEditRisks && (
                      <button
                        type="button"
                        disabled={isApplyingMitigation}
                        onClick={handleApplyAiMitigation}
                        className="min-h-[44px] rounded-lg bg-purple-600 px-5 py-2 font-semibold text-white hover:bg-purple-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400 disabled:opacity-50"
                      >
                        {isApplyingMitigation ? "Applying Plan..." : "One-Click Apply Mitigation to Risk"}
                      </button>
                    )}
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        )}

        {/* AI Emerging Risk Discovery Modal */}
        {showAiDiscoveryModal && (
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="ai-discovery-dialog-title"
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4"
          >
            <div className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-xl border border-purple-500/50 bg-slate-900 p-6 shadow-2xl">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div>
                  <span className="rounded border border-purple-500/60 bg-purple-950 px-2 py-0.5 font-mono text-[11px] font-semibold text-purple-200">
                    Pulse Drop Telemetry (&gt;15 pts or &lt;40)
                  </span>
                  <h2
                    id="ai-discovery-dialog-title"
                    className="mt-1 text-base font-bold text-white"
                  >
                    AI Discovered Emerging Risks ({aiDiscoveredRisks.length})
                  </h2>
                </div>
                <button
                  type="button"
                  onClick={() => setShowAiDiscoveryModal(false)}
                  className="min-h-[44px] min-w-[44px] rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400"
                >
                  Close
                </button>
              </div>

              {aiDiscoverySummary && (
                <div className="mt-3 rounded-lg border border-purple-500/30 bg-purple-950/40 p-3 text-xs text-purple-200">
                  {aiDiscoverySummary}
                </div>
              )}

              {aiDiscoveredRisks.length === 0 ? (
                <div className="py-10 text-center text-xs text-slate-300">
                  No emerging pulse-drop risks detected in recent meetings. All stakeholder sentiment trajectories remain stable.
                </div>
              ) : (
                <div className="mt-4 space-y-4">
                  {aiDiscoveredRisks.map((item, idx) => (
                    <div
                      key={idx}
                      className="rounded-xl border border-slate-800 bg-slate-950 p-4 text-xs space-y-2.5"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className="rounded border border-rose-500/60 bg-rose-950 px-2.5 py-0.5 font-mono text-[11px] font-bold text-rose-200">
                            {item.severity_band} ({item.severity_score}/25)
                          </span>
                          <span className="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 font-mono text-[11px] text-slate-300">
                            {item.category}
                          </span>
                        </div>
                        <span className="font-mono text-[11px] text-amber-300">
                          {item.trigger_reason}
                        </span>
                      </div>

                      <h3 className="text-sm font-bold text-white">{item.title}</h3>
                      <p className="text-slate-300 leading-relaxed">{item.description}</p>

                      {item.associated_groups.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                          {item.associated_groups.map((grp) => (
                            <span
                              key={grp}
                              className="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 font-mono text-[11px] text-slate-300"
                            >
                              {grp}
                            </span>
                          ))}
                        </div>
                      )}

                      <div className="rounded border border-slate-800/80 bg-slate-900/60 p-2.5">
                        <div className="font-semibold text-purple-200 uppercase tracking-wide text-[11px]">
                          Proposed Proactive Mitigation:
                        </div>
                        <p className="mt-1 whitespace-pre-line text-slate-300 text-[11px]">
                          {item.mitigation_strategy}
                        </p>
                      </div>

                      <div className="flex justify-end pt-2">
                        <button
                          type="button"
                          disabled={registeringRiskIdx === idx}
                          onClick={() => void handleRegisterDiscoveredRisk(item, idx)}
                          className="min-h-[44px] rounded-lg bg-indigo-600 px-4 py-2 font-semibold text-white hover:bg-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 disabled:opacity-50"
                        >
                          {registeringRiskIdx === idx ? "Registering..." : "One-Click Register Risk"}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </main>

    </div>
  );
};
