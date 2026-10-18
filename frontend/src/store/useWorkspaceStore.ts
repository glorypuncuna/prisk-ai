import { create } from "zustand";
import {
  CompliancePackageDoc,
  DialogueBlockDoc,
  MeetingDoc,
  ProjectDoc,
  ProjectVectorDiagnostics,
  RiskRegisterDoc,
} from "../types/domain";
import { listMeetings, fetchProjectVectorDiagnostics } from "../api/meetingsApi";
import { listRisks } from "../api/risksApi";
import { listCompliancePackages } from "../api/complianceApi";

export interface WorkspaceState {
  activeProjectId: string | null;
  projects: ProjectDoc[];
  activeMeetingId: string | null;
  meetings: MeetingDoc[];
  activeMeeting: MeetingDoc | null;
  dialogueBlocks: DialogueBlockDoc[];
  risks: RiskRegisterDoc[];
  compliancePackages: CompliancePackageDoc[];
  vectorDiagnostics: ProjectVectorDiagnostics | null;
  isLoading: boolean;
  error: string | null;

  setActiveProjectId: (projectId: string | null) => void;
  setActiveMeetingId: (meetingId: string | null) => void;
  setProjects: (projects: ProjectDoc[]) => void;
  setMeetings: (meetings: MeetingDoc[]) => void;
  setActiveMeeting: (meeting: MeetingDoc | null) => void;
  setDialogueBlocks: (blocks: DialogueBlockDoc[]) => void;
  updateDialogueBlock: (
    blockId: string,
    updates: Partial<DialogueBlockDoc>
  ) => void;
  setRisks: (risks: RiskRegisterDoc[]) => void;
  updateRisk: (riskId: string, updates: Partial<RiskRegisterDoc>) => void;
  setCompliancePackages: (packages: CompliancePackageDoc[]) => void;
  setVectorDiagnostics: (diag: ProjectVectorDiagnostics | null) => void;
  setLoading: (isLoading: boolean) => void;
  setError: (error: string | null) => void;
  resetWorkspace: () => void;
  refreshWorkspaceData: (idToken: string, projectId: string) => Promise<void>;
}

export const useWorkspaceStore = create<WorkspaceState>((set, get) => ({
  activeProjectId: null,
  projects: [],
  activeMeetingId: null,
  meetings: [],
  activeMeeting: null,
  dialogueBlocks: [],
  risks: [],
  compliancePackages: [],
  vectorDiagnostics: null,
  isLoading: false,
  error: null,

  setActiveProjectId: (projectId) => {
    set({ activeProjectId: projectId });
  },

  setActiveMeetingId: (meetingId) => {
    const { meetings } = get();
    const found = meetings.find((m) => m.meeting_id === meetingId) || null;
    set({ activeMeetingId: meetingId, activeMeeting: found });
  },

  setProjects: (projects) => set({ projects }),
  setMeetings: (meetings) => {
    const { activeMeetingId } = get();
    const active = activeMeetingId
      ? meetings.find((m) => m.meeting_id === activeMeetingId) || null
      : null;
    set({ meetings, activeMeeting: active });
  },
  setActiveMeeting: (activeMeeting) => set({ activeMeeting }),

  setDialogueBlocks: (dialogueBlocks) => set({ dialogueBlocks }),
  updateDialogueBlock: (blockId, updates) =>
    set((state) => ({
      dialogueBlocks: state.dialogueBlocks.map((block) =>
        block.block_id === blockId ? { ...block, ...updates } : block
      ),
    })),

  setRisks: (risks) => set({ risks }),
  updateRisk: (riskId, updates) =>
    set((state) => ({
      risks: state.risks.map((risk) =>
        risk.risk_id === riskId ? { ...risk, ...updates } : risk
      ),
    })),

  setCompliancePackages: (compliancePackages) => set({ compliancePackages }),
  setVectorDiagnostics: (vectorDiagnostics) => set({ vectorDiagnostics }),
  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error }),

  resetWorkspace: () =>
    set({
      activeProjectId: null,
      activeMeetingId: null,
      activeMeeting: null,
      dialogueBlocks: [],
      risks: [],
      compliancePackages: [],
      vectorDiagnostics: null,
      error: null,
    }),

  refreshWorkspaceData: async (idToken: string, projectId: string) => {
    set({ isLoading: true, error: null, activeProjectId: projectId });
    try {
      const [meetings, risks, packages, diagnostics] = await Promise.all([
        listMeetings(idToken, projectId).catch(() => []),
        listRisks(idToken, { projectId }).catch(() => []),
        listCompliancePackages(idToken, projectId).catch(() => []),
        fetchProjectVectorDiagnostics(idToken, projectId).catch(() => null),
      ]);

      const currentActiveId = get().activeMeetingId;
      const activeMeeting = currentActiveId
        ? meetings.find((m) => m.meeting_id === currentActiveId) || meetings[0] || null
        : meetings[0] || null;

      set({
        meetings,
        risks,
        compliancePackages: packages,
        vectorDiagnostics: diagnostics,
        activeMeeting,
        activeMeetingId: activeMeeting?.meeting_id || null,
        isLoading: false,
      });
    } catch (err) {
      set({
        isLoading: false,
        error:
          err instanceof Error
            ? err.message
            : "Failed to synchronize workspace state",
      });
    }
  },
}));
