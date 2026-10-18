import React from "react";
import { ProjectInvitation, UserProfile } from "../api/authApi";

export interface QuarantinedOnboardingViewProps {
  profile: UserProfile;
  pendingInvitations: ProjectInvitation[];
  onAcceptInvitation: (projectId: string, invitationId: string) => Promise<void>;
  onClaimExecutive?: () => Promise<void>;
  onSignOut: () => void;
  isBusy?: boolean;
}

export const QuarantinedOnboardingView: React.FC<
  QuarantinedOnboardingViewProps
> = ({
  profile,
  pendingInvitations,
  onAcceptInvitation,
  onClaimExecutive,
  onSignOut,
  isBusy = false,
}) => {
  return (
    <div className="mx-auto max-w-2xl px-4 py-12">
      <div className="rounded-2xl border border-amber-500/40 bg-slate-900/90 p-8 shadow-2xl">
        <div className="mb-6 flex items-center justify-between">
          <span className="inline-flex items-center gap-2 rounded-full border border-amber-400/40 bg-amber-500/10 px-3.5 py-1 text-xs font-semibold uppercase tracking-wide text-amber-300">
            Access Pending Project Invitation
          </span>
          <button
            type="button"
            onClick={onSignOut}
            className="text-xs font-medium text-slate-400 hover:text-slate-200"
          >
            Sign Out
          </button>
        </div>

        <h1 className="text-2xl font-bold text-slate-100">
          Access Pending Project Invitation
        </h1>
        <p className="mt-2 text-sm text-slate-300">
          Welcome,{" "}
          <span className="font-semibold text-white">
            {profile.first_name} {profile.last_name}
          </span>
          . Under pRiskAI Principle of Least Privilege governance, newly
          registered accounts are provisioned with the{" "}
          <code className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-xs text-amber-300">
            {profile.role}
          </code>{" "}
          role and zero project bindings until invited by a Project Manager or
          elevated by an Executive.
        </p>

        <div className="mt-6 grid grid-cols-1 gap-3 rounded-xl border border-slate-800 bg-slate-950/70 p-4 text-xs sm:grid-cols-2">
          <div>
            <span className="text-slate-400">Registered Email:</span>
            <p className="mt-0.5 font-mono text-slate-200">{profile.email}</p>
          </div>
          <div>
            <span className="text-slate-400">Verified E.164 Phone:</span>
            <p className="mt-0.5 font-mono text-indigo-300">
              {profile.phone_number}
            </p>
          </div>
          <div>
            <span className="text-slate-400">Identity Provider:</span>
            <p className="mt-0.5 font-mono text-slate-200">
              {profile.auth_provider}
            </p>
          </div>
          <div>
            <span className="text-slate-400">Manager Notification:</span>
            <p className="mt-0.5 text-emerald-400">
              Dispatched to Enterprise Managers
            </p>
          </div>
        </div>

        <div className="mt-8">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
            Pending Project Invitations ({pendingInvitations.length})
          </h2>

          {pendingInvitations.length === 0 ? (
            <div className="mt-3 rounded-xl border border-dashed border-slate-800 p-6 text-center text-sm text-slate-400">
              <p>
                No pending project invitations found for{" "}
                <span className="font-mono text-slate-300">{profile.email}</span>.
                Once a Manager invites you to a project, it will appear here.
              </p>
              {onClaimExecutive && (
                <div className="mt-5 border-t border-slate-800/80 pt-4">
                  <p className="text-xs text-slate-400 mb-2">
                    Are you setting up this organization for the first time?
                  </p>
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={onClaimExecutive}
                    className="inline-flex items-center rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
                  >
                    Claim Initial Executive Account (Bootstrap)
                  </button>
                </div>
              )}
            </div>
          ) : (
            <ul className="mt-3 space-y-3">
              {pendingInvitations.map((inv) => (
                <li
                  key={inv.invitation_id}
                  className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950 p-4"
                >
                  <div>
                    <p className="font-semibold text-slate-100">
                      {inv.project_name}
                    </p>
                    <p className="text-xs text-slate-400">
                      Project ID:{" "}
                      <code className="font-mono text-slate-300">
                        {inv.project_id}
                      </code>{" "}
                      • Invited by {inv.invited_by_uid}
                    </p>
                  </div>
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={() =>
                      onAcceptInvitation(inv.project_id, inv.invitation_id)
                    }
                    className="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
                  >
                    Accept Invitation
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
};
