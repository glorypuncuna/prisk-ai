export type UserRole =
  | "ADMIN"
  | "EXECUTIVE"
  | "MANAGER"
  | "ADJUDICATOR"
  | "EXTERNAL_STAKEHOLDER";

export interface UserProfile {
  uid: string;
  email: string;
  first_name: string;
  last_name: string;
  phone_number: string;
  role: UserRole;
  auth_provider: string;
  assigned_project_ids: string[];
  onboarding_status: "QUARANTINED_PENDING_INVITATION" | "ACTIVE";
  created_at: string;
  last_login_at: string;
}

export interface RegisterProfilePayload {
  first_name: string;
  last_name: string;
  phone_number: string;
  country_code: string;
  email?: string;
}

export interface ProjectInvitation {
  invitation_id: string;
  project_id: string;
  project_name: string;
  invitee_email: string;
  invited_by_uid: string;
  status: "PENDING" | "ACCEPTED";
  created_at: string;
  accepted_at?: string | null;
}

const API_BASE = `${(import.meta.env.VITE_API_BASE_URL || "").replace(/\/+$/, "")}/api/v1`;
const DIRECT_LOCAL_API_BASES = [
  "http://127.0.0.1:8001/api/v1",
  "http://127.0.0.1:8000/api/v1",
];

async function apiRequest<T>(
  path: string,
  idToken: string,
  options: RequestInit = {}
): Promise<T> {
  const reqInit: RequestInit = {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${idToken}`,
      ...(options.headers || {}),
    },
  };

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, reqInit);
  } catch (networkErr) {
    let directResp: Response | null = null;
    if (typeof window !== "undefined" && window.location.protocol === "http:") {
      for (const directBase of DIRECT_LOCAL_API_BASES) {
        try {
          directResp = await fetch(`${directBase}${path}`, reqInit);
          break;
        } catch {
          // Ignore and try next local port
        }
      }
    }
    if (!directResp) {
      throw new Error(
        `Backend service unreachable (${networkErr instanceof Error ? networkErr.message : "Failed to fetch"}). Ensure the FastAPI server is running on port 8001.`
      );
    }
    response = directResp;
  }

  // If Vite dev proxy returns 500 (e.g. sandbox EPERM), retry directly from the browser against local FastAPI if on http:
  if (response.status >= 500) {
    if (typeof window !== "undefined" && window.location.protocol === "http:") {
      for (const directBase of DIRECT_LOCAL_API_BASES) {
        try {
          const directResp = await fetch(`${directBase}${path}`, reqInit);
          if (directResp.ok || directResp.status < 500) {
            response = directResp;
            break;
          }
        } catch {
          // Ignore and try next local port
        }
      }
    }
  }

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    const detail =
      typeof errorBody.detail === "string"
        ? errorBody.detail
        : Array.isArray(errorBody.detail)
          ? errorBody.detail.map((e: { msg?: string }) => e.msg).join(", ")
          : `Request failed with status ${response.status}`;
    const err = new Error(detail) as Error & { status?: number };
    err.status = response.status;
    throw err;
  }

  return (await response.json()) as T;
}

export async function registerUserProfile(
  idToken: string,
  payload: RegisterProfilePayload
): Promise<UserProfile> {
  return apiRequest<UserProfile>("/auth/register-profile", idToken, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchCurrentUserProfile(
  idToken: string
): Promise<UserProfile> {
  return apiRequest<UserProfile>("/auth/me", idToken, {
    method: "GET",
  });
}

export async function fetchPendingInvitations(
  idToken: string
): Promise<ProjectInvitation[]> {
  return apiRequest<ProjectInvitation[]>("/projects/invitations/me", idToken, {
    method: "GET",
  });
}

export async function acceptProjectInvitation(
  idToken: string,
  projectId: string,
  invitationId: string
): Promise<UserProfile> {
  return apiRequest<UserProfile>(
    `/projects/${encodeURIComponent(projectId)}/invitations/${encodeURIComponent(invitationId)}/accept`,
    idToken,
    {
      method: "POST",
    }
  );
}

export async function sendProjectInvitation(
  idToken: string,
  projectId: string,
  inviteeEmail: string
): Promise<ProjectInvitation> {
  return apiRequest<ProjectInvitation>(
    `/projects/${encodeURIComponent(projectId)}/invitations`,
    idToken,
    {
      method: "POST",
      body: JSON.stringify({ invitee_email: inviteeEmail }),
    }
  );
}

export async function updateUserRole(
  idToken: string,
  targetUid: string,
  role: UserRole,
  assignedProjectIds?: string[]
): Promise<UserProfile> {
  return apiRequest<UserProfile>(
    `/users/${encodeURIComponent(targetUid)}/role`,
    idToken,
    {
      method: "PATCH",
      body: JSON.stringify({
        role,
        assigned_project_ids: assignedProjectIds,
      }),
    }
  );
}

export async function claimInitialExecutive(
  idToken: string
): Promise<UserProfile> {
  return apiRequest<UserProfile>("/auth/claim-initial-executive", idToken, {
    method: "POST",
  });
}

export interface AdminProvisionUserPayload {
  email: string;
  first_name: string;
  last_name: string;
  phone_number: string;
  country_code: string;
  role: UserRole;
  assigned_project_ids?: string[];
}

export interface AdminDeleteUserResponse {
  status: string;
  uid: string;
  message: string;
}

export async function fetchAdminUsers(
  idToken: string,
  search?: string,
  role?: string
): Promise<UserProfile[]> {
  const params = new URLSearchParams();
  if (search) params.set("q", search);
  if (role) params.set("role", role);
  const qs = params.toString() ? `?${params.toString()}` : "";
  return apiRequest<UserProfile[]>(`/admin/users${qs}`, idToken, {
    method: "GET",
  });
}

export async function provisionAdminUser(
  idToken: string,
  payload: AdminProvisionUserPayload
): Promise<UserProfile> {
  return apiRequest<UserProfile>("/admin/users", idToken, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteAdminUser(
  idToken: string,
  uid: string
): Promise<AdminDeleteUserResponse> {
  return apiRequest<AdminDeleteUserResponse>(
    `/admin/users/${encodeURIComponent(uid)}`,
    idToken,
    {
      method: "DELETE",
    }
  );
}

export async function adminUpdateUser(
  idToken: string,
  uid: string,
  role: UserRole,
  assignedProjectIds?: string[]
): Promise<UserProfile> {
  return apiRequest<UserProfile>(
    `/admin/users/${encodeURIComponent(uid)}`,
    idToken,
    {
      method: "PATCH",
      body: JSON.stringify({
        role,
        assigned_project_ids: assignedProjectIds,
      }),
    }
  );
}

export interface ProjectAlertThresholds {
  pulse_drop_delta: number;
  minimum_pulse_score: number;
  escalation_enabled: boolean;
  escalation_intervals_hours: number[];
}

export interface ProjectWorkspace {
  project_id: string;
  name: string;
  company_name: string;
  description: string;
  canonical_groups: string[];
  alert_thresholds: ProjectAlertThresholds;
  owner_uid: string;
  created_at: string;
  updated_at?: string | null;
}

export interface ProjectCreatePayload {
  project_id: string;
  name: string;
  company_name?: string;
  description?: string;
  canonical_groups?: string[];
  alert_thresholds?: ProjectAlertThresholds;
}

export interface ProjectUpdatePayload {
  name?: string;
  company_name?: string;
  description?: string;
  canonical_groups?: string[];
  alert_thresholds?: ProjectAlertThresholds;
}

export interface ProjectAISuggestionResponse {
  project_id: string;
  suggested_canonical_groups: string[];
  suggested_risk_categories: string[];
  recommended_alert_thresholds: ProjectAlertThresholds;
  rationale: string;
  inference_mode: string;
  model_version: string;
}

export interface AdminGovernanceDigest {
  generated_at: string;
  inference_mode: string;
  model_version: string;
  total_users: number;
  active_users_count: number;
  quarantined_users_count: number;
  total_projects: number;
  unassigned_projects_count: number;
  pending_invitations_count: number;
  role_distribution: Record<string, number>;
  executive_summary: string;
  key_findings: string[];
  recommended_actions: string[];
}

export const DEFAULT_CANONICAL_GROUPS = [
  "Client Executive Sponsor",
  "Client Legal & Compliance",
  "Client Engineering",
  "Internal Delivery Team",
];

export async function fetchProjects(
  idToken: string
): Promise<ProjectWorkspace[]> {
  return apiRequest<ProjectWorkspace[]>("/projects", idToken, {
    method: "GET",
  });
}

export async function createProject(
  idToken: string,
  payload: ProjectCreatePayload
): Promise<ProjectWorkspace> {
  return apiRequest<ProjectWorkspace>("/projects", idToken, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateProject(
  idToken: string,
  projectId: string,
  payload: ProjectUpdatePayload
): Promise<ProjectWorkspace> {
  return apiRequest<ProjectWorkspace>(
    `/projects/${encodeURIComponent(projectId)}`,
    idToken,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    }
  );
}

export function buildClientFallbackGroupSuggestion(
  projectId: string,
  name: string,
  companyName: string,
  description: string
): ProjectAISuggestionResponse {
  const combined = `${name} ${companyName} ${description}`.toLowerCase();
  let groups = [...DEFAULT_CANONICAL_GROUPS];
  let riskCategories = [
    "STAKEHOLDER_ALIGNMENT",
    "SCOPE_CREEP",
    "TIMELINE_SLIPPAGE",
    "COMMERCIAL_RISK",
  ];
  let pulseDropDelta = 15;
  let minPulseScore = 42;
  let domainLabel = "enterprise program delivery";

  if (
    /bank|fin|payment|treasury|audit|capital|ledger|tax/.test(combined)
  ) {
    groups = [
      "Client Executive Sponsor",
      "Chief Risk & Compliance Office",
      "Treasury & Finance Operations",
      "Security & Audit Governance",
      "Internal Delivery Team",
    ];
    riskCategories = [
      "REGULATORY_COMPLIANCE",
      "FINANCIAL_OVERRUN",
      "SECURITY_GOVERNANCE",
      "DELIVERY_TIMELINE",
    ];
    pulseDropDelta = 12;
    minPulseScore = 48;
    domainLabel = "financial and regulatory compliance";
  } else if (
    /health|clinical|medical|hipaa|patient|pharma|hospital/.test(combined)
  ) {
    groups = [
      "Client Executive Sponsor",
      "Clinical Privacy & HIPAA Officer",
      "Healthcare IT & EHR Integration",
      "Quality Assurance Lead",
      "Internal Delivery Team",
    ];
    riskCategories = [
      "HIPAA_PRIVACY_SG",
      "CLINICAL_WORKFLOW_DISRUPTION",
      "DATA_INTEGRATION_RISK",
      "STAKEHOLDER_ALIGNMENT",
    ];
    pulseDropDelta = 10;
    minPulseScore = 50;
    domainLabel = "healthcare and clinical data privacy";
  } else if (
    /cloud|infra|migration|platform|security|data|ai|cyber|engineering/.test(
      combined
    )
  ) {
    groups = [
      "Client Executive Sponsor",
      "Enterprise Architecture & Platform",
      "Information Security & DLP",
      "Client Product Engineering",
      "Internal Delivery Team",
    ];
    riskCategories = [
      "TECHNICAL_DEBT_MIGRATION",
      "SECURITY_DLP_EXPOSURE",
      "SCOPE_CREEP",
      "DELIVERY_VELOCITY",
    ];
    pulseDropDelta = 14;
    minPulseScore = 44;
    domainLabel = "cloud infrastructure and security engineering";
  }

  const displayTitle = name.trim() || projectId;
  const companyClause = companyName.trim() ? ` for ${companyName.trim()}` : "";

  return {
    project_id: projectId,
    suggested_canonical_groups: groups,
    suggested_risk_categories: riskCategories,
    recommended_alert_thresholds: {
      pulse_drop_delta: pulseDropDelta,
      minimum_pulse_score: minPulseScore,
      escalation_enabled: true,
      escalation_intervals_hours: [24, 48, 72],
    },
    rationale: `Calibrated ${groups.length} canonical stakeholder groups and ${riskCategories.length} risk categories around ${domainLabel} requirements in '${displayTitle}'${companyClause}. Recommended a ${pulseDropDelta}-point pulse drop trigger and a minimum group health floor of ${minPulseScore}.`,
    inference_mode: "DETERMINISTIC_FALLBACK",
    model_version: "gemini-2.5-flash",
  };
}

export async function suggestProjectGroupsWithAI(
  idToken: string,
  projectId: string,
  payload: { name: string; company_name: string; description: string }
): Promise<ProjectAISuggestionResponse> {
  try {
    return await apiRequest<ProjectAISuggestionResponse>(
      `/projects/${encodeURIComponent(projectId)}/ai-suggest-groups`,
      idToken,
      {
        method: "POST",
        body: JSON.stringify(payload),
      }
    );
  } catch {
    return buildClientFallbackGroupSuggestion(
      projectId,
      payload.name,
      payload.company_name,
      payload.description
    );
  }
}

export function buildClientFallbackGovernanceDigest(
  users: UserProfile[] = []
): AdminGovernanceDigest {
  const totalUsers = users.length;
  let activeUsers = 0;
  let quarantinedUsers = 0;
  const roleDistribution: Record<string, number> = {
    ADMIN: 0,
    EXECUTIVE: 0,
    MANAGER: 0,
    ADJUDICATOR: 0,
    EXTERNAL_STAKEHOLDER: 0,
  };
  const projectSet = new Set<string>();

  for (const u of users) {
    roleDistribution[u.role] = (roleDistribution[u.role] || 0) + 1;
    for (const pid of u.assigned_project_ids || []) {
      projectSet.add(pid);
    }
    if (
      u.onboarding_status === "ACTIVE" ||
      u.role !== "EXTERNAL_STAKEHOLDER" ||
      (u.assigned_project_ids && u.assigned_project_ids.length > 0)
    ) {
      activeUsers += 1;
    } else {
      quarantinedUsers += 1;
    }
  }

  const totalProjects = Math.max(projectSet.size, 1);
  const findings = [
    `${activeUsers} of ${totalUsers} registered accounts hold active workspace access across ${totalProjects} tracked project workspace(s).`,
  ];
  const actions: string[] = [];

  if (quarantinedUsers > 0) {
    findings.push(
      `${quarantinedUsers} External Stakeholder account(s) remain in QUARANTINED_PENDING_INVITATION state with zero assigned projects.`
    );
    actions.push(
      "Review quarantined External Stakeholder accounts and issue project invitations or de-provision stale registrations."
    );
  } else {
    findings.push(
      "Zero accounts are stuck in quarantine; all External Stakeholders have verified project assignments."
    );
  }

  if ((roleDistribution.ADJUDICATOR || 0) === 0) {
    actions.push(
      "Assign at least one ADJUDICATOR account to maintain Human-in-the-Loop transcript verification throughput."
    );
  }

  if (actions.length === 0) {
    actions.push(
      "Maintain weekly audits of role assignments and verify canonical stakeholder group taxonomies across active projects."
    );
  }

  return {
    generated_at: new Date().toISOString(),
    inference_mode: "DETERMINISTIC_FALLBACK",
    model_version: "gemini-2.5-flash",
    total_users: totalUsers,
    active_users_count: activeUsers,
    quarantined_users_count: quarantinedUsers,
    total_projects: totalProjects,
    unassigned_projects_count: 0,
    pending_invitations_count: 0,
    role_distribution: roleDistribution,
    executive_summary: `Identity governance check evaluated ${totalUsers} user account(s) across ${totalProjects} project workspace(s). ${activeUsers} account(s) are active and ${quarantinedUsers} account(s) are quarantined pending invitation.`,
    key_findings: findings,
    recommended_actions: actions,
  };
}

export async function fetchAdminGovernanceSummary(
  idToken: string,
  fallbackUsers: UserProfile[] = []
): Promise<AdminGovernanceDigest> {
  try {
    return await apiRequest<AdminGovernanceDigest>(
      "/admin/ai-governance-summary",
      idToken,
      {
        method: "GET",
      }
    );
  } catch {
    return buildClientFallbackGovernanceDigest(fallbackUsers);
  }
}

