import React, { useCallback, useEffect, useState } from "react";
import {
  AdminGovernanceDigest,
  adminUpdateUser,
  deleteAdminUser,
  fetchAdminGovernanceSummary,
  fetchAdminUsers,
  provisionAdminUser,
  UserProfile,
  UserRole,
} from "../api/authApi";
import { CountryPhoneInput } from "../components/CountryPhoneInput";
import { toE164Phone } from "../lib/phoneUtils";

interface AdminUsersPageProps {
  idToken: string;
  currentAdminUid: string;
  onBackToWorkspace: () => void;
}

export const AdminUsersPage: React.FC<AdminUsersPageProps> = ({
  idToken,
  currentAdminUid,
  onBackToWorkspace,
}) => {
  const [users, setUsers] = useState<UserProfile[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successBanner, setSuccessBanner] = useState<string | null>(null);

  // AI Governance Digest state
  const [governanceDigest, setGovernanceDigest] =
    useState<AdminGovernanceDigest | null>(null);
  const [isLoadingDigest, setIsLoadingDigest] = useState(false);

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState<string>("ALL");

  // Modals state
  const [isProvisionModalOpen, setIsProvisionModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<UserProfile | null>(null);
  const [deletingUser, setDeletingUser] = useState<UserProfile | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Provision Form state
  const [provEmail, setProvEmail] = useState("");
  const [provFirstName, setProvFirstName] = useState("");
  const [provLastName, setProvLastName] = useState("");
  const [provPhone, setProvPhone] = useState("");
  const [provCountryIso2, setProvCountryIso2] = useState("ID");
  const [provRole, setProvRole] = useState<UserRole>("MANAGER");
  const [provProjects, setProvProjects] = useState("proj-alpha");
  const [provFormError, setProvFormError] = useState<string | null>(null);

  // Edit Role Form state
  const [editRole, setEditRole] = useState<UserRole>("MANAGER");
  const [editProjects, setEditProjects] = useState("");

  const refreshGovernanceDigest = useCallback(
    async (currentUsers: UserProfile[]) => {
      setIsLoadingDigest(true);
      try {
        const digest = await fetchAdminGovernanceSummary(idToken, currentUsers);
        setGovernanceDigest(digest);
      } finally {
        setIsLoadingDigest(false);
      }
    },
    [idToken]
  );

  const loadUsers = useCallback(
    async (search?: string, role?: string) => {
      setIsLoading(true);
      setErrorMessage(null);
      try {
        const queryRole = role && role !== "ALL" ? role : undefined;
        const fetched = await fetchAdminUsers(idToken, search, queryRole);
        setUsers(fetched);
        void refreshGovernanceDigest(fetched);
      } catch (err) {
        setErrorMessage(
          err instanceof Error ? err.message : "Failed to load users"
        );
      } finally {
        setIsLoading(false);
      }
    },
    [idToken, refreshGovernanceDigest]
  );

  useEffect(() => {
    void loadUsers(searchQuery, roleFilter);
  }, [loadUsers, searchQuery, roleFilter]);

  // Handle Escape key to close modals
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setIsProvisionModalOpen(false);
        setEditingUser(null);
        setDeletingUser(null);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const handleOpenProvisionModal = () => {
    setProvEmail("");
    setProvFirstName("");
    setProvLastName("");
    setProvPhone("");
    setProvCountryIso2("ID");
    setProvRole("MANAGER");
    setProvProjects("proj-alpha");
    setProvFormError(null);
    setIsProvisionModalOpen(true);
  };

  const handleProvisionSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setProvFormError(null);

    const validation = toE164Phone(provPhone, provCountryIso2);
    if (!validation.isValid || !validation.e164) {
      setProvFormError(
        validation.error || "Please enter a valid phone number in E.164 format."
      );
      return;
    }

    const assignedList = provProjects
      .split(",")
      .map((p) => p.trim())
      .filter((p) => p.length > 0);

    setIsSubmitting(true);
    try {
      const created = await provisionAdminUser(idToken, {
        email: provEmail.trim(),
        first_name: provFirstName.trim(),
        last_name: provLastName.trim(),
        phone_number: provPhone.trim(),
        country_code: provCountryIso2,
        role: provRole,
        assigned_project_ids: assignedList,
      });

      setSuccessBanner(
        `User ${created.email} provisioned with role ${created.role}.`
      );
      setIsProvisionModalOpen(false);
      await loadUsers(searchQuery, roleFilter);
    } catch (err) {
      setProvFormError(
        err instanceof Error ? err.message : "Failed to provision user"
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleOpenEditModal = (user: UserProfile) => {
    setEditingUser(user);
    setEditRole(user.role);
    setEditProjects(user.assigned_project_ids.join(", "));
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingUser) return;

    const assignedList = editProjects
      .split(",")
      .map((p) => p.trim())
      .filter((p) => p.length > 0);

    setIsSubmitting(true);
    try {
      const updated = await adminUpdateUser(
        idToken,
        editingUser.uid,
        editRole,
        assignedList
      );
      setSuccessBanner(
        `Updated role for ${updated.email} to ${updated.role}.`
      );
      setEditingUser(null);
      await loadUsers(searchQuery, roleFilter);
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to update user"
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleConfirmDelete = async () => {
    if (!deletingUser) return;
    setIsSubmitting(true);
    try {
      await deleteAdminUser(idToken, deletingUser.uid);
      setSuccessBanner(
        `Account for ${deletingUser.email} has been de-provisioned.`
      );
      setDeletingUser(null);
      await loadUsers(searchQuery, roleFilter);
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to delete user"
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* Top Header */}
      <header className="border-b border-slate-800 bg-slate-900/90 px-6 py-4">
        <div className="mx-auto flex max-w-6xl items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded bg-rose-500/20 px-2 py-0.5 text-xs font-semibold text-rose-300">
                SUPER ADMIN
              </span>
              <h1 className="text-lg font-bold text-white">
                User Governance Console
              </h1>
            </div>
            <p className="text-xs text-slate-300">
              Manage accounts, project assignments, and RBAC security boundaries
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onBackToWorkspace}
              className="inline-flex min-h-[44px] items-center justify-center rounded-lg border border-slate-700 bg-slate-800/80 px-4 py-2 text-xs font-medium text-slate-200 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
            >
              Workspace View
            </button>
            <button
              type="button"
              onClick={handleOpenProvisionModal}
              className="inline-flex min-h-[44px] items-center justify-center rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
            >
              Provision Account
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-6 px-6 py-8">
        {/* Success / Error Banners */}
        {successBanner && (
          <div
            role="status"
            className="flex items-center justify-between rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-4 py-3 text-xs text-emerald-200"
          >
            <span>{successBanner}</span>
            <button
              type="button"
              onClick={() => setSuccessBanner(null)}
              className="min-h-[44px] px-2 text-emerald-300 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
            >
              Dismiss
            </button>
          </div>
        )}

        {errorMessage && (
          <div
            role="alert"
            className="flex items-center justify-between rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-xs text-rose-200"
          >
            <span>{errorMessage}</span>
            <button
              type="button"
              onClick={() => setErrorMessage(null)}
              className="min-h-[44px] px-2 text-rose-300 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* AI Governance Digest Panel */}
        <section
          aria-label="AI Governance Digest"
          className="rounded-xl border border-indigo-500/30 bg-slate-900 p-5 space-y-4"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded bg-indigo-500/20 px-2.5 py-0.5 font-mono text-[11px] font-semibold text-indigo-300">
                  AI GOVERNANCE DIGEST
                </span>
                {governanceDigest && (
                  <span className="rounded bg-slate-800 px-2.5 py-0.5 font-mono text-[11px] text-emerald-300">
                    {governanceDigest.inference_mode}
                  </span>
                )}
              </div>
              <h2 className="mt-1 text-sm font-bold text-white">
                Identity, Quarantine & Workspace Access Posture
              </h2>
            </div>
            <button
              type="button"
              onClick={() => void refreshGovernanceDigest(users)}
              disabled={isLoadingDigest}
              className="min-h-[44px] rounded-lg border border-indigo-500/40 bg-indigo-950/60 px-3.5 py-2 text-xs font-semibold text-indigo-200 hover:bg-indigo-900/60 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
            >
              {isLoadingDigest ? "Synthesizing..." : "Refresh AI Digest"}
            </button>
          </div>

          {governanceDigest ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <div className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                  <span className="block text-[11px] text-slate-300">
                    Active Accounts
                  </span>
                  <span className="mt-1 block font-mono text-base font-bold text-emerald-300">
                    {governanceDigest.active_users_count} /{" "}
                    {governanceDigest.total_users}
                  </span>
                </div>
                <div className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                  <span className="block text-[11px] text-slate-300">
                    Quarantined Stakeholders
                  </span>
                  <span className="mt-1 block font-mono text-base font-bold text-amber-300">
                    {governanceDigest.quarantined_users_count}
                  </span>
                </div>
                <div className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                  <span className="block text-[11px] text-slate-300">
                    Project Workspaces
                  </span>
                  <span className="mt-1 block font-mono text-base font-bold text-indigo-300">
                    {governanceDigest.total_projects}
                  </span>
                </div>
                <div className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                  <span className="block text-[11px] text-slate-300">
                    Pending Invitations
                  </span>
                  <span className="mt-1 block font-mono text-base font-bold text-slate-100">
                    {governanceDigest.pending_invitations_count}
                  </span>
                </div>
              </div>

              <p className="rounded-lg border border-slate-800 bg-slate-950/80 p-3.5 text-xs leading-relaxed text-slate-200">
                {governanceDigest.executive_summary}
              </p>

              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3.5">
                  <h3 className="text-xs font-semibold text-indigo-300">
                    Key Governance Findings
                  </h3>
                  <ul className="mt-2 space-y-1.5 text-xs text-slate-200">
                    {governanceDigest.key_findings.map((finding, idx) => (
                      <li key={idx} className="flex items-start gap-2">
                        <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-400" />
                        <span>{finding}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3.5">
                  <h3 className="text-xs font-semibold text-emerald-300">
                    Recommended Admin Actions
                  </h3>
                  <ul className="mt-2 space-y-1.5 text-xs text-slate-200">
                    {governanceDigest.recommended_actions.map((action, idx) => (
                      <li key={idx} className="flex items-start gap-2">
                        <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
                        <span>{action}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          ) : (
            <div className="h-20 animate-pulse rounded-lg bg-slate-800/60" />
          )}
        </section>

        {/* Search & Filters */}
        <section className="flex flex-col gap-4 rounded-xl border border-slate-800 bg-slate-900 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex-1">
            <label htmlFor="user-search-input" className="sr-only">
              Search Users
            </label>
            <input
              id="user-search-input"
              type="text"
              placeholder="Filter by name, email, or phone..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-xs text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
            />
          </div>
          <div className="flex items-center gap-2">
            <label
              htmlFor="role-filter-select"
              className="text-xs text-slate-300"
            >
              Role:
            </label>
            <select
              id="role-filter-select"
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus:border-indigo-500 focus:outline-none"
            >
              <option value="ALL">All Roles</option>
              <option value="ADMIN">ADMIN</option>
              <option value="EXECUTIVE">EXECUTIVE</option>
              <option value="MANAGER">MANAGER</option>
              <option value="ADJUDICATOR">ADJUDICATOR</option>
              <option value="EXTERNAL_STAKEHOLDER">EXTERNAL_STAKEHOLDER</option>
            </select>
          </div>
        </section>

        {/* Directory Table */}
        <section className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900">
          {isLoading ? (
            <div className="flex items-center justify-center p-12 text-slate-400 text-xs">
              Loading user directory...
            </div>
          ) : users.length === 0 ? (
            <div className="p-12 text-center text-xs text-slate-400">
              No registered user accounts match the current filters.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-slate-800 bg-slate-950/60 font-semibold text-slate-400">
                  <tr>
                    <th scope="col" className="px-4 py-3">
                      User
                    </th>
                    <th scope="col" className="px-4 py-3">
                      E.164 Phone
                    </th>
                    <th scope="col" className="px-4 py-3">
                      Role
                    </th>
                    <th scope="col" className="px-4 py-3">
                      Onboarding
                    </th>
                    <th scope="col" className="px-4 py-3">
                      Projects
                    </th>
                    <th scope="col" className="px-4 py-3 text-right">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {users.map((u) => {
                    const isSelf = u.uid === currentAdminUid;
                    return (
                      <tr key={u.uid} className="hover:bg-slate-800/40">
                        <td className="px-4 py-3">
                          <div className="font-medium text-white">
                            {u.first_name} {u.last_name}
                            {isSelf && (
                              <span className="ml-2 rounded bg-indigo-500/20 px-1.5 py-0.5 text-[10px] text-indigo-300">
                                You
                              </span>
                            )}
                          </div>
                          <div className="text-slate-400">{u.email}</div>
                          <div className="font-mono text-[10px] text-slate-500">
                            {u.uid}
                          </div>
                        </td>
                        <td className="px-4 py-3 font-mono text-slate-300">
                          {u.phone_number}
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`rounded-full px-2.5 py-1 font-mono text-[11px] font-semibold ${
                              u.role === "ADMIN"
                                ? "bg-rose-500/20 text-rose-300"
                                : u.role === "EXECUTIVE"
                                  ? "bg-purple-500/20 text-purple-300"
                                  : u.role === "MANAGER"
                                    ? "bg-indigo-500/20 text-indigo-300"
                                    : u.role === "ADJUDICATOR"
                                      ? "bg-emerald-500/20 text-emerald-300"
                                      : "bg-amber-500/20 text-amber-300"
                            }`}
                          >
                            {u.role}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`text-[11px] ${
                              u.onboarding_status === "ACTIVE"
                                ? "text-emerald-400"
                                : "text-amber-400"
                            }`}
                          >
                            {u.onboarding_status === "ACTIVE"
                              ? "Active"
                              : "Quarantined"}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          {u.assigned_project_ids.length === 0 ? (
                            <span className="text-slate-500">None</span>
                          ) : (
                            <div className="flex flex-wrap gap-1">
                              {u.assigned_project_ids.map((pid) => (
                                <span
                                  key={pid}
                                  className="rounded border border-slate-700 bg-slate-950 px-1.5 py-0.5 font-mono text-[10px] text-slate-300"
                                >
                                  {pid}
                                </span>
                              ))}
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <button
                              type="button"
                              onClick={() => handleOpenEditModal(u)}
                              className="rounded border border-slate-700 bg-slate-800 px-2.5 py-1 text-[11px] text-slate-200 hover:bg-slate-700"
                            >
                              Edit Role
                            </button>
                            <button
                              type="button"
                              disabled={isSelf}
                              onClick={() => setDeletingUser(u)}
                              className={`rounded border px-2.5 py-1 text-[11px] ${
                                isSelf
                                  ? "cursor-not-allowed border-slate-800 text-slate-600"
                                  : "border-rose-900/60 bg-rose-950/40 text-rose-300 hover:bg-rose-900/50"
                              }`}
                            >
                              De-provision
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
      </main>

      {/* Provision Account Modal */}
      {isProvisionModalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="provision-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
        >
          <div className="w-full max-w-lg rounded-xl border border-slate-700 bg-slate-900 p-6 shadow-2xl">
            <h2
              id="provision-modal-title"
              className="text-base font-bold text-white"
            >
              Provision New Enterprise Account
            </h2>
            <p className="mt-1 text-xs text-slate-400">
              Create an authenticated profile with assigned role and pre-bound
              project workspaces.
            </p>

            {provFormError && (
              <div
                role="alert"
                className="mt-3 rounded border border-rose-500/40 bg-rose-500/10 p-2.5 text-xs text-rose-300"
              >
                {provFormError}
              </div>
            )}

            <form onSubmit={handleProvisionSubmit} className="mt-4 space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label
                    htmlFor="prov-first-name"
                    className="block text-xs text-slate-300"
                  >
                    First Name <span className="text-rose-400">*</span>
                  </label>
                  <input
                    id="prov-first-name"
                    type="text"
                    required
                    value={provFirstName}
                    onChange={(e) => setProvFirstName(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus:border-indigo-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label
                    htmlFor="prov-last-name"
                    className="block text-xs text-slate-300"
                  >
                    Last Name <span className="text-rose-400">*</span>
                  </label>
                  <input
                    id="prov-last-name"
                    type="text"
                    required
                    value={provLastName}
                    onChange={(e) => setProvLastName(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus:border-indigo-500 focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label
                  htmlFor="prov-email"
                  className="block text-xs text-slate-300"
                >
                  Email Address <span className="text-rose-400">*</span>
                </label>
                <input
                  id="prov-email"
                  type="email"
                  required
                  value={provEmail}
                  onChange={(e) => setProvEmail(e.target.value)}
                  placeholder="analyst@enterprise.com"
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus:border-indigo-500 focus:outline-none"
                />
              </div>

              <CountryPhoneInput
                countryIso2={provCountryIso2}
                phoneNumber={provPhone}
                onCountryChange={setProvCountryIso2}
                onPhoneChange={setProvPhone}
                disabled={isSubmitting}
              />

              <div className="grid grid-cols-2 gap-3 pt-1">
                <div>
                  <label
                    htmlFor="prov-role"
                    className="block text-xs text-slate-300"
                  >
                    Assigned Role
                  </label>
                  <select
                    id="prov-role"
                    value={provRole}
                    onChange={(e) => setProvRole(e.target.value as UserRole)}
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus:border-indigo-500 focus:outline-none"
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
                <div>
                  <label
                    htmlFor="prov-projects"
                    className="block text-xs text-slate-300"
                  >
                    Project IDs (comma-separated)
                  </label>
                  <input
                    id="prov-projects"
                    type="text"
                    value={provProjects}
                    onChange={(e) => setProvProjects(e.target.value)}
                    placeholder="proj-alpha, proj-beta"
                    className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus:border-indigo-500 focus:outline-none"
                  />
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => setIsProvisionModalOpen(false)}
                  className="min-h-[44px] rounded-lg border border-slate-700 px-4 py-2 text-xs text-slate-300 hover:bg-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="min-h-[44px] rounded-lg bg-indigo-600 px-5 py-2 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
                >
                  {isSubmitting ? "Provisioning..." : "Confirm & Provision"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Role Modal */}
      {editingUser && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="edit-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
        >
          <div className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-900 p-6 shadow-2xl">
            <h2 id="edit-modal-title" className="text-base font-bold text-white">
              Adjust Role & Access Boundaries
            </h2>
            <p className="mt-1 text-xs text-slate-400">
              Update credentials and synchronization claims for{" "}
              <span className="font-semibold text-slate-200">
                {editingUser.email}
              </span>
            </p>

            <form onSubmit={handleEditSubmit} className="mt-4 space-y-4">
              <div>
                <label
                  htmlFor="edit-role-select"
                  className="block text-xs text-slate-300"
                >
                  Target Role
                </label>
                <select
                  id="edit-role-select"
                  value={editRole}
                  onChange={(e) => setEditRole(e.target.value as UserRole)}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus:border-indigo-500 focus:outline-none"
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

              <div>
                <label
                  htmlFor="edit-projects-input"
                  className="block text-xs text-slate-300"
                >
                  Assigned Project IDs (comma-separated)
                </label>
                <input
                  id="edit-projects-input"
                  type="text"
                  value={editProjects}
                  onChange={(e) => setEditProjects(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus:border-indigo-500 focus:outline-none"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-3">
                <button
                  type="button"
                  onClick={() => setEditingUser(null)}
                  className="min-h-[44px] rounded-lg border border-slate-700 px-4 py-2 text-xs text-slate-300 hover:bg-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="min-h-[44px] rounded-lg bg-indigo-600 px-5 py-2 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
                >
                  {isSubmitting ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deletingUser && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
        >
          <div className="w-full max-w-md rounded-xl border border-rose-900/60 bg-slate-900 p-6 shadow-2xl">
            <h2
              id="delete-modal-title"
              className="text-base font-bold text-rose-300"
            >
              Confirm Account De-provisioning
            </h2>
            <p className="mt-2 text-xs text-slate-300">
              Are you sure you want to permanently delete the account for{" "}
              <strong className="text-white">{deletingUser.email}</strong>?
            </p>
            <p className="mt-1 text-xs text-slate-400">
              This action will purge the user profile from Cloud Firestore,
              delete authentication credentials from Firebase Identity Platform,
              and record a permanent tombstone in the immutable audit ledger.
            </p>

            <div className="mt-6 flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => setDeletingUser(null)}
                className="min-h-[44px] rounded-lg border border-slate-700 px-4 py-2 text-xs text-slate-300 hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isSubmitting}
                onClick={handleConfirmDelete}
                className="min-h-[44px] rounded-lg bg-rose-600 px-5 py-2 text-xs font-semibold text-white hover:bg-rose-500 disabled:opacity-50"
              >
                {isSubmitting ? "De-provisioning..." : "Confirm Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
