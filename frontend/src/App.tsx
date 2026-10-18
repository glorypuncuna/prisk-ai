import React, { useCallback, useEffect, useState } from "react";
import {
  acceptProjectInvitation,
  claimInitialExecutive,
  fetchCurrentUserProfile,
  fetchPendingInvitations,
  ProjectInvitation,
  sendProjectInvitation,
  updateUserRole,
  UserProfile,
  UserRole,
} from "./api/authApi";
import { QuarantinedOnboardingView } from "./components/QuarantinedOnboardingView";
import {
  clearSession,
  FirebaseIdentitySession,
  getStoredSession,
  refreshIdToken,
} from "./lib/firebaseClient";
import { AdminUsersPage } from "./pages/AdminUsersPage";
import { AdjudicationWorkspacePage } from "./pages/AdjudicationWorkspacePage";
import { AuthPage } from "./pages/AuthPage";
import { CalendarArchivePage } from "./pages/CalendarArchivePage";
import { ComplianceConsolePage } from "./pages/ComplianceConsolePage";
import { MeetingCapturePage } from "./pages/MeetingCapturePage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { PulseDashboardPage } from "./pages/PulseDashboardPage";
import { RiskRegisterPage } from "./pages/RiskRegisterPage";

export const App: React.FC = () => {
  const [session, setSession] = useState<FirebaseIdentitySession | null>(() =>
    getStoredSession()
  );
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [pendingInvitations, setPendingInvitations] = useState<
    ProjectInvitation[]
  >([]);
  const [isBusy, setIsBusy] = useState(false);

  const [inviteProjectId, setInviteProjectId] = useState("proj-alpha");
  const [inviteEmail, setInviteEmail] = useState("");
  const [targetUid, setTargetUid] = useState("");
  const [targetRole, setTargetRole] = useState<UserRole>("ADJUDICATOR");
  const [statusBanner, setStatusBanner] = useState<string | null>(null);
  const [currentView, setCurrentView] = useState<
    | "workspace"
    | "projects"
    | "adjudication"
    | "capture"
    | "calendar"
    | "risks"
    | "admin_users"
    | "pulse"
    | "compliance"
  >(() => {
    if (window.location.pathname.startsWith("/admin")) return "admin_users";
    if (window.location.pathname.startsWith("/projects")) return "projects";
    if (window.location.pathname.startsWith("/adjudication"))
      return "adjudication";
    if (window.location.pathname.startsWith("/capture")) return "capture";
    if (window.location.pathname.startsWith("/calendar")) return "calendar";
    if (window.location.pathname.startsWith("/risks")) return "risks";
    if (window.location.pathname.startsWith("/compliance")) return "compliance";
    if (
      window.location.pathname.startsWith("/pulse") ||
      window.location.pathname.startsWith("/analytics")
    )
      return "pulse";
    return "workspace";
  });

  useEffect(() => {
    const handlePopState = () => {
      if (window.location.pathname.startsWith("/admin")) {
        setCurrentView("admin_users");
      } else if (window.location.pathname.startsWith("/projects")) {
        setCurrentView("projects");
      } else if (window.location.pathname.startsWith("/adjudication")) {
        setCurrentView("adjudication");
      } else if (window.location.pathname.startsWith("/capture")) {
        setCurrentView("capture");
      } else if (window.location.pathname.startsWith("/calendar")) {
        setCurrentView("calendar");
      } else if (window.location.pathname.startsWith("/risks")) {
        setCurrentView("risks");
      } else if (window.location.pathname.startsWith("/compliance")) {
        setCurrentView("compliance");
      } else if (
        window.location.pathname.startsWith("/pulse") ||
        window.location.pathname.startsWith("/analytics")
      ) {
        setCurrentView("pulse");
      } else {
        setCurrentView("workspace");
      }
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);


  const loadUserContext = useCallback(async (idToken: string) => {
    try {
      const [userProf, invites] = await Promise.all([
        fetchCurrentUserProfile(idToken),
        fetchPendingInvitations(idToken).catch(() => []),
      ]);
      setProfile(userProf);
      setPendingInvitations(invites);
    } catch {
      clearSession();
      setSession(null);
      setProfile(null);
    }
  }, []);

  useEffect(() => {
    if (session?.idToken && !profile) {
      void loadUserContext(session.idToken);
    }
  }, [session, profile, loadUserContext]);

  const handleAuthenticated = async (
    newSession: FirebaseIdentitySession,
    newProfile: UserProfile
  ) => {
    setSession(newSession);
    setProfile(newProfile);
    const invites = await fetchPendingInvitations(newSession.idToken).catch(
      () => []
    );
    setPendingInvitations(invites);
  };

  const handleSignOut = () => {
    clearSession();
    setSession(null);
    setProfile(null);
    setPendingInvitations([]);
  };

  const handleAcceptInvitation = async (
    projectId: string,
    invitationId: string
  ) => {
    if (!session) return;
    setIsBusy(true);
    try {
      const updatedProfile = await acceptProjectInvitation(
        session.idToken,
        projectId,
        invitationId
      );
      await refreshIdToken();
      setProfile(updatedProfile);
      const remaining = await fetchPendingInvitations(session.idToken).catch(
        () => []
      );
      setPendingInvitations(remaining);
    } finally {
      setIsBusy(false);
    }
  };

  const handleSendInvitation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!session) return;
    setIsBusy(true);
    setStatusBanner(null);
    try {
      const inv = await sendProjectInvitation(
        session.idToken,
        inviteProjectId,
        inviteEmail
      );
      setStatusBanner(
        `Invitation ${inv.invitation_id} dispatched to ${inv.invitee_email} for project ${inv.project_id}.`
      );
      setInviteEmail("");
    } catch (err) {
      setStatusBanner(
        err instanceof Error ? err.message : "Failed to send invitation"
      );
    } finally {
      setIsBusy(false);
    }
  };

  const handleElevateRole = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!session) return;
    setIsBusy(true);
    setStatusBanner(null);
    try {
      const updated = await updateUserRole(
        session.idToken,
        targetUid,
        targetRole
      );
      setStatusBanner(
        `Updated user ${updated.uid} role to ${updated.role} and synced Firebase Custom Claims.`
      );
      setTargetUid("");
    } catch (err) {
      setStatusBanner(
        err instanceof Error ? err.message : "Failed to update user role"
      );
    } finally {
      setIsBusy(false);
    }
  };

  const handleClaimExecutive = async () => {
    if (!session) return;
    setIsBusy(true);
    setStatusBanner(null);
    try {
      const updated = await claimInitialExecutive(session.idToken);
      await refreshIdToken();
      setProfile(updated);
      setStatusBanner("Congratulations! You have claimed the initial EXECUTIVE role for your organization.");
    } catch (err) {
      setStatusBanner(err instanceof Error ? err.message : "Failed to claim executive role");
    } finally {
      setIsBusy(false);
    }
  };

  if (!session || !profile) {
    return <AuthPage onAuthenticated={handleAuthenticated} />;
  }

  // Quarantined onboarding state for EXTERNAL_STAKEHOLDER with zero assigned projects
  const isQuarantined =
    profile.role === "EXTERNAL_STAKEHOLDER" &&
    profile.assigned_project_ids.length === 0;

  if (isQuarantined) {
    return (
      <QuarantinedOnboardingView
        profile={profile}
        pendingInvitations={pendingInvitations}
        onAcceptInvitation={handleAcceptInvitation}
        onClaimExecutive={handleClaimExecutive}
        onSignOut={handleSignOut}
        isBusy={isBusy}
      />
    );
  }

  if (currentView === "projects") {
    return (
      <ProjectsPage
        idToken={session.idToken}
        userRole={profile.role}
        onBackToWorkspace={() => {
          setCurrentView("workspace");
          window.history.pushState({}, "", "/");
        }}
      />
    );
  }

  if (currentView === "adjudication") {
    return (
      <AdjudicationWorkspacePage
        idToken={session.idToken}
        onBackToWorkspace={() => {
          setCurrentView("workspace");
          window.history.pushState({}, "", "/");
        }}
      />
    );
  }

  if (currentView === "capture") {
    return (
      <MeetingCapturePage
        idToken={session.idToken}
        userRole={profile.role}
        onBackToWorkspace={() => {
          setCurrentView("workspace");
          window.history.pushState({}, "", "/");
        }}
        onOpenAdjudication={() => {
          setCurrentView("adjudication");
          window.history.pushState({}, "", "/adjudication");
        }}
      />
    );
  }

  if (currentView === "calendar") {
    return (
      <CalendarArchivePage
        idToken={session.idToken}
        userRole={profile.role}
        onBackToWorkspace={() => {
          setCurrentView("workspace");
          window.history.pushState({}, "", "/");
        }}
        onOpenAdjudication={() => {
          setCurrentView("adjudication");
          window.history.pushState({}, "", "/adjudication");
        }}
        onOpenCapture={() => {
          setCurrentView("capture");
          window.history.pushState({}, "", "/capture");
        }}
      />
    );
  }

  if (currentView === "risks") {
    return (
      <RiskRegisterPage
        idToken={session.idToken}
        userRole={profile.role}
        onBackToWorkspace={() => {
          setCurrentView("workspace");
          window.history.pushState({}, "", "/");
        }}
        onOpenAdjudication={() => {
          setCurrentView("adjudication");
          window.history.pushState({}, "", "/adjudication");
        }}
      />
    );
  }

  if (currentView === "pulse") {
    return (
      <PulseDashboardPage
        idToken={session.idToken}
        onBackToWorkspace={() => {
          setCurrentView("workspace");
          window.history.pushState({}, "", "/");
        }}
        onOpenAdjudication={() => {
          setCurrentView("adjudication");
          window.history.pushState({}, "", "/adjudication");
        }}
      />
    );
  }

  if (currentView === "compliance") {
    return (
      <ComplianceConsolePage
        idToken={session.idToken}
        userRole={profile.role}
        onBackToWorkspace={() => {
          setCurrentView("workspace");
          window.history.pushState({}, "", "/");
        }}
      />
    );
  }

  if (currentView === "admin_users") {
    if (profile.role === "ADMIN") {
      return (
        <AdminUsersPage
          idToken={session.idToken}
          currentAdminUid={profile.uid}
          onBackToWorkspace={() => {
            setCurrentView("workspace");
            window.history.pushState({}, "", "/");
          }}
        />
      );
    }
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-slate-950 p-6 text-slate-100">
        <div className="max-w-md rounded-xl border border-slate-800 bg-slate-900 p-6 text-center shadow-xl">
          <h2 className="text-base font-bold text-rose-400">Access Restricted</h2>
          <p className="mt-2 text-xs text-slate-300">
            The Super Admin Console is strictly reserved for accounts with the ADMIN role.
          </p>
          <button
            type="button"
            onClick={() => {
              setCurrentView("workspace");
              window.history.pushState({}, "", "/");
            }}
            className="mt-4 min-h-[44px] rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
          >
            Return to Workspace
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* Executive Top Navigation Header */}
      <header className="sticky top-0 z-40 border-b border-slate-800 bg-slate-900/90 backdrop-blur-md">
        {/* Top Info Bar: Brand + User Profile + Sign Out */}
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 font-bold text-white shadow-sm shadow-indigo-600/30">
                pR
              </span>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold tracking-tight text-white">
                    pRiskAI
                  </span>
                  <span className="rounded bg-indigo-500/10 px-1.5 py-0.5 text-[10px] font-mono font-semibold text-indigo-300 border border-indigo-500/20">
                    Enterprise
                  </span>
                </div>
              </div>
            </div>
            <div className="hidden sm:block h-4 w-px bg-slate-800" />
            <p className="hidden sm:block text-xs text-slate-400">
              {profile.first_name} {profile.last_name} ({profile.email})
            </p>
          </div>

          <div className="flex items-center gap-2.5">
            <span className="rounded-full border border-slate-700 bg-slate-800 px-2.5 py-0.5 font-mono text-[11px] font-semibold text-slate-200">
              {profile.role}
            </span>
            <button
              type="button"
              onClick={handleSignOut}
              className="min-h-[36px] rounded-lg border border-slate-750 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-800 hover:text-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
            >
              Sign Out
            </button>
          </div>
        </div>

        {/* Clean Secondary Navigation Strip */}
        <div className="border-t border-slate-800/80 bg-slate-950/60 px-4 sm:px-6">
          <nav
            aria-label="Workspace Modules"
            className="mx-auto flex max-w-7xl items-center gap-1 overflow-x-auto py-2 text-xs no-scrollbar"
          >
            <button
              type="button"
              onClick={() => {
                setCurrentView("workspace");
                window.history.pushState({}, "", "/");
              }}
              className={`rounded-lg px-3 py-1.5 font-medium whitespace-nowrap transition-colors ${
                currentView === "workspace"
                  ? "bg-slate-800 text-white border border-slate-700 font-semibold"
                  : "text-slate-400 hover:bg-slate-850 hover:text-slate-200"
              }`}
            >
              Overview
            </button>
            <button
              type="button"
              onClick={() => {
                setCurrentView("projects");
                window.history.pushState({}, "", "/projects");
              }}
              className="rounded-lg px-3 py-1.5 font-medium whitespace-nowrap text-slate-400 hover:bg-slate-850 hover:text-slate-200 transition-colors"
            >
              Projects &amp; Taxonomies
            </button>
            <button
              type="button"
              onClick={() => {
                setCurrentView("capture");
                window.history.pushState({}, "", "/capture");
              }}
              className="rounded-lg px-3 py-1.5 font-medium whitespace-nowrap text-slate-400 hover:bg-slate-850 hover:text-slate-200 transition-colors"
            >
              Meeting Capture &amp; Bots
            </button>
            <button
              type="button"
              onClick={() => {
                setCurrentView("calendar");
                window.history.pushState({}, "", "/calendar");
              }}
              className="rounded-lg px-3 py-1.5 font-medium whitespace-nowrap text-slate-400 hover:bg-slate-850 hover:text-slate-200 transition-colors"
            >
              Historical Calendar
            </button>
            <button
              type="button"
              onClick={() => {
                setCurrentView("adjudication");
                window.history.pushState({}, "", "/adjudication");
              }}
              className="rounded-lg px-3 py-1.5 font-medium whitespace-nowrap text-slate-400 hover:bg-slate-850 hover:text-slate-200 transition-colors"
            >
              HITL Adjudication
            </button>
            <button
              type="button"
              onClick={() => {
                setCurrentView("risks");
                window.history.pushState({}, "", "/risks");
              }}
              className="rounded-lg px-3 py-1.5 font-medium whitespace-nowrap text-slate-400 hover:bg-slate-850 hover:text-slate-200 transition-colors"
            >
              Risk Register &amp; Heatmap
            </button>
            <button
              type="button"
              onClick={() => {
                setCurrentView("compliance");
                window.history.pushState({}, "", "/compliance");
              }}
              className="rounded-lg px-3 py-1.5 font-medium whitespace-nowrap text-slate-400 hover:bg-slate-850 hover:text-slate-200 transition-colors"
            >
              Compliance &amp; WORM Console
            </button>
            <button
              type="button"
              onClick={() => {
                setCurrentView("pulse");
                window.history.pushState({}, "", "/pulse");
              }}
              className="rounded-lg px-3 py-1.5 font-medium whitespace-nowrap text-slate-400 hover:bg-slate-850 hover:text-slate-200 transition-colors"
            >
              Pulse &amp; Health Analytics
            </button>
            {profile.role === "ADMIN" && (
              <button
                type="button"
                onClick={() => {
                  setCurrentView("admin_users");
                  window.history.pushState({}, "", "/admin/users");
                }}
                className="rounded-lg px-3 py-1.5 font-medium whitespace-nowrap text-slate-400 hover:bg-slate-850 hover:text-slate-200 transition-colors"
              >
                Super Admin Console
              </button>
            )}
          </nav>
        </div>
      </header>

      {/* Main Workspace Dashboard Content */}
      <main className="mx-auto max-w-7xl space-y-8 px-4 py-8 sm:px-6">
        {statusBanner && (
          <div
            role="status"
            className="rounded-xl border border-indigo-500/30 bg-indigo-950/40 px-4 py-3 text-xs text-indigo-200"
          >
            {statusBanner}
          </div>
        )}

        {/* Workspace Intro Hero */}
        <section className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-slate-800 bg-gradient-to-r from-slate-900 via-slate-900 to-slate-950 p-6 sm:p-8">
          <div>
            <span className="text-xs font-semibold uppercase tracking-wider text-indigo-400">
              Workspace Overview
            </span>
            <h1 className="mt-1 text-xl font-bold text-white sm:text-2xl">
              Enterprise Meeting &amp; Risk Intelligence
            </h1>
            <p className="mt-2 max-w-2xl text-xs text-slate-300 leading-relaxed">
              Real-time multi-framework compliance, COSO/ISO 31000 quantitative risk scoring,
              longitudinal sentiment trajectories, and cryptographic WORM audit packages.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-lg border border-slate-800 bg-slate-950/80 px-3 py-2 font-mono text-xs text-slate-300">
              {profile.assigned_project_ids.length > 0
                ? `${profile.assigned_project_ids.length} Active Project(s)`
                : "Global Role Access"}
            </span>
          </div>
        </section>

        {/* Functional Module Capabilities Grid (2 Columns) */}
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400">
              Platform Modules
            </h2>
          </div>

          <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-3">
            {/* Card 1: Risk Register */}
            <div className="flex flex-col justify-between rounded-xl border border-slate-800 bg-slate-900 p-5 transition-all hover:border-slate-700 hover:bg-slate-900/90">
              <div>
                <div className="flex items-center justify-between">
                  <span className="rounded bg-indigo-500/10 px-2 py-0.5 text-[10px] font-semibold text-indigo-300 border border-indigo-500/20">
                    Governance
                  </span>
                  <span className="text-[10px] font-mono text-slate-500">COSO / ISO 31000</span>
                </div>
                <h3 className="mt-3 text-sm font-bold text-white">
                  Risk Register &amp; 5x5 Heatmap
                </h3>
                <p className="mt-1.5 text-xs text-slate-300 leading-relaxed">
                  Quantitative Impact (1-5) and Probability (1-5) severity matrix, 24h/48h/72h SLA escalations, and immutable audit logs.
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setCurrentView("risks");
                  window.history.pushState({}, "", "/risks");
                }}
                className="mt-5 min-h-[38px] w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-200 transition-colors hover:bg-slate-700 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              >
                Open Risk Register →
              </button>
            </div>

            {/* Card 2: Pulse Analytics */}
            <div className="flex flex-col justify-between rounded-xl border border-slate-800 bg-slate-900 p-5 transition-all hover:border-slate-700 hover:bg-slate-900/90">
              <div>
                <div className="flex items-center justify-between">
                  <span className="rounded bg-sky-500/10 px-2 py-0.5 text-[10px] font-semibold text-sky-300 border border-sky-500/20">
                    Analytics
                  </span>
                  <span className="text-[10px] font-mono text-slate-500">TRD §10.4</span>
                </div>
                <h3 className="mt-3 text-sm font-bold text-white">
                  Pulse &amp; Health Analytics
                </h3>
                <p className="mt-1.5 text-xs text-slate-300 leading-relaxed">
                  Interactive multi-series pulse trajectory line charts, Gemini trend synthesis, customizable widgets, and meeting drill-downs.
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setCurrentView("pulse");
                  window.history.pushState({}, "", "/pulse");
                }}
                className="mt-5 min-h-[38px] w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-200 transition-colors hover:bg-slate-700 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              >
                Open Pulse Analytics →
              </button>
            </div>

            {/* Card 3: Compliance & WORM */}
            <div className="flex flex-col justify-between rounded-xl border border-slate-800 bg-slate-900 p-5 transition-all hover:border-slate-700 hover:bg-slate-900/90">
              <div>
                <div className="flex items-center justify-between">
                  <span className="rounded bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-300 border border-emerald-500/20">
                    Compliance
                  </span>
                  <span className="text-[10px] font-mono text-slate-500">WORM SHA-256</span>
                </div>
                <h3 className="mt-3 text-sm font-bold text-white">
                  Compliance &amp; WORM Console
                </h3>
                <p className="mt-1.5 text-xs text-slate-300 leading-relaxed">
                  Sealed multi-framework packages (ISO 31000, COSO, SOC 2, HIPAA, GDPR), zero-verbatim privacy audits, and GDPR Article 17 purges.
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setCurrentView("compliance");
                  window.history.pushState({}, "", "/compliance");
                }}
                className="mt-5 min-h-[38px] w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-200 transition-colors hover:bg-slate-700 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              >
                Open Compliance Console →
              </button>
            </div>

            {/* Card 4: HITL Adjudication */}
            <div className="flex flex-col justify-between rounded-xl border border-slate-800 bg-slate-900 p-5 transition-all hover:border-slate-700 hover:bg-slate-900/90">
              <div>
                <div className="flex items-center justify-between">
                  <span className="rounded bg-indigo-500/10 px-2 py-0.5 text-[10px] font-semibold text-indigo-300 border border-indigo-500/20">
                    Calibration
                  </span>
                  <span className="text-[10px] font-mono text-slate-500">HITL Rollup</span>
                </div>
                <h3 className="mt-3 text-sm font-bold text-white">
                  HITL Adjudication Workspace
                </h3>
                <p className="mt-1.5 text-xs text-slate-300 leading-relaxed">
                  Review redacted transcripts, split mixed-sentiment dialogue bubbles, map session speakers to stakeholder groups, and commit Golden Records.
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setCurrentView("adjudication");
                  window.history.pushState({}, "", "/adjudication");
                }}
                className="mt-5 min-h-[38px] w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-200 transition-colors hover:bg-slate-700 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              >
                Open Adjudication →
              </button>
            </div>

            {/* Card 5: Meeting Capture & Bots */}
            <div className="flex flex-col justify-between rounded-xl border border-slate-800 bg-slate-900 p-5 transition-all hover:border-slate-700 hover:bg-slate-900/90">
              <div>
                <div className="flex items-center justify-between">
                  <span className="rounded bg-slate-800 px-2 py-0.5 text-[10px] font-semibold text-slate-300 border border-slate-700">
                    Ingestion
                  </span>
                  <span className="text-[10px] font-mono text-slate-500">Meetstream.ai</span>
                </div>
                <h3 className="mt-3 text-sm font-bold text-white">
                  Meeting Capture &amp; Bots
                </h3>
                <p className="mt-1.5 text-xs text-slate-300 leading-relaxed">
                  Dispatch recording bots, monitor live webhook statuses, inspect Cloud DLP redaction flags, and initiate AI sentiment scoring.
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setCurrentView("capture");
                  window.history.pushState({}, "", "/capture");
                }}
                className="mt-5 min-h-[38px] w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-200 transition-colors hover:bg-slate-700 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              >
                Open Meeting Capture →
              </button>
            </div>

            {/* Card 6: Historical Calendar */}
            <div className="flex flex-col justify-between rounded-xl border border-slate-800 bg-slate-900 p-5 transition-all hover:border-slate-700 hover:bg-slate-900/90">
              <div>
                <div className="flex items-center justify-between">
                  <span className="rounded bg-slate-800 px-2 py-0.5 text-[10px] font-semibold text-slate-300 border border-slate-700">
                    Archive
                  </span>
                  <span className="text-[10px] font-mono text-slate-500">Month / Week</span>
                </div>
                <h3 className="mt-3 text-sm font-bold text-white">
                  Historical Calendar &amp; Archive
                </h3>
                <p className="mt-1.5 text-xs text-slate-300 leading-relaxed">
                  Browse historical sessions, inspect color-coded group pulse badges, and analyze date-to-date trajectory differences.
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setCurrentView("calendar");
                  window.history.pushState({}, "", "/calendar");
                }}
                className="mt-5 min-h-[38px] w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-200 transition-colors hover:bg-slate-700 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              >
                Open Historical Calendar →
              </button>
            </div>

            {/* Card 7: Projects & Group Taxonomy */}
            <div className="flex flex-col justify-between rounded-xl border border-slate-800 bg-slate-900 p-5 transition-all hover:border-slate-700 hover:bg-slate-900/90">
              <div>
                <div className="flex items-center justify-between">
                  <span className="rounded bg-slate-800 px-2 py-0.5 text-[10px] font-semibold text-slate-300 border border-slate-700">
                    Configuration
                  </span>
                  <span className="text-[10px] font-mono text-slate-500">Vertex AI</span>
                </div>
                <h3 className="mt-3 text-sm font-bold text-white">
                  Projects &amp; AI Group Taxonomy
                </h3>
                <p className="mt-1.5 text-xs text-slate-300 leading-relaxed">
                  Workspace projects, canonical group taxonomy mapping, and Vertex AI text-embedding-004 vector diagnostics.
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setCurrentView("projects");
                  window.history.pushState({}, "", "/projects");
                }}
                className="mt-5 min-h-[38px] w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-200 transition-colors hover:bg-slate-700 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              >
                Manage Projects →
              </button>
            </div>

            {/* Card 8: Super Admin Console (Admins only) */}
            {profile.role === "ADMIN" && (
              <div className="flex flex-col justify-between rounded-xl border border-slate-800 bg-slate-900 p-5 transition-all hover:border-slate-700 hover:bg-slate-900/90">
                <div>
                  <div className="flex items-center justify-between">
                    <span className="rounded bg-rose-500/10 px-2 py-0.5 text-[10px] font-semibold text-rose-300 border border-rose-500/20">
                      Security &amp; RBAC
                    </span>
                    <span className="text-[10px] font-mono text-slate-500">Super Admin</span>
                  </div>
                  <h3 className="mt-3 text-sm font-bold text-white">
                    Super Admin Console
                  </h3>
                  <p className="mt-1.5 text-xs text-slate-300 leading-relaxed">
                    User account governance, quarantined stakeholder onboarding, role elevation, and synchronized Firebase Custom Claims.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setCurrentView("admin_users");
                    window.history.pushState({}, "", "/admin/users");
                  }}
                  className="mt-5 min-h-[38px] w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-200 transition-colors hover:bg-slate-700 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                >
                  Open Admin Console →
                </button>
              </div>
            )}
          </div>
        </section>

        {(profile.role === "MANAGER" || profile.role === "EXECUTIVE") && (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <form
              onSubmit={handleSendInvitation}
              className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4"
            >
              <h3 className="text-sm font-semibold text-white">
                Issue Project Invitation
              </h3>
              <div>
                <label className="block text-xs text-slate-300">
                  Project ID
                </label>
                <input
                  type="text"
                  value={inviteProjectId}
                  onChange={(e) => setInviteProjectId(e.target.value)}
                  required
                  className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-300">
                  Invitee Email
                </label>
                <input
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  placeholder="stakeholder@enterprise.com"
                  required
                  className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                />
              </div>
              <button
                type="submit"
                disabled={isBusy}
                className="min-h-[44px] rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              >
                Send Project Invitation
              </button>
            </form>

            <form
              onSubmit={handleElevateRole}
              className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4"
            >
              <h3 className="text-sm font-semibold text-white">
                Elevate User RBAC Role
              </h3>
              <div>
                <label className="block text-xs text-slate-300">
                  Target User UID
                </label>
                <input
                  type="text"
                  value={targetUid}
                  onChange={(e) => setTargetUid(e.target.value)}
                  placeholder="uid_..."
                  required
                  className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-300">
                  Target Role
                </label>
                <select
                  value={targetRole}
                  onChange={(e) => setTargetRole(e.target.value as UserRole)}
                  className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                >
                  <option value="ADMIN">ADMIN</option>
                  <option value="EXECUTIVE">EXECUTIVE</option>
                  <option value="MANAGER">MANAGER</option>
                  <option value="ADJUDICATOR">ADJUDICATOR</option>
                  <option value="EXTERNAL_STAKEHOLDER">
                    EXTERNAL_STAKEHOLDER
                  </option>
                </select>
              </div>
              <button
                type="submit"
                disabled={isBusy}
                className="min-h-[44px] rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
              >
                Update Role & Sync Claims
              </button>
            </form>
          </div>
        )}
      </main>
    </div>
  );
};
