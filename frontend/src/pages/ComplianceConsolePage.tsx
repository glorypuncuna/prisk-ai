import React, { useCallback, useEffect, useState } from "react";
import { UserRole } from "../api/authApi";
import {
  ComplianceDownloadResponse,
  ComplianceExportPayload,
  ComplianceFormat,
  ComplianceFramework,
  ComplianceIntegrityCheck,
  ComplianceNarrativeResponse,
  CompliancePackageDoc,
  exportCompliancePackage,
  fetchAiComplianceNarrative,
  getComplianceDownloadUrl,
  listCompliancePackages,
  purgeMeetingGdpr,
  verifyCompliancePackageIntegrity,
} from "../api/complianceApi";

interface ComplianceConsolePageProps {
  idToken: string;
  userRole: UserRole;
  onBackToWorkspace: () => void;
  defaultProjectId?: string;
}

const SUPPORTED_FRAMEWORKS: {
  id: ComplianceFramework;
  label: string;
  description: string;
  clause: string;
}[] = [
  {
    id: "ISO_31000",
    label: "ISO 31000:2018",
    description: "Risk evaluation & treatment controls with 5x5 matrix containment",
    clause: "Clause 6.4 (Evaluation) & Clause 6.5 (Treatment)",
  },
  {
    id: "COSO",
    label: "COSO ERM 2017",
    description: "Enterprise governance, culture, and internal control principles",
    clause: "Principle 10 (Risk Analysis) & Principle 12 (Policies)",
  },
  {
    id: "SOC_2",
    label: "SOC 2 Type II",
    description: "Security, Confidentiality & Availability Trust Services Criteria",
    clause: "CC6.1 (Access Controls) & CC7.2 (Incident Monitoring)",
  },
  {
    id: "HIPAA",
    label: "HIPAA Security Rule",
    description: "45 CFR § 164.308/312 technical & administrative safeguards",
    clause: "Automated Google Cloud DLP De-identification",
  },
  {
    id: "GDPR",
    label: "GDPR (EU) 2016/679",
    description: "Article 17 Right-to-Erasure decoupled WORM compliance architecture",
    clause: "Article 17 (Erasure) & Article 32 (Security)",
  },
];

export const ComplianceConsolePage: React.FC<ComplianceConsolePageProps> = ({
  idToken,
  userRole,
  onBackToWorkspace,
  defaultProjectId = "proj-alpha",
}) => {
  const canManageCompliance =
    userRole === "ADMIN" || userRole === "EXECUTIVE" || userRole === "MANAGER";

  const [projectId, setProjectId] = useState<string>(defaultProjectId);
  const [companyName, setCompanyName] = useState<string>("Enterprise Holdings Inc.");
  const [selectedFrameworks, setSelectedFrameworks] = useState<string[]>([
    "ISO_31000",
    "COSO",
    "SOC_2",
    "GDPR",
  ]);
  const [exportFormat, setExportFormat] = useState<ComplianceFormat>("PDF");

  const [packages, setPackages] = useState<CompliancePackageDoc[]>([]);
  const [isLoadingPackages, setIsLoadingPackages] = useState<boolean>(true);
  const [isExporting, setIsExporting] = useState<boolean>(false);
  const [isPreviewingNarrative, setIsPreviewingNarrative] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Verification state per packageId
  const [verificationResults, setVerificationResults] = useState<
    Record<string, ComplianceIntegrityCheck>
  >({});
  const [isVerifyingPackageId, setIsVerifyingPackageId] = useState<string | null>(null);

  // Signed Download Drawer state
  const [inspectPackage, setInspectPackage] = useState<CompliancePackageDoc | null>(null);
  const [downloadInfo, setDownloadInfo] = useState<ComplianceDownloadResponse | null>(null);
  const [isLoadingDownload, setIsLoadingDownload] = useState<boolean>(false);

  // AI Narrative Preview state
  const [narrativePreview, setNarrativePreview] =
    useState<ComplianceNarrativeResponse | null>(null);

  // GDPR Article 17 Purge Modal state
  const [showGdprModal, setShowGdprModal] = useState<boolean>(false);
  const [gdprMeetingId, setGdprMeetingId] = useState<string>("");
  const [gdprReason, setGdprReason] = useState<string>(
    "Data subject formally invoked GDPR Article 17 Right-to-Erasure."
  );
  const [gdprConfirmed, setGdprConfirmed] = useState<boolean>(false);
  const [isPurgingGdpr, setIsPurgingGdpr] = useState<boolean>(false);
  const [purgeResult, setPurgeResult] = useState<{
    meeting_id: string;
    tombstone_event_id: string;
    purged_dialogue_blocks: number;
    purged_risks: number;
  } | null>(null);

  const loadPackages = useCallback(async () => {
    setIsLoadingPackages(true);
    setErrorMessage(null);
    try {
      const data = await listCompliancePackages(idToken, projectId);
      setPackages(data);
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to load compliance packages."
      );
    } finally {
      setIsLoadingPackages(false);
    }
  }, [idToken, projectId]);

  useEffect(() => {
    void loadPackages();
  }, [loadPackages]);

  // Handle keyboard Escape to dismiss drawers/modals
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (showGdprModal) setShowGdprModal(false);
        else if (inspectPackage) setInspectPackage(null);
        else if (narrativePreview) setNarrativePreview(null);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [showGdprModal, inspectPackage, narrativePreview]);

  const toggleFramework = (fw: string) => {
    setSelectedFrameworks((prev) =>
      prev.includes(fw) ? prev.filter((f) => f !== fw) : [...prev, fw]
    );
  };

  const handleExportPackage = async () => {
    if (!selectedFrameworks.length) {
      setErrorMessage("Please select at least one compliance framework.");
      return;
    }
    setIsExporting(true);
    setStatusMessage(null);
    setErrorMessage(null);
    try {
      const payload: ComplianceExportPayload = {
        project_id: projectId,
        target_frameworks: selectedFrameworks,
        format: exportFormat,
      };
      const created = await exportCompliancePackage(idToken, payload);
      setStatusMessage(
        `Compiled & sealed WORM compliance package ${created.package_id} (${created.format}) with SHA-256: ${created.sha256_hash.slice(0, 12)}...`
      );
      await loadPackages();
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to generate compliance package."
      );
    } finally {
      setIsExporting(false);
    }
  };

  const handlePreviewNarrative = async () => {
    if (!selectedFrameworks.length) {
      setErrorMessage("Please select at least one compliance framework.");
      return;
    }
    setIsPreviewingNarrative(true);
    setErrorMessage(null);
    try {
      const res = await fetchAiComplianceNarrative(idToken, {
        project_id: projectId,
        company_name: companyName,
        target_frameworks: selectedFrameworks,
      });
      setNarrativePreview(res);
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to synthesize compliance narrative."
      );
    } finally {
      setIsPreviewingNarrative(false);
    }
  };

  const handleVerifyIntegrity = async (pkg: CompliancePackageDoc) => {
    setIsVerifyingPackageId(pkg.package_id);
    try {
      const check = await verifyCompliancePackageIntegrity(idToken, pkg.package_id);
      setVerificationResults((prev) => ({
        ...prev,
        [pkg.package_id]: check,
      }));
    } catch (err) {
      setErrorMessage(
        err instanceof Error
          ? err.message
          : `Failed to verify integrity for ${pkg.package_id}`
      );
    } finally {
      setIsVerifyingPackageId(null);
    }
  };

  const handleOpenInspectDrawer = async (pkg: CompliancePackageDoc) => {
    setInspectPackage(pkg);
    setDownloadInfo(null);
    setIsLoadingDownload(true);
    try {
      const dl = await getComplianceDownloadUrl(idToken, pkg.package_id);
      setDownloadInfo(dl);
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to obtain signed download link."
      );
    } finally {
      setIsLoadingDownload(false);
    }
  };

  const handleExecuteGdprPurge = async () => {
    if (!gdprMeetingId.trim()) {
      setErrorMessage("Please provide a valid Meeting ID to purge.");
      return;
    }
    if (!gdprConfirmed) {
      setErrorMessage("Please check the confirmation box to authorize data subject erasure.");
      return;
    }
    setIsPurgingGdpr(true);
    setStatusMessage(null);
    setErrorMessage(null);
    try {
      const res = await purgeMeetingGdpr(idToken, gdprMeetingId.trim(), gdprReason);
      setPurgeResult({
        meeting_id: res.meeting_id,
        tombstone_event_id: res.tombstone_audit_event_id,
        purged_dialogue_blocks: res.purged_dialogue_blocks_count,
        purged_risks: res.purged_risks_count,
      });
      setStatusMessage(
        `GDPR Article 17 Purge completed for ${res.meeting_id}. Tombstone: ${res.tombstone_audit_event_id}`
      );
      await loadPackages();
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to execute GDPR cascade purge."
      );
    } finally {
      setIsPurgingGdpr(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900 px-4 py-4 sm:px-6">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded border border-emerald-500/60 bg-emerald-950 px-2.5 py-0.5 font-mono text-xs font-semibold text-emerald-200">
                WORM Compliant (SHA-256 Sealed)
              </span>
              <h1 className="text-lg font-bold text-slate-50 sm:text-xl">
                Compliance &amp; WORM Audit Console
              </h1>
            </div>
            <p className="mt-1 text-xs text-slate-300">
              Multi-framework regulatory packages (ISO 31000, COSO, SOC 2, HIPAA, GDPR),
              zero-verbatim privacy verification, and GDPR Article 17 Right-to-Erasure controls.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            {canManageCompliance && (
              <button
                type="button"
                onClick={() => {
                  setPurgeResult(null);
                  setShowGdprModal(true);
                }}
                className="min-h-[44px] rounded-lg border border-slate-700 bg-slate-800 px-3.5 py-2 text-xs font-semibold text-slate-200 transition-colors hover:border-rose-500/60 hover:bg-rose-950/60 hover:text-rose-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400"
              >
                GDPR Article 17 Purge
              </button>
            )}
            <button
              type="button"
              onClick={onBackToWorkspace}
              className="min-h-[44px] rounded-lg border border-slate-750 bg-slate-900 px-3.5 py-2 text-xs font-semibold text-slate-300 transition-colors hover:bg-slate-800 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
            >
              Back to Workspace
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
        {/* Status / Error alerts */}
        {statusMessage && (
          <div
            role="status"
            className="rounded-lg border border-emerald-500/60 bg-emerald-950 px-4 py-3 text-xs text-emerald-100"
          >
            {statusMessage}
          </div>
        )}
        {errorMessage && (
          <div
            role="alert"
            className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 rounded-lg border border-rose-500/40 bg-rose-950/40 px-4 py-3 text-xs text-rose-200"
          >
            <div>
              <p className="font-semibold text-rose-100">Compliance Service Notice</p>
              <p className="mt-0.5 text-rose-300">{errorMessage}</p>
            </div>
            <button
              type="button"
              onClick={() => void loadPackages()}
              className="min-h-[38px] shrink-0 rounded-lg border border-rose-500/50 bg-rose-900/60 px-3.5 py-1.5 font-semibold text-rose-100 hover:bg-rose-800 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400"
            >
              Retry
            </button>
          </div>
        )}

        {/* Section 1: Audit Package Generator */}
        <section className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-5">
          <div className="flex flex-wrap items-center justify-between border-b border-slate-800 pb-3 gap-2">
            <div>
              <h2 className="text-sm font-bold text-white uppercase tracking-wider">
                Generate Sealed WORM Compliance Package
              </h2>
              <p className="mt-0.5 text-xs text-slate-300">
                Compiles 5 sanitized sections with zero verbatim quotes and stores immutable artifact in Cloud Storage.
              </p>
            </div>
            <span className="font-mono text-xs text-emerald-300">
              Project: {projectId}
            </span>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <label
                htmlFor="compliance-project-id"
                className="block text-xs font-medium text-slate-200"
              >
                Project Identifier
              </label>
              <input
                id="compliance-project-id"
                type="text"
                value={projectId}
                onChange={(e) => setProjectId(e.target.value)}
                className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              />
            </div>

            <div>
              <label
                htmlFor="compliance-company-name"
                className="block text-xs font-medium text-slate-200"
              >
                Audited Organization Name
              </label>
              <input
                id="compliance-company-name"
                type="text"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              />
            </div>

            <div>
              <label
                htmlFor="compliance-format"
                className="block text-xs font-medium text-slate-200"
              >
                Artifact Output Format
              </label>
              <div className="mt-1 flex rounded-lg border border-slate-700 bg-slate-950 p-1">
                {(["PDF", "CSV", "JSON"] as ComplianceFormat[]).map((fmt) => (
                  <button
                    key={fmt}
                    type="button"
                    onClick={() => setExportFormat(fmt)}
                    className={`flex-1 min-h-[36px] rounded py-1 text-xs font-semibold transition ${
                      exportFormat === fmt
                        ? "bg-indigo-600 text-white shadow"
                        : "text-slate-300 hover:text-white"
                    }`}
                  >
                    {fmt}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Framework Checkbox Selection */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300">
              Target Regulatory Frameworks (Select all applicable)
            </label>
            <div className="mt-2.5 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {SUPPORTED_FRAMEWORKS.map((fw) => {
                const isSelected = selectedFrameworks.includes(fw.id);
                return (
                  <label
                    key={fw.id}
                    className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition ${
                      isSelected
                        ? "border-indigo-500 bg-indigo-950/40 text-white"
                        : "border-slate-800 bg-slate-950/60 text-slate-300 hover:border-slate-700"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleFramework(fw.id)}
                      className="mt-0.5 h-4 w-4 rounded border-slate-700 bg-slate-950 text-indigo-600 focus-visible:ring-2 focus-visible:ring-indigo-400"
                    />
                    <div className="text-xs">
                      <div className="font-bold">{fw.label}</div>
                      <div className="mt-0.5 text-[11px] text-slate-300 leading-tight">
                        {fw.description}
                      </div>
                      <div className="mt-1 font-mono text-[10px] text-indigo-300">
                        {fw.clause}
                      </div>
                    </div>
                  </label>
                );
              })}
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-800 pt-4">
            <button
              type="button"
              disabled={isPreviewingNarrative}
              onClick={handlePreviewNarrative}
              className="min-h-[44px] rounded-lg border border-purple-500/60 bg-purple-950 px-4 py-2 text-xs font-semibold text-purple-100 hover:bg-purple-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400 disabled:opacity-50"
            >
              {isPreviewingNarrative
                ? "Synthesizing AI Narrative..."
                : "Preview AI Attestation Narrative"}
            </button>

            {canManageCompliance && (
              <button
                type="button"
                disabled={isExporting}
                onClick={handleExportPackage}
                className="min-h-[44px] rounded-lg bg-indigo-600 px-6 py-2 text-xs font-semibold text-white hover:bg-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 disabled:opacity-50"
              >
                {isExporting ? "Sealing WORM Package..." : "Compile & Seal WORM Package"}
              </button>
            )}
          </div>
        </section>

        {/* Section 2: WORM Package History Table */}
        <section className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <h2 className="text-sm font-bold text-white uppercase tracking-wider">
                Cryptographically Sealed WORM Package History
              </h2>
              <p className="mt-0.5 text-xs text-slate-300">
                Immutable artifacts sealed with SHA-256 digests. Download or verify integrity at any time.
              </p>
            </div>
            <button
              type="button"
              onClick={() => void loadPackages()}
              className="min-h-[36px] rounded border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-800"
            >
              Refresh Table
            </button>
          </div>

          {isLoadingPackages ? (
            <div className="py-12 text-center">
              <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-indigo-500 border-t-transparent" />
              <p className="mt-3 text-xs text-slate-300">Loading sealed WORM packages...</p>
            </div>
          ) : packages.length === 0 ? (
            <div className="rounded-lg border border-slate-800 bg-slate-950 p-8 text-center text-xs text-slate-300">
              No WORM compliance packages generated yet for project {projectId}. Compile your first package above.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-800 bg-slate-950 text-slate-200">
                    <th className="px-3 py-3 font-semibold">Package ID &amp; Version</th>
                    <th className="px-3 py-3 font-semibold">Frameworks</th>
                    <th className="px-3 py-3 font-semibold">Format &amp; Size</th>
                    <th className="px-3 py-3 font-semibold">SHA-256 Digest</th>
                    <th className="px-3 py-3 font-semibold">Cryptographic Integrity</th>
                    <th className="px-3 py-3 font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {packages.map((pkg) => {
                    const verification = verificationResults[pkg.package_id];
                    const isVerifying = isVerifyingPackageId === pkg.package_id;
                    const truncatedHash = `${pkg.sha256_hash.slice(0, 10)}...${pkg.sha256_hash.slice(-8)}`;

                    return (
                      <tr
                        key={pkg.package_id}
                        className="bg-slate-900/60 hover:bg-slate-800/50"
                      >
                        <td className="px-3 py-3 align-top">
                          <div className="font-mono font-bold text-white">
                            {pkg.package_id}
                          </div>
                          <span className="font-mono text-[11px] text-slate-400">
                            {pkg.status}
                          </span>
                        </td>

                        <td className="px-3 py-3 align-top">
                          <div className="flex flex-wrap gap-1">
                            {pkg.target_frameworks.map((fw: string) => (
                              <span
                                key={fw}
                                className="rounded border border-indigo-500/40 bg-indigo-950 px-2 py-0.5 font-mono text-[10px] text-indigo-200"
                              >
                                {fw}
                              </span>
                            ))}
                          </div>
                        </td>

                        <td className="px-3 py-3 align-top font-mono">
                          <span className="rounded bg-slate-800 px-2 py-0.5 font-bold text-slate-200">
                            {pkg.format}
                          </span>
                        </td>

                        <td className="px-3 py-3 align-top font-mono text-[11px] text-slate-300">
                          <span title={pkg.sha256_hash}>{truncatedHash}</span>
                        </td>

                        <td className="px-3 py-3 align-top">
                          {verification ? (
                            verification.integrity_valid ? (
                              <span className="inline-flex items-center gap-1.5 rounded border border-emerald-500/70 bg-emerald-950 px-2.5 py-1 font-mono text-[11px] font-bold text-emerald-200">
                                ✓ SHA-256 Valid
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1.5 rounded border border-rose-500/70 bg-rose-950 px-2.5 py-1 font-mono text-[11px] font-bold text-rose-200">
                                ✗ Digest Mismatch
                              </span>
                            )
                          ) : (
                            <button
                              type="button"
                              disabled={isVerifying}
                              onClick={() => void handleVerifyIntegrity(pkg)}
                              className="min-h-[36px] rounded border border-slate-700 bg-slate-950 px-2.5 py-1 font-mono text-[11px] text-slate-200 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-indigo-400 disabled:opacity-50"
                            >
                              {isVerifying ? "Verifying..." : "Verify Hash"}
                            </button>
                          )}
                        </td>

                        <td className="px-3 py-3 align-top">
                          <div className="flex flex-wrap gap-2">
                            <button
                              type="button"
                              onClick={() => void handleOpenInspectDrawer(pkg)}
                              className="min-h-[36px] rounded border border-indigo-500/60 bg-indigo-950 px-3 py-1 text-xs font-semibold text-indigo-100 hover:bg-indigo-900 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-indigo-400"
                            >
                              Inspect / Download
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

        {/* AI Compliance Narrative Preview Drawer */}
        {narrativePreview && (
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="narrative-preview-title"
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4"
          >
            <div className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-xl border border-purple-500/50 bg-slate-900 p-6 shadow-2xl">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div>
                  <span className="rounded border border-purple-500/60 bg-purple-950 px-2 py-0.5 font-mono text-[11px] font-semibold text-purple-200">
                    Vertex AI Gemini 2.5 Flash
                  </span>
                  <h2
                    id="narrative-preview-title"
                    className="mt-1 text-base font-bold text-white"
                  >
                    AI Privacy-Preserving Compliance Attestation Narrative
                  </h2>
                </div>
                <button
                  type="button"
                  onClick={() => setNarrativePreview(null)}
                  className="min-h-[44px] min-w-[44px] rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-800"
                >
                  Close
                </button>
              </div>

              <div className="mt-4 space-y-4 text-xs">
                {/* Privacy Badge */}
                <div className="flex items-center justify-between rounded-lg border border-emerald-500/40 bg-emerald-950/40 p-3">
                  <span className="font-semibold text-emerald-200">
                    Zero Verbatim Participant Quotes Verified
                  </span>
                  <span className="font-mono text-[11px] text-emerald-300">
                    DLP Scrubbed &amp; Speaker Blind
                  </span>
                </div>

                {/* Executive Summary */}
                <div>
                  <h3 className="font-semibold uppercase tracking-wider text-purple-200">
                    Executive Governance &amp; Risk Posture Summary
                  </h3>
                  <div className="mt-1.5 rounded-lg border border-slate-800 bg-slate-950 p-3 text-slate-200 leading-relaxed">
                    {narrativePreview.executive_summary}
                  </div>
                </div>

                {/* Framework Treatment Summaries */}
                <div>
                  <h3 className="font-semibold uppercase tracking-wider text-purple-200">
                    Regulatory Framework-by-Framework Treatment Analysis
                  </h3>
                  <div className="mt-1.5 space-y-2.5">
                    {Object.entries(narrativePreview.framework_treatment_summaries).map(
                      ([fw, desc]) => (
                        <div
                          key={fw}
                          className="rounded-lg border border-slate-800 bg-slate-950 p-3 text-slate-200"
                        >
                          <span className="rounded border border-indigo-500/40 bg-indigo-950 px-2 py-0.5 font-mono text-[10px] font-bold text-indigo-200">
                            {fw}
                          </span>
                          <p className="mt-1.5 text-xs leading-relaxed">{desc}</p>
                        </div>
                      )
                    )}
                  </div>
                </div>

                {/* Continuous Monitoring & Privacy */}
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                    <h4 className="font-semibold text-purple-200">
                      Continuous SLA Escalation Monitoring
                    </h4>
                    <p className="mt-1 text-slate-300 text-[11px] leading-relaxed">
                      {narrativePreview.continuous_monitoring_attestation}
                    </p>
                  </div>

                  <div className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                    <h4 className="font-semibold text-purple-200">
                      Zero-Audio Retention &amp; Cryptographic Sealing
                    </h4>
                    <p className="mt-1 text-slate-300 text-[11px] leading-relaxed">
                      {narrativePreview.zero_audio_privacy_statement}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Signed Download / Package Inspection Drawer */}
        {inspectPackage && (
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="inspect-package-title"
            className="fixed inset-0 z-50 flex justify-end bg-slate-950/80"
          >
            <div className="flex h-full w-full max-w-xl flex-col overflow-y-auto border-l border-slate-700 bg-slate-900 p-6 shadow-2xl">
              <div className="flex items-center justify-between border-b border-slate-800 pb-4">
                <div>
                  <h2
                    id="inspect-package-title"
                    className="text-base font-bold text-white"
                  >
                    WORM Sealed Package: {inspectPackage.package_id}
                  </h2>
                  <p className="font-mono text-xs text-slate-300">
                    Status: {inspectPackage.status} • {inspectPackage.format}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setInspectPackage(null)}
                  className="min-h-[44px] rounded-lg border border-slate-700 px-4 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-800"
                >
                  Close
                </button>
              </div>

              <div className="mt-5 space-y-4 text-xs">
                {/* Cryptographic Hash */}
                <div className="rounded-lg border border-slate-800 bg-slate-950 p-3.5">
                  <div className="text-slate-400 uppercase tracking-wide text-[11px] font-semibold">
                    Cryptographic SHA-256 Digest
                  </div>
                  <div className="mt-1.5 break-all font-mono text-xs text-emerald-300 bg-slate-900 p-2 rounded border border-slate-800">
                    {inspectPackage.sha256_hash}
                  </div>
                </div>

                {/* Cloud Storage URI */}
                <div className="rounded-lg border border-slate-800 bg-slate-950 p-3.5">
                  <div className="text-slate-400 uppercase tracking-wide text-[11px] font-semibold">
                    Cloud Storage WORM URI
                  </div>
                  <div className="mt-1.5 break-all font-mono text-xs text-slate-200">
                    {inspectPackage.gcs_uri}
                  </div>
                </div>

                {/* Target Frameworks */}
                <div className="rounded-lg border border-slate-800 bg-slate-950 p-3.5">
                  <div className="text-slate-400 uppercase tracking-wide text-[11px] font-semibold">
                    Included Regulatory Frameworks
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {inspectPackage.target_frameworks.map((fw: string) => (
                      <span
                        key={fw}
                        className="rounded border border-indigo-500/40 bg-indigo-950 px-2 py-0.5 font-mono text-xs text-indigo-200"
                      >
                        {fw}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Direct Download Action */}
                <div className="pt-2">
                  {isLoadingDownload ? (
                    <div className="py-4 text-center text-xs text-slate-300">
                      Fetching signed download token...
                    </div>
                  ) : downloadInfo ? (
                    <a
                      href={downloadInfo.download_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex min-h-[44px] w-full items-center justify-center rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
                    >
                      Download Sealed Binary Artifact ({inspectPackage.format})
                    </a>
                  ) : (
                    <a
                      href={`/api/v1/compliance/packages/${inspectPackage.package_id}/download`}
                      className="flex min-h-[44px] w-full items-center justify-center rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                    >
                      Download Binary ({inspectPackage.format})
                    </a>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* GDPR Article 17 Right-to-Erasure Modal */}
        {showGdprModal && (
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="gdpr-dialog-title"
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4"
          >
            <div className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-xl border border-rose-500/70 bg-slate-900 p-6 shadow-2xl space-y-4">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div className="flex items-center gap-2">
                  <span className="rounded border border-rose-500/70 bg-rose-950 px-2 py-0.5 font-mono text-[11px] font-bold text-rose-200">
                    GDPR Article 17
                  </span>
                  <h2
                    id="gdpr-dialog-title"
                    className="text-base font-bold text-white"
                  >
                    Right-to-Erasure Cascade Purge
                  </h2>
                </div>
                <button
                  type="button"
                  onClick={() => setShowGdprModal(false)}
                  className="min-h-[44px] min-w-[44px] rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-800"
                >
                  Cancel
                </button>
              </div>

              {/* Warning Alert */}
              <div className="rounded-lg border border-rose-500/50 bg-rose-950/60 p-3.5 text-xs text-rose-100 leading-relaxed space-y-1.5">
                <p className="font-bold">CRITICAL DELETION NOTICE:</p>
                <p>
                  Pursuant to GDPR Article 17, this operation permanently obliterates all raw participant speech,
                  dialogue blocks, vector embeddings, and linked risk draft records for the target meeting.
                </p>
                <p>
                  Sealed WORM compliance packages decouple participant quotes, preserving immutable SHA-256
                  audit hashes while redacting participant text with an irreversible cryptographic tombstone.
                </p>
              </div>

              {purgeResult ? (
                <div className="rounded-lg border border-emerald-500/60 bg-emerald-950 p-4 space-y-2 text-xs">
                  <div className="font-bold text-emerald-200">
                    ✓ Cascade Purge Executed Successfully
                  </div>
                  <div className="text-slate-300">
                    Meeting ID: <span className="font-mono text-white">{purgeResult.meeting_id}</span>
                  </div>
                  <div className="text-slate-300">
                    Purged Dialogue Blocks: <span className="font-mono text-white">{purgeResult.purged_dialogue_blocks}</span>
                  </div>
                  <div className="text-slate-300">
                    Purged Draft Risks: <span className="font-mono text-white">{purgeResult.purged_risks}</span>
                  </div>
                  <div className="text-slate-300">
                    Audit Tombstone ID: <span className="font-mono text-emerald-300">{purgeResult.tombstone_event_id}</span>
                  </div>
                </div>
              ) : (
                <div className="space-y-4 text-xs">
                  <div>
                    <label
                      htmlFor="gdpr-target-meeting-id"
                      className="block font-medium text-slate-200"
                    >
                      Target Meeting ID to Purge
                    </label>
                    <input
                      id="gdpr-target-meeting-id"
                      type="text"
                      placeholder="e.g. mtg-2026-0001"
                      value={gdprMeetingId}
                      onChange={(e) => setGdprMeetingId(e.target.value)}
                      className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400"
                    />
                  </div>

                  <div>
                    <label
                      htmlFor="gdpr-reason"
                      className="block font-medium text-slate-200"
                    >
                      Regulatory Erasure Rationale
                    </label>
                    <textarea
                      id="gdpr-reason"
                      rows={2}
                      value={gdprReason}
                      onChange={(e) => setGdprReason(e.target.value)}
                      className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400"
                    />
                  </div>

                  <div className="flex items-start gap-3 rounded-lg border border-slate-800 bg-slate-950 p-3">
                    <input
                      id="gdpr-confirm-checkbox"
                      type="checkbox"
                      checked={gdprConfirmed}
                      onChange={(e) => setGdprConfirmed(e.target.checked)}
                      className="mt-0.5 h-4 w-4 rounded border-slate-700 bg-slate-950 text-rose-600 focus-visible:ring-2 focus-visible:ring-rose-400"
                    />
                    <label
                      htmlFor="gdpr-confirm-checkbox"
                      className="text-xs text-slate-200 leading-tight"
                    >
                      I confirm that data subject erasure was formally verified and acknowledge that this
                      cascade deletion cannot be undone.
                    </label>
                  </div>

                  <div className="flex justify-end gap-2 pt-2 border-t border-slate-800">
                    <button
                      type="button"
                      onClick={() => setShowGdprModal(false)}
                      className="min-h-[44px] rounded-lg border border-slate-700 px-4 py-2 font-semibold text-slate-200 hover:bg-slate-800"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      disabled={isPurgingGdpr || !gdprConfirmed || !gdprMeetingId.trim()}
                      onClick={handleExecuteGdprPurge}
                      className="min-h-[44px] rounded-lg bg-rose-600 px-5 py-2 font-semibold text-white hover:bg-rose-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400 disabled:opacity-50"
                    >
                      {isPurgingGdpr ? "Executing Purge..." : "Execute Cascade Purge"}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
};
