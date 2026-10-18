import React, { useCallback, useEffect, useState } from "react";
import {
  createProject,
  DEFAULT_CANONICAL_GROUPS,
  fetchProjects,
  ProjectAISuggestionResponse,
  ProjectWorkspace,
  sendProjectInvitation,
  suggestProjectGroupsWithAI,
  updateProject,
  UserRole,
} from "../api/authApi";

interface ProjectsPageProps {
  idToken: string;
  userRole: UserRole;
  onBackToWorkspace: () => void;
}

export const ProjectsPage: React.FC<ProjectsPageProps> = ({
  idToken,
  userRole,
  onBackToWorkspace,
}) => {
  const canManageProjects =
    userRole === "ADMIN" || userRole === "EXECUTIVE" || userRole === "MANAGER";

  const [projects, setProjects] = useState<ProjectWorkspace[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(
    null
  );
  const [isCreatingNew, setIsCreatingNew] = useState<boolean>(false);

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [isSuggestingAI, setIsSuggestingAI] = useState<boolean>(false);

  // Project Editor Form State
  const [slugInput, setSlugInput] = useState<string>("proj-enterprise-01");
  const [nameInput, setNameInput] = useState<string>(
    "Core Banking Cloud Migration"
  );
  const [companyInput, setCompanyInput] = useState<string>(
    "Meridian Financial Group"
  );
  const [descriptionInput, setDescriptionInput] = useState<string>(
    "Multi-phase ledger modernization, treasury API integration, and regulatory audit readiness."
  );
  const [canonicalGroups, setCanonicalGroups] = useState<string[]>([
    ...DEFAULT_CANONICAL_GROUPS,
  ]);
  const [newGroupChip, setNewGroupChip] = useState<string>("");
  const [pulseDropDelta, setPulseDropDelta] = useState<number>(15);
  const [minimumPulseScore, setMinimumPulseScore] = useState<number>(40);
  const [escalationEnabled, setEscalationEnabled] = useState<boolean>(true);

  // AI Suggestion State
  const [aiSuggestion, setAiSuggestion] =
    useState<ProjectAISuggestionResponse | null>(null);

  // Project Invitation Form State
  const [inviteEmail, setInviteEmail] = useState<string>("");
  const [isSendingInvite, setIsSendingInvite] = useState<boolean>(false);

  const applyProjectToEditor = useCallback((project: ProjectWorkspace) => {
    setIsCreatingNew(false);
    setSelectedProjectId(project.project_id);
    setSlugInput(project.project_id);
    setNameInput(project.name);
    setCompanyInput(project.company_name || "");
    setDescriptionInput(project.description || "");
    setCanonicalGroups(
      project.canonical_groups && project.canonical_groups.length > 0
        ? [...project.canonical_groups]
        : [...DEFAULT_CANONICAL_GROUPS]
    );
    setPulseDropDelta(project.alert_thresholds?.pulse_drop_delta ?? 15);
    setMinimumPulseScore(project.alert_thresholds?.minimum_pulse_score ?? 40);
    setEscalationEnabled(project.alert_thresholds?.escalation_enabled ?? true);
    setAiSuggestion(null);
    setFormError(null);
  }, []);

  const loadProjects = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const fetched = await fetchProjects(idToken);
      setProjects(fetched);
      if (fetched.length > 0) {
        const current =
          fetched.find((p) => p.project_id === selectedProjectId) || fetched[0];
        applyProjectToEditor(current);
      } else {
        setIsCreatingNew(true);
        setSelectedProjectId(null);
      }
    } catch (err) {
      setLoadError(
        err instanceof Error
          ? err.message
          : "Unable to load project workspaces from the server."
      );
    } finally {
      setIsLoading(false);
    }
  }, [idToken, selectedProjectId, applyProjectToEditor]);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  const handleStartNewProject = () => {
    setIsCreatingNew(true);
    setSelectedProjectId(null);
    setSlugInput(`proj-${Math.random().toString(36).slice(2, 7)}`);
    setNameInput("");
    setCompanyInput("");
    setDescriptionInput("");
    setCanonicalGroups([...DEFAULT_CANONICAL_GROUPS]);
    setPulseDropDelta(15);
    setMinimumPulseScore(40);
    setEscalationEnabled(true);
    setAiSuggestion(null);
    setFormError(null);
    setStatusMessage(null);
  };

  const handleSuggestWithAI = async () => {
    const targetProjectId = slugInput.trim() || "proj-draft";
    setIsSuggestingAI(true);
    setFormError(null);
    setStatusMessage(null);
    try {
      const suggestion = await suggestProjectGroupsWithAI(
        idToken,
        targetProjectId,
        {
          name: nameInput.trim() || targetProjectId,
          company_name: companyInput.trim(),
          description: descriptionInput.trim(),
        }
      );
      setAiSuggestion(suggestion);
      setCanonicalGroups(suggestion.suggested_canonical_groups);
      setPulseDropDelta(
        suggestion.recommended_alert_thresholds.pulse_drop_delta
      );
      setMinimumPulseScore(
        suggestion.recommended_alert_thresholds.minimum_pulse_score
      );
      setEscalationEnabled(
        suggestion.recommended_alert_thresholds.escalation_enabled
      );
      setStatusMessage(
        `AI recommended ${suggestion.suggested_canonical_groups.length} canonical stakeholder groups (${suggestion.inference_mode}).`
      );
    } catch (err) {
      setFormError(
        err instanceof Error
          ? err.message
          : "Unable to generate canonical group suggestions."
      );
    } finally {
      setIsSuggestingAI(false);
    }
  };

  const handleAddGroupChip = () => {
    const trimmed = newGroupChip.trim();
    if (!trimmed) return;
    if (canonicalGroups.includes(trimmed)) {
      setNewGroupChip("");
      return;
    }
    setCanonicalGroups((prev) => [...prev, trimmed]);
    setNewGroupChip("");
  };

  const handleRemoveGroupChip = (groupToRemove: string) => {
    if (canonicalGroups.length <= 2) {
      setFormError(
        "A project workspace requires at least 2 canonical stakeholder groups."
      );
      return;
    }
    setFormError(null);
    setCanonicalGroups((prev) => prev.filter((g) => g !== groupToRemove));
  };

  const handleSaveProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canManageProjects) return;

    setFormError(null);
    setStatusMessage(null);

    if (canonicalGroups.length < 2) {
      setFormError(
        "Please configure at least 2 canonical stakeholder groups before saving."
      );
      return;
    }

    setIsSaving(true);
    try {
      const thresholdsPayload = {
        pulse_drop_delta: pulseDropDelta,
        minimum_pulse_score: minimumPulseScore,
        escalation_enabled: escalationEnabled,
        escalation_intervals_hours: [24, 48, 72],
      };

      if (isCreatingNew || !selectedProjectId) {
        const cleanSlug = slugInput.trim();
        const cleanName = nameInput.trim();
        if (cleanSlug.length < 2 || cleanName.length < 2) {
          setFormError("Project ID and Project Name must be at least 2 characters.");
          setIsSaving(false);
          return;
        }
        const created = await createProject(idToken, {
          project_id: cleanSlug,
          name: cleanName,
          company_name: companyInput.trim(),
          description: descriptionInput.trim(),
          canonical_groups: canonicalGroups,
          alert_thresholds: thresholdsPayload,
        });
        setProjects((prev) => [
          created,
          ...prev.filter((p) => p.project_id !== created.project_id),
        ]);
        applyProjectToEditor(created);
        setStatusMessage(
          `Created project workspace '${created.name}' (${created.project_id}) with ${created.canonical_groups.length} canonical groups.`
        );
      } else {
        const updated = await updateProject(idToken, selectedProjectId, {
          name: nameInput.trim(),
          company_name: companyInput.trim(),
          description: descriptionInput.trim(),
          canonical_groups: canonicalGroups,
          alert_thresholds: thresholdsPayload,
        });
        setProjects((prev) =>
          prev.map((p) =>
            p.project_id === updated.project_id ? updated : p
          )
        );
        applyProjectToEditor(updated);
        setStatusMessage(
          `Saved governance taxonomy and alert thresholds for '${updated.name}'.`
        );
      }
    } catch (err) {
      setFormError(
        err instanceof Error ? err.message : "Failed to save project governance."
      );
    } finally {
      setIsSaving(false);
    }
  };

  const handleDispatchInvitation = async (e: React.FormEvent) => {
    e.preventDefault();
    const targetProjectId = selectedProjectId || slugInput.trim();
    if (!targetProjectId || !inviteEmail.trim()) return;

    setIsSendingInvite(true);
    setFormError(null);
    setStatusMessage(null);
    try {
      const inv = await sendProjectInvitation(
        idToken,
        targetProjectId,
        inviteEmail.trim()
      );
      setStatusMessage(
        `Project invitation ${inv.invitation_id} dispatched to ${inv.invitee_email} for ${inv.project_id}.`
      );
      setInviteEmail("");
    } catch (err) {
      setFormError(
        err instanceof Error ? err.message : "Failed to send project invitation."
      );
    } finally {
      setIsSendingInvite(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-900/90 px-4 py-4 sm:px-6">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="rounded bg-indigo-500/20 px-2.5 py-0.5 font-mono text-xs font-semibold text-indigo-300">
                GOVERNANCE & TAXONOMY
              </span>
              <h1 className="text-lg font-bold text-white">
                Project Workspaces & AI Group Taxonomy
              </h1>
            </div>
            <p className="mt-1 text-xs text-slate-300">
              Configure canonical stakeholder groups, pulse drop triggers, and stakeholder invitations per project.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {canManageProjects && (
              <button
                type="button"
                onClick={handleStartNewProject}
                className="min-h-[44px] rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              >
                + New Project Workspace
              </button>
            )}
            <button
              type="button"
              onClick={onBackToWorkspace}
              className="min-h-[44px] rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-medium text-slate-200 hover:bg-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
            >
              Back to Workspace Overview
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-6 px-4 py-6 sm:px-6">
        {statusMessage && (
          <div
            role="status"
            className="flex items-center justify-between rounded-lg border border-emerald-500/40 bg-emerald-950/50 px-4 py-3 text-xs text-emerald-200"
          >
            <span>{statusMessage}</span>
            <button
              type="button"
              onClick={() => setStatusMessage(null)}
              className="min-h-[44px] px-2 font-semibold text-emerald-300 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
            >
              Dismiss
            </button>
          </div>
        )}

        {loadError && (
          <div
            role="alert"
            className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-rose-500/40 bg-rose-950/50 px-4 py-3 text-xs text-rose-200"
          >
            <span>{loadError}</span>
            <button
              type="button"
              onClick={() => void loadProjects()}
              className="min-h-[44px] rounded-lg border border-rose-400/40 px-3 py-1.5 font-semibold text-rose-200 hover:bg-rose-900/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400"
            >
              Retry Loading
            </button>
          </div>
        )}

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          {/* Left Column: Accessible Project List */}
          <aside className="space-y-4 lg:col-span-4">
            <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-white">
                  Project Workspaces ({projects.length})
                </h2>
                <button
                  type="button"
                  onClick={() => void loadProjects()}
                  className="min-h-[44px] rounded-lg px-2.5 text-xs font-medium text-indigo-300 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                >
                  Refresh
                </button>
              </div>

              {isLoading ? (
                <div className="mt-4 space-y-2.5" aria-busy="true">
                  <div className="h-14 animate-pulse rounded-lg bg-slate-800/70" />
                  <div className="h-14 animate-pulse rounded-lg bg-slate-800/70" />
                </div>
              ) : projects.length === 0 ? (
                <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950 p-4 text-xs text-slate-300">
                  No project workspaces have been initialized yet. Use the editor to create your first workspace and generate canonical stakeholder groups with AI.
                </div>
              ) : (
                <ul className="mt-3 space-y-2">
                  {projects.map((proj) => {
                    const isSelected =
                      !isCreatingNew && selectedProjectId === proj.project_id;
                    return (
                      <li key={proj.project_id}>
                        <button
                          type="button"
                          onClick={() => applyProjectToEditor(proj)}
                          className={`flex min-h-[44px] w-full flex-col items-start rounded-lg border p-3 text-left transition ${
                            isSelected
                              ? "border-indigo-500 bg-indigo-950/40 text-white"
                              : "border-slate-800 bg-slate-950/70 text-slate-200 hover:border-slate-700 hover:bg-slate-800/50"
                          } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400`}
                        >
                          <div className="flex w-full items-center justify-between gap-2">
                            <span className="font-semibold text-xs text-white">
                              {proj.name}
                            </span>
                            <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-[11px] text-emerald-300">
                              {proj.project_id}
                            </span>
                          </div>
                          {proj.company_name && (
                            <span className="mt-1 text-[11px] text-slate-300">
                              Client: {proj.company_name}
                            </span>
                          )}
                          <span className="mt-1.5 text-[11px] text-slate-400">
                            {proj.canonical_groups?.length || 4} canonical groups | Drop alert: -{proj.alert_thresholds?.pulse_drop_delta ?? 15} pts
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </aside>

          {/* Right Column: Project Governance & AI Group Taxonomy Editor */}
          <section className="space-y-6 lg:col-span-8">
            <form
              onSubmit={handleSaveProject}
              className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-5"
            >
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
                <div>
                  <h2 className="text-base font-bold text-white">
                    {isCreatingNew
                      ? "Create New Project Workspace"
                      : `Project Governance: ${nameInput || selectedProjectId}`}
                  </h2>
                  <p className="mt-0.5 text-xs text-slate-300">
                    Define project context, generate AI-calibrated stakeholder groups, and set pulse SLA thresholds.
                  </p>
                </div>

                <button
                  type="button"
                  onClick={handleSuggestWithAI}
                  disabled={isSuggestingAI || !canManageProjects}
                  className="min-h-[44px] rounded-lg border border-indigo-400/50 bg-indigo-950/70 px-4 py-2 text-xs font-semibold text-indigo-200 hover:bg-indigo-900/70 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                >
                  {isSuggestingAI
                    ? "Synthesizing Groups..."
                    : "Suggest Canonical Groups with AI"}
                </button>
              </div>

              {formError && (
                <div
                  role="alert"
                  className="rounded-lg border border-rose-500/40 bg-rose-950/50 px-4 py-3 text-xs text-rose-200"
                >
                  {formError}
                </div>
              )}

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label
                    htmlFor="project-slug-input"
                    className="block text-xs font-medium text-slate-200"
                  >
                    Project ID (Slug)
                  </label>
                  <input
                    id="project-slug-input"
                    type="text"
                    value={slugInput}
                    onChange={(e) => setSlugInput(e.target.value)}
                    disabled={!isCreatingNew || !canManageProjects}
                    required
                    className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-xs text-slate-100 disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                  />
                </div>

                <div>
                  <label
                    htmlFor="project-name-input"
                    className="block text-xs font-medium text-slate-200"
                  >
                    Project Name
                  </label>
                  <input
                    id="project-name-input"
                    type="text"
                    value={nameInput}
                    onChange={(e) => setNameInput(e.target.value)}
                    disabled={!canManageProjects}
                    placeholder="e.g. Core Banking Cloud Migration"
                    required
                    className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                  />
                </div>
              </div>

              <div>
                <label
                  htmlFor="project-company-input"
                  className="block text-xs font-medium text-slate-200"
                >
                  Client / Organization Name
                </label>
                <input
                  id="project-company-input"
                  type="text"
                  value={companyInput}
                  onChange={(e) => setCompanyInput(e.target.value)}
                  disabled={!canManageProjects}
                  placeholder="e.g. Meridian Financial Group"
                  className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                />
              </div>

              <div>
                <label
                  htmlFor="project-description-input"
                  className="block text-xs font-medium text-slate-200"
                >
                  Project Scope & Domain Context (Used by AI Governance Engine)
                </label>
                <textarea
                  id="project-description-input"
                  rows={3}
                  value={descriptionInput}
                  onChange={(e) => setDescriptionInput(e.target.value)}
                  disabled={!canManageProjects}
                  placeholder="Describe deliverables, regulatory constraints, and key stakeholder teams..."
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                />
              </div>

              {/* AI Governance Suggestion Rationale Banner */}
              {aiSuggestion && (
                <div className="rounded-xl border border-indigo-500/40 bg-indigo-950/30 p-4 space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-xs font-semibold text-indigo-200">
                      AI Governance Recommendation ({aiSuggestion.model_version})
                    </span>
                    <span className="rounded bg-indigo-500/20 px-2.5 py-0.5 font-mono text-[11px] font-semibold text-indigo-300">
                      {aiSuggestion.inference_mode}
                    </span>
                  </div>
                  <p className="text-xs leading-relaxed text-slate-200">
                    {aiSuggestion.rationale}
                  </p>
                  {aiSuggestion.suggested_risk_categories.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5 pt-1">
                      <span className="text-[11px] font-medium text-slate-300">
                        Priority Risk Categories:
                      </span>
                      {aiSuggestion.suggested_risk_categories.map((cat) => (
                        <span
                          key={cat}
                          className="rounded border border-amber-500/40 bg-amber-950/40 px-2 py-0.5 font-mono text-[11px] text-amber-200"
                        >
                          {cat}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Canonical Stakeholder Group Chips */}
              <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-950/70 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h3 className="text-xs font-semibold text-white">
                      Canonical Stakeholder Groups ({canonicalGroups.length})
                    </h3>
                    <p className="text-[11px] text-slate-300">
                      Adjudicators map ephemeral session speakers to these group buckets during transcript verification.
                    </p>
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  {canonicalGroups.map((group) => (
                    <span
                      key={group}
                      className="inline-flex min-h-[36px] items-center gap-2 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1 text-xs font-medium text-emerald-300"
                    >
                      <span>{group}</span>
                      {canManageProjects && (
                        <button
                          type="button"
                          onClick={() => handleRemoveGroupChip(group)}
                          aria-label={`Remove ${group}`}
                          className="rounded px-1.5 py-0.5 text-slate-400 hover:bg-rose-950/70 hover:text-rose-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400"
                        >
                          x
                        </button>
                      )}
                    </span>
                  ))}
                </div>

                {canManageProjects && (
                  <div className="flex flex-wrap items-center gap-2 pt-2">
                    <input
                      type="text"
                      value={newGroupChip}
                      onChange={(e) => setNewGroupChip(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          handleAddGroupChip();
                        }
                      }}
                      placeholder="Add custom stakeholder group..."
                      aria-label="New canonical stakeholder group"
                      className="min-h-[44px] flex-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                    />
                    <button
                      type="button"
                      onClick={handleAddGroupChip}
                      className="min-h-[44px] rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                    >
                      Add Group
                    </button>
                  </div>
                )}
              </div>

              {/* Alert & SLA Thresholds */}
              <div className="grid grid-cols-1 gap-4 rounded-xl border border-slate-800 bg-slate-950/70 p-4 sm:grid-cols-3">
                <div>
                  <label
                    htmlFor="pulse-drop-delta-input"
                    className="block text-xs font-medium text-slate-200"
                  >
                    Pulse Drop Alert Delta (pts)
                  </label>
                  <input
                    id="pulse-drop-delta-input"
                    type="number"
                    min={5}
                    max={50}
                    value={pulseDropDelta}
                    onChange={(e) =>
                      setPulseDropDelta(Number(e.target.value) || 15)
                    }
                    disabled={!canManageProjects}
                    className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 font-mono text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                  />
                  <span className="mt-1 block text-[11px] text-slate-400">
                    Triggers alert if group pulse drops by this amount.
                  </span>
                </div>

                <div>
                  <label
                    htmlFor="minimum-pulse-score-input"
                    className="block text-xs font-medium text-slate-200"
                  >
                    Minimum Group Pulse Floor
                  </label>
                  <input
                    id="minimum-pulse-score-input"
                    type="number"
                    min={10}
                    max={80}
                    value={minimumPulseScore}
                    onChange={(e) =>
                      setMinimumPulseScore(Number(e.target.value) || 40)
                    }
                    disabled={!canManageProjects}
                    className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 font-mono text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                  />
                  <span className="mt-1 block text-[11px] text-slate-400">
                    Scores below this floor flag automatic risk review.
                  </span>
                </div>

                <div className="flex flex-col justify-between">
                  <span className="block text-xs font-medium text-slate-200">
                    Automated SLA Escalation
                  </span>
                  <label className="mt-1 flex min-h-[44px] cursor-pointer items-center gap-2.5 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-200">
                    <input
                      type="checkbox"
                      checked={escalationEnabled}
                      onChange={(e) => setEscalationEnabled(e.target.checked)}
                      disabled={!canManageProjects}
                      className="h-4 w-4 rounded border-slate-600 text-indigo-600 focus:ring-indigo-500"
                    />
                    <span>24h / 48h / 72h Tiers</span>
                  </label>
                  <span className="mt-1 block text-[11px] text-slate-400">
                    Dispatches SLA reminders for unmitigated risks.
                  </span>
                </div>
              </div>

              {canManageProjects && (
                <div className="flex justify-end pt-2">
                  <button
                    type="submit"
                    disabled={isSaving}
                    className="min-h-[44px] rounded-lg bg-indigo-600 px-5 py-2.5 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                  >
                    {isSaving
                      ? "Saving Workspace..."
                      : isCreatingNew
                        ? "Create Project Workspace"
                        : "Save Project Governance"}
                  </button>
                </div>
              )}
            </form>

            {/* Project Invitation Card */}
            {canManageProjects && (
              <form
                onSubmit={handleDispatchInvitation}
                className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4"
              >
                <div>
                  <h3 className="text-sm font-semibold text-white">
                    Invite Stakeholder to{" "}
                    <span className="font-mono text-emerald-300">
                      {selectedProjectId || slugInput}
                    </span>
                  </h3>
                  <p className="mt-0.5 text-xs text-slate-300">
                    Send an email invitation so quarantined External Stakeholders can accept access to this workspace.
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <input
                    type="email"
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                    placeholder="stakeholder@enterprise.com"
                    aria-label="Stakeholder email address"
                    required
                    className="min-h-[44px] flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                  />
                  <button
                    type="submit"
                    disabled={isSendingInvite}
                    className="min-h-[44px] rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
                  >
                    {isSendingInvite
                      ? "Sending Invitation..."
                      : "Dispatch Project Invitation"}
                  </button>
                </div>
              </form>
            )}
          </section>
        </div>
      </main>
    </div>
  );
};
