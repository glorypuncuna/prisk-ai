import { describe, expect, it, vi } from "vitest";
import {
  adminUpdateUser,
  deleteAdminUser,
  fetchAdminGovernanceSummary,
  fetchAdminUsers,
  provisionAdminUser,
  suggestProjectGroupsWithAI,
} from "./authApi";

describe("Admin API Client", () => {
  it("formats fetchAdminUsers query parameters correctly", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{ uid: "uid_1", email: "admin@enterprise.com", role: "ADMIN" }],
    });
    vi.stubGlobal("fetch", mockFetch);

    const users = await fetchAdminUsers("test-token", "siti", "MANAGER");
    expect(users).toHaveLength(1);
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/admin/users?q=siti&role=MANAGER",
      expect.objectContaining({
        method: "GET",
        headers: expect.objectContaining({
          Authorization: "Bearer test-token",
        }),
      })
    );
  });

  it("submits provisionAdminUser with JSON body", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        uid: "uid_new",
        email: "user@enterprise.com",
        role: "EXECUTIVE",
      }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const result = await provisionAdminUser("test-token", {
      email: "user@enterprise.com",
      first_name: "John",
      last_name: "Doe",
      phone_number: "+628123456789",
      country_code: "ID",
      role: "EXECUTIVE",
      assigned_project_ids: ["proj-alpha"],
    });

    expect(result.uid).toBe("uid_new");
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/admin/users",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          email: "user@enterprise.com",
          first_name: "John",
          last_name: "Doe",
          phone_number: "+628123456789",
          country_code: "ID",
          role: "EXECUTIVE",
          assigned_project_ids: ["proj-alpha"],
        }),
      })
    );
  });

  it("submits deleteAdminUser to specific endpoint", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: "deleted", uid: "uid_target", message: "Deleted" }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const result = await deleteAdminUser("test-token", "uid_target");
    expect(result.status).toBe("deleted");
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/admin/users/uid_target",
      expect.objectContaining({
        method: "DELETE",
      })
    );
  });

  it("submits adminUpdateUser PATCH request", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ uid: "uid_target", role: "ADMIN" }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const result = await adminUpdateUser("test-token", "uid_target", "ADMIN", ["proj-beta"]);
    expect(result.role).toBe("ADMIN");
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/admin/users/uid_target",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({
          role: "ADMIN",
          assigned_project_ids: ["proj-beta"],
        }),
      })
    );
  });

  it("falls back deterministically when suggestProjectGroupsWithAI has no API available", async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error("Network error"));
    vi.stubGlobal("fetch", mockFetch);

    const suggestion = await suggestProjectGroupsWithAI("test-token", "proj-fin-01", {
      name: "Treasury Payment Modernization",
      company_name: "Meridian Bank",
      description: "Audit and ledger compliance upgrade",
    });

    expect(suggestion.project_id).toBe("proj-fin-01");
    expect(suggestion.inference_mode).toBe("DETERMINISTIC_FALLBACK");
    expect(suggestion.suggested_canonical_groups).toContain("Chief Risk & Compliance Office");
    expect(suggestion.recommended_alert_thresholds.pulse_drop_delta).toBe(12);
  });

  it("falls back deterministically when fetchAdminGovernanceSummary has no API available", async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error("Network error"));
    vi.stubGlobal("fetch", mockFetch);

    const digest = await fetchAdminGovernanceSummary("test-token", [
      {
        uid: "u1",
        email: "ext@client.com",
        first_name: "Dana",
        last_name: "Client",
        phone_number: "+628111111111",
        role: "EXTERNAL_STAKEHOLDER",
        auth_provider: "password",
        assigned_project_ids: [],
        onboarding_status: "QUARANTINED_PENDING_INVITATION",
        created_at: "2026-10-18T00:00:00Z",
        last_login_at: "2026-10-18T00:00:00Z",
      },
    ]);

    expect(digest.inference_mode).toBe("DETERMINISTIC_FALLBACK");
    expect(digest.total_users).toBe(1);
    expect(digest.quarantined_users_count).toBe(1);
    expect(digest.recommended_actions.length).toBeGreaterThan(0);
  });
});

