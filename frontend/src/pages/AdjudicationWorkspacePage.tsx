import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  BlockExplainResponse,
  commitGoldenRecord,
  DialogueBlock,
  DraftRiskRecord,
  explainDialogueBlockRationale,
  fetchAdjudicationWorkspace,
  fetchMeetingsList,
  GroupPulseMetric,
  MeetingRecord,
  MoMSummary,
  regenerateMeetingInsights,
  splitDialogueBlock,
  updateDialogueBlockScoreOrGroup,
  updateSessionSpeakerGrouping,
  XAIAttributionItem,
} from "../api/adjudicationApi";
import {
  calculateDeterministicRollups,
  splitDialogueBlockClient,
} from "../lib/rollupUtils";
import { XaiRationaleDrawer } from "../components/XaiRationaleDrawer";

interface AdjudicationWorkspacePageProps {
  idToken: string;
  initialMeetingId?: string;
  onBackToWorkspace: () => void;
}

const DLP_TOKEN_REGEX =
  /(\[(?:PHONE_NUMBER|EMAIL_ADDRESS|EMAIL|CREDIT_CARD|CREDIT_CARD_NUMBER|GOVERNMENT_ID|US_SOCIAL_SECURITY_NUMBER|ADDRESS|STREET_ADDRESS|BANK_ACCOUNT|IBAN_CODE)\])/g;

function getPulseScoreStatus(score: number): {
  label: string;
  badgeClass: string;
  barClass: string;
} {
  if (score < 40) {
    return {
      label: "Negative / At Risk",
      badgeClass: "border-rose-500/50 bg-rose-950/60 text-rose-200",
      barClass: "bg-rose-500",
    };
  }
  if (score < 70) {
    return {
      label: "Neutral / Guarded",
      badgeClass: "border-amber-500/50 bg-amber-950/60 text-amber-200",
      barClass: "bg-amber-500",
    };
  }
  return {
    label: "Positive / Aligned",
    badgeClass: "border-emerald-500/50 bg-emerald-950/60 text-emerald-200",
    barClass: "bg-emerald-500",
  };
}

function renderDlpAndXaiHighlightedText(
  text: string,
  attributions?: XAIAttributionItem[]
): React.ReactNode {
  if (!text) return null;

  if (attributions && attributions.length > 0) {
    const sorted = [...attributions]
      .filter(
        (a) =>
          a.start_char >= 0 &&
          a.end_char <= text.length &&
          a.start_char < a.end_char
      )
      .sort((a, b) => a.start_char - b.start_char);

    const nodes: React.ReactNode[] = [];
    let cursor = 0;

    sorted.forEach((attr, idx) => {
      if (attr.start_char < cursor) return;
      if (attr.start_char > cursor) {
        nodes.push(
          <React.Fragment key={`plain-${idx}`}>
            {renderDlpTokens(text.slice(cursor, attr.start_char))}
          </React.Fragment>
        );
      }
      const isPositive = attr.attribution_weight >= 0;
      const phraseSlice = text.slice(attr.start_char, attr.end_char);
      nodes.push(
        <mark
          key={`xai-${idx}`}
          title={`${attr.rubric_dimension}: ${attr.rationale} (${
            attr.attribution_weight >= 0 ? "+" : ""
          }${attr.attribution_weight})`}
          className={`rounded px-1 py-0.5 font-medium underline decoration-2 ${
            isPositive
              ? "bg-emerald-900/70 text-emerald-100 decoration-emerald-400"
              : "bg-rose-900/70 text-rose-100 decoration-rose-400"
          }`}
        >
          {renderDlpTokens(phraseSlice)}
        </mark>
      );
      cursor = attr.end_char;
    });

    if (cursor < text.length) {
      nodes.push(
        <React.Fragment key="plain-tail">
          {renderDlpTokens(text.slice(cursor))}
        </React.Fragment>
      );
    }
    return nodes;
  }

  return renderDlpTokens(text);
}

function renderDlpTokens(segment: string): React.ReactNode {
  const parts = segment.split(DLP_TOKEN_REGEX);
  return parts.map((part, idx) => {
    if (DLP_TOKEN_REGEX.test(part)) {
      DLP_TOKEN_REGEX.lastIndex = 0;
      return (
        <span
          key={`dlp-${idx}`}
          className="mx-0.5 inline-flex items-center rounded border border-amber-500/60 bg-amber-950/80 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-amber-200"
          title="Scrubbed by Google Cloud DLP before persistence"
        >
          DLP Masked: {part}
        </span>
      );
    }
    return <React.Fragment key={`txt-${idx}`}>{part}</React.Fragment>;
  });
}

export const AdjudicationWorkspacePage: React.FC<
  AdjudicationWorkspacePageProps
> = ({ idToken, initialMeetingId, onBackToWorkspace }) => {
  const [meetings, setMeetings] = useState<MeetingRecord[]>([]);
  const [selectedMeetingId, setSelectedMeetingId] = useState<string>(
    initialMeetingId || "mtg_alpha_adjudication"
  );
  const [meeting, setMeeting] = useState<MeetingRecord | null>(null);
  const [blocks, setBlocks] = useState<DialogueBlock[]>([]);
  const [canonicalGroups, setCanonicalGroups] = useState<string[]>([
    "Client Legal & Compliance",
    "Client Executive Sponsor",
    "Client Engineering",
    "Internal Delivery Team",
  ]);
  const [ephemeralSpeakerMap, setEphemeralSpeakerMap] = useState<
    Record<string, string>
  >({});
  const [draftRisks, setDraftRisks] = useState<DraftRiskRecord[]>([]);
  const [approvedRiskIds, setApprovedRiskIds] = useState<Set<string>>(
    new Set()
  );

  // Deterministic live rollup state (<50ms client-side reactivity)
  const [livePulseScore, setLivePulseScore] = useState<number>(50.0);
  const [liveGroupScores, setLiveGroupScores] = useState<
    Record<string, GroupPulseMetric>
  >({});
  const [lastRollupDurationMs, setLastRollupDurationMs] = useState<number>(0.2);

  // Split & editor state per block
  const [activeBlockId, setActiveBlockId] = useState<string | null>(null);
  const [splitCursorByBlock, setSplitCursorByBlock] = useState<
    Record<string, number>
  >({});
  const [editingTextByBlock, setEditingTextByBlock] = useState<
    Record<string, string>
  >({});
  const [xaiByBlock, setXaiByBlock] = useState<
    Record<string, BlockExplainResponse>
  >({});
  const [loadingXaiBlockId, setLoadingXaiBlockId] = useState<string | null>(
    null
  );
  const [drawerXaiBlockId, setDrawerXaiBlockId] = useState<string | null>(null);

  // MoM editable summary
  const [momSummaryText, setMomSummaryText] = useState<string>("");

  // UI feedback states (R-27: loading, error, empty)
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [statusNotice, setStatusNotice] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState<boolean>(false);

  const textareaRefs = useRef<Record<string, HTMLTextAreaElement | null>>({});

  const loadWorkspace = useCallback(
    async (targetMeetingId: string) => {
      setIsLoading(true);
      setErrorMessage(null);
      try {
        const mtgList = await fetchMeetingsList(idToken).catch(() => []);
        setMeetings(mtgList);

        const resolvedId =
          targetMeetingId ||
          (mtgList.length > 0 ? mtgList[0].meeting_id : "mtg_alpha_adjudication");

        const data = await fetchAdjudicationWorkspace(idToken, resolvedId);
        setSelectedMeetingId(resolvedId);
        setMeeting(data.meeting);
        setBlocks(data.dialogue_blocks);
        setCanonicalGroups(
          data.canonical_groups.length > 0
            ? data.canonical_groups
            : [
                "Client Legal & Compliance",
                "Client Executive Sponsor",
                "Client Engineering",
                "Internal Delivery Team",
              ]
        );
        setEphemeralSpeakerMap(data.ephemeral_speaker_map || {});
        setDraftRisks(data.draft_risks || []);
        setApprovedRiskIds(
          new Set((data.draft_risks || []).map((r) => r.risk_id))
        );

        const initialTextMap: Record<string, string> = {};
        const initialSplitMap: Record<string, number> = {};
        for (const blk of data.dialogue_blocks) {
          initialTextMap[blk.block_id] = blk.text_scrubbed;
          initialSplitMap[blk.block_id] = Math.max(
            1,
            Math.floor((blk.text_scrubbed || "").length / 2)
          );
        }
        setEditingTextByBlock(initialTextMap);
        setSplitCursorByBlock(initialSplitMap);
        if (data.dialogue_blocks.length > 0) {
          setActiveBlockId(data.dialogue_blocks[0].block_id);
        }

        const t0 = performance.now();
        const rollup = calculateDeterministicRollups(
          data.dialogue_blocks,
          data.meeting.group_scores
        );
        const elapsed = Math.round((performance.now() - t0) * 100) / 100;
        setLastRollupDurationMs(elapsed);
        setLivePulseScore(rollup.overallPulseScore);
        setLiveGroupScores(rollup.groupScores);

        const mom = data.meeting.mom_summary;
        if (mom && typeof mom === "object" && "summary" in mom) {
          setMomSummaryText(String(mom.summary || ""));
        } else if (typeof mom === "string") {
          setMomSummaryText(mom);
        } else {
          setMomSummaryText("");
        }
      } catch (err) {
        setErrorMessage(
          err instanceof Error
            ? err.message
            : "Unable to load the HITL Adjudication Workspace."
        );
      } finally {
        setIsLoading(false);
      }
    },
    [idToken]
  );

  useEffect(() => {
    void loadWorkspace(selectedMeetingId);
  }, [loadWorkspace, selectedMeetingId]);

  const isLockedGoldenRecord = meeting?.status === "GOLDEN_RECORD";

  // Recalculate deterministic rollup in <50ms whenever blocks change
  const recomputeClientRollup = useCallback(
    (nextBlocks: DialogueBlock[]) => {
      const t0 = performance.now();
      const rollup = calculateDeterministicRollups(nextBlocks, liveGroupScores);
      const elapsed = Math.round((performance.now() - t0) * 100) / 100;
      setLastRollupDurationMs(elapsed);
      setLivePulseScore(rollup.overallPulseScore);
      setLiveGroupScores(rollup.groupScores);
    },
    [liveGroupScores]
  );

  const handleSliderChange = (blockId: string, newScoreValue: number) => {
    if (isLockedGoldenRecord) return;
    const clamped = Math.max(0, Math.min(100, Math.round(newScoreValue)));
    const nextBlocks = blocks.map((blk) =>
      blk.block_id === blockId
        ? {
            ...blk,
            sentiment_score: clamped,
            is_human_overridden: true,
          }
        : blk
    );
    setBlocks(nextBlocks);
    recomputeClientRollup(nextBlocks);
  };

  const handleSliderCommit = async (blockId: string, finalScore: number) => {
    if (isLockedGoldenRecord || !meeting) return;
    try {
      const resp = await updateDialogueBlockScoreOrGroup(
        idToken,
        meeting.meeting_id,
        blockId,
        { final_pulse_score: finalScore }
      );
      setLivePulseScore(resp.pulse_score);
      setLiveGroupScores(resp.group_scores);
      setStatusNotice(
        `Block ${blockId} Pulse Score calibrated to ${finalScore}/100. Group and Meeting Pulse rollups updated.`
      );
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to persist score override"
      );
    }
  };

  const handleSessionSpeakerGroupChange = async (
    block: DialogueBlock,
    newGroupName: string,
    applyToAllFromSpeaker: boolean
  ) => {
    if (isLockedGoldenRecord || !meeting) return;
    const speakerKey =
      block.ephemeral_speaker_account_id ||
      block.speaker_alias ||
      block.display_speaker_label;

    if (applyToAllFromSpeaker && speakerKey) {
      // Optimistic client update for all unpinned blocks from this speaker
      const nextMap = { ...ephemeralSpeakerMap, [speakerKey]: newGroupName };
      setEphemeralSpeakerMap(nextMap);

      const nextBlocks = blocks.map((b) => {
        const bKey =
          b.ephemeral_speaker_account_id ||
          b.speaker_alias ||
          b.display_speaker_label;
        if (bKey === speakerKey && !b.is_pinned) {
          return { ...b, group_name: newGroupName, group_id: newGroupName };
        }
        return b;
      });
      setBlocks(nextBlocks);
      recomputeClientRollup(nextBlocks);

      try {
        const resp = await updateSessionSpeakerGrouping(
          idToken,
          meeting.meeting_id,
          speakerKey,
          newGroupName
        );
        setBlocks(resp.blocks);
        setEphemeralSpeakerMap(resp.ephemeral_speaker_map);
        setLivePulseScore(resp.pulse_score);
        setLiveGroupScores(resp.group_scores);
        setStatusNotice(
          `Assigned speaker ${speakerKey} to "${newGroupName}" for this session (${resp.updated_block_ids.length} unpinned blocks updated).`
        );
      } catch (err) {
        setErrorMessage(
          err instanceof Error
            ? err.message
            : "Failed to update session speaker grouping"
        );
      }
    } else {
      // Single block pinned group override
      const nextBlocks = blocks.map((b) =>
        b.block_id === block.block_id
          ? {
              ...b,
              group_name: newGroupName,
              group_id: newGroupName,
              is_pinned: true,
            }
          : b
      );
      setBlocks(nextBlocks);
      recomputeClientRollup(nextBlocks);

      try {
        const resp = await updateDialogueBlockScoreOrGroup(
          idToken,
          meeting.meeting_id,
          block.block_id,
          { group_name: newGroupName, is_pinned: true }
        );
        setLivePulseScore(resp.pulse_score);
        setLiveGroupScores(resp.group_scores);
        setStatusNotice(
          `Pinned block ${block.block_id} to group "${newGroupName}".`
        );
      } catch (err) {
        setErrorMessage(
          err instanceof Error ? err.message : "Failed to pin block group"
        );
      }
    }
  };

  const handleTogglePinBlock = async (block: DialogueBlock) => {
    if (isLockedGoldenRecord || !meeting) return;
    const nextPinned = !block.is_pinned;
    setBlocks((prev) =>
      prev.map((b) =>
        b.block_id === block.block_id ? { ...b, is_pinned: nextPinned } : b
      )
    );
    try {
      await updateDialogueBlockScoreOrGroup(
        idToken,
        meeting.meeting_id,
        block.block_id,
        { is_pinned: nextPinned }
      );
    } catch {
      // Ignore transient toggle error
    }
  };

  const handleBubbleSplit = async (block: DialogueBlock) => {
    if (isLockedGoldenRecord || !meeting) return;
    const text = editingTextByBlock[block.block_id] ?? block.text_scrubbed;
    const cursorIdx =
      splitCursorByBlock[block.block_id] ?? Math.floor(text.length / 2);

    if (cursorIdx <= 0 || cursorIdx >= text.length) {
      setErrorMessage(
        "Place your text cursor inside the dialogue block text (not at the very start or end) before splitting."
      );
      return;
    }

    // Immediate optimistic client split
    const optimisticBlocks = splitDialogueBlockClient(
      blocks,
      block.block_id,
      cursorIdx
    );
    setBlocks(optimisticBlocks);
    recomputeClientRollup(optimisticBlocks);

    setIsBusy(true);
    setErrorMessage(null);
    try {
      const resp = await splitDialogueBlock(
        idToken,
        meeting.meeting_id,
        block.block_id,
        cursorIdx
      );
      setBlocks(resp.blocks);
      setLivePulseScore(resp.pulse_score);
      setLiveGroupScores(resp.group_scores);

      const nextTextMap = { ...editingTextByBlock };
      const nextSplitMap = { ...splitCursorByBlock };
      for (const child of resp.child_blocks) {
        nextTextMap[child.block_id] = child.text_scrubbed;
        nextSplitMap[child.block_id] = Math.max(
          1,
          Math.floor(child.text_scrubbed.length / 2)
        );
      }
      setEditingTextByBlock(nextTextMap);
      setSplitCursorByBlock(nextSplitMap);
      setStatusNotice(
        `Bubble Split complete: "${block.block_id}" divided into "${resp.child_blocks[0]?.block_id}" and "${resp.child_blocks[1]?.block_id}" inheriting parent score and group.`
      );
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Bubble split failed"
      );
      await loadWorkspace(meeting.meeting_id);
    } finally {
      setIsBusy(false);
    }
  };

  const handleSaveBlockText = async (block: DialogueBlock) => {
    if (isLockedGoldenRecord || !meeting) return;
    const edited = (editingTextByBlock[block.block_id] ?? "").trim();
    if (!edited || edited === block.text_scrubbed) return;

    const nextBlocks = blocks.map((b) =>
      b.block_id === block.block_id
        ? {
            ...b,
            text_scrubbed: edited,
            word_count: Math.max(1, edited.split(/\s+/).filter(Boolean).length),
          }
        : b
    );
    setBlocks(nextBlocks);
    recomputeClientRollup(nextBlocks);

    try {
      const resp = await updateDialogueBlockScoreOrGroup(
        idToken,
        meeting.meeting_id,
        block.block_id,
        { text_scrubbed: edited }
      );
      setLivePulseScore(resp.pulse_score);
      setLiveGroupScores(resp.group_scores);
      setStatusNotice(
        `Updated transcript text for ${block.block_id} (${resp.block.word_count} words).`
      );
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to save edited text"
      );
    }
  };

  const handleExplainRationale = async (blockId: string) => {
    if (!meeting) return;
    setDrawerXaiBlockId(blockId);
    setLoadingXaiBlockId(blockId);
    setErrorMessage(null);
    try {
      const explanation = await explainDialogueBlockRationale(
        idToken,
        meeting.meeting_id,
        blockId
      );
      setXaiByBlock((prev) => ({ ...prev, [blockId]: explanation }));
      setStatusNotice(
        `Generated Explainable AI (XAI) rubric attributions for ${blockId} with verified substring offsets.`
      );
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to generate XAI rationale"
      );
    } finally {
      setLoadingXaiBlockId(null);
    }
  };

  const handleRegenerateInsights = async () => {
    if (isLockedGoldenRecord || !meeting) return;
    setIsBusy(true);
    setErrorMessage(null);
    try {
      const res = await regenerateMeetingInsights(idToken, meeting.meeting_id);
      await loadWorkspace(meeting.meeting_id);
      setStatusNotice(
        `Regenerated MoM and Draft Risks using ${res.inference_mode} mode (${res.few_shot_count} Few-Shot exemplars).`
      );
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to regenerate insights"
      );
    } finally {
      setIsBusy(false);
    }
  };

  const handleCommitGoldenRecord = async () => {
    if (isLockedGoldenRecord || !meeting) return;
    setIsBusy(true);
    setErrorMessage(null);
    try {
      const allRiskIds = draftRisks.map((r) => r.risk_id);
      const approved = allRiskIds.filter((id) => approvedRiskIds.has(id));
      const dismissed = allRiskIds.filter((id) => !approvedRiskIds.has(id));

      const updatedMom: MoMSummary | null = meeting.mom_summary
        ? {
            ...meeting.mom_summary,
            summary: momSummaryText,
          }
        : {
            location: "Google Meet",
            title: meeting.title,
            agenda: [],
            topics_of_discussion: [],
            summary: momSummaryText,
            action_items: [],
            recommended_mitigations: [],
          };

      const res = await commitGoldenRecord(idToken, meeting.meeting_id, {
        approved_risk_ids: approved,
        dismissed_risk_ids: dismissed,
        mom_summary: updatedMom,
        block_updates: blocks.map((b) => ({
          block_id: b.block_id,
          sentiment_score: b.sentiment_score,
          group_name: b.group_name || b.group_id,
          is_human_overridden: b.is_human_overridden,
          text_scrubbed: editingTextByBlock[b.block_id] ?? b.text_scrubbed,
        })),
      });

      await loadWorkspace(meeting.meeting_id);
      setStatusNotice(
        `Golden Record committed at ${new Date(
          res.committed_at
        ).toLocaleTimeString()}. Ephemeral speaker accounts stripped, ${
          res.corrected_contexts_saved
        } Corrected Context 768-dim vectors saved, and ${
          res.bigquery_rows_streamed
        } rows streamed to BigQuery.`
      );
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to commit Golden Record"
      );
    } finally {
      setIsBusy(false);
    }
  };

  // Keyboard shortcuts (TRD Section 10.7: Alt+S split, [ / ] adjust slider by 5, Alt+E explain)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!activeBlockId || isLockedGoldenRecord) return;
      const activeBlock = blocks.find((b) => b.block_id === activeBlockId);
      if (!activeBlock) return;

      const tag = (e.target as HTMLElement)?.tagName;
      const isTypingInInput = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";

      if (e.altKey && e.key.toLowerCase() === "s") {
        e.preventDefault();
        void handleBubbleSplit(activeBlock);
      } else if (e.altKey && e.key.toLowerCase() === "e") {
        e.preventDefault();
        void handleExplainRationale(activeBlock.block_id);
      } else if (!isTypingInInput && (e.key === "[" || e.key === "]")) {
        e.preventDefault();
        const current = activeBlock.sentiment_score ?? 50;
        const delta = e.key === "]" ? 5 : -5;
        const nextVal = Math.max(0, Math.min(100, current + delta));
        handleSliderChange(activeBlock.block_id, nextVal);
        void handleSliderCommit(activeBlock.block_id, nextVal);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  });

  const overallStatus = getPulseScoreStatus(livePulseScore);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* Top Bar */}
      <header className="border-b border-slate-800 bg-slate-900/95 px-4 py-4 sm:px-6">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded border border-indigo-500/40 bg-indigo-950/70 px-2.5 py-0.5 font-mono text-xs font-semibold text-indigo-200">
                HITL ADJUDICATION
              </span>
              {meeting && (
                <span
                  className={`rounded border px-2.5 py-0.5 font-mono text-xs font-semibold ${
                    isLockedGoldenRecord
                      ? "border-emerald-500/50 bg-emerald-950/70 text-emerald-200"
                      : "border-amber-500/50 bg-amber-950/70 text-amber-200"
                  }`}
                >
                  {meeting.status}
                </span>
              )}
              <h1 className="text-lg font-bold text-white">
                {meeting ? meeting.title : "Transcript Adjudication & Score Calibration"}
              </h1>
            </div>
            <p className="mt-1 text-xs text-slate-300">
              Review DLP-scrubbed dialogue blocks, split multi-topic bubbles, assign session speaker groups, and calibrate 0 to 100 Pulse Scores.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {meetings.length > 0 && (
              <div className="flex items-center gap-2">
                <label
                  htmlFor="meeting-selector"
                  className="text-xs font-medium text-slate-300"
                >
                  Meeting:
                </label>
                <select
                  id="meeting-selector"
                  value={selectedMeetingId}
                  onChange={(e) => setSelectedMeetingId(e.target.value)}
                  className="min-h-[44px] rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-400"
                >
                  {meetings.map((m) => (
                    <option key={m.meeting_id} value={m.meeting_id}>
                      {m.title} ({m.status})
                    </option>
                  ))}
                </select>
              </div>
            )}

            <button
              type="button"
              onClick={onBackToWorkspace}
              className="inline-flex min-h-[44px] items-center justify-center rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-100 hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-400"
            >
              Return to Overview
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
        {/* Status and Error Banners */}
        {statusNotice && (
          <div
            role="status"
            aria-live="polite"
            className="flex items-center justify-between rounded-lg border border-emerald-500/50 bg-emerald-950/50 px-4 py-3 text-xs text-emerald-100"
          >
            <span>{statusNotice}</span>
            <button
              type="button"
              onClick={() => setStatusNotice(null)}
              className="ml-4 min-h-[44px] px-2 font-semibold text-emerald-300 hover:text-emerald-100 focus:outline-none focus:ring-2 focus:ring-emerald-400"
            >
              Dismiss
            </button>
          </div>
        )}

        {errorMessage && (
          <div
            role="alert"
            className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 rounded-xl border border-rose-500/40 bg-rose-950/40 p-4 text-xs text-rose-200"
          >
            <div>
              <p className="font-semibold text-rose-100">Adjudication Service Notice</p>
              <p className="mt-0.5 text-rose-300">{errorMessage}</p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => void loadWorkspace(selectedMeetingId || "mtg_alpha_adjudication")}
                className="min-h-[38px] rounded-lg border border-rose-500/50 bg-rose-900/60 px-3.5 py-1.5 font-semibold text-rose-100 hover:bg-rose-800 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400"
              >
                Retry
              </button>
              <button
                type="button"
                onClick={() => setErrorMessage(null)}
                className="min-h-[38px] rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 font-medium text-slate-300 hover:bg-slate-700 hover:text-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
              >
                Dismiss
              </button>
            </div>
          </div>
        )}

        {/* Loading / Empty / Workspace States (R-27) */}
        {isLoading ? (
          <div
            role="status"
            className="rounded-xl border border-slate-800 bg-slate-900 p-12 text-center"
          >
            <p className="text-sm font-semibold text-slate-200">
              Loading meeting transcript, DLP redaction flags, and baseline rubric scores...
            </p>
            <p className="mt-1 text-xs text-slate-400">
              Fetching dialogue blocks and project canonical group taxonomy.
            </p>
          </div>
        ) : !meeting ? (
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-12 text-center">
            <h2 className="text-base font-bold text-white">
              No Meeting Selected for Adjudication
            </h2>
            <p className="mt-2 text-xs text-slate-300">
              Dispatch a Google Meet bot from the Project Overview or select an ingested meeting to begin adjudication.
            </p>
            <button
              type="button"
              onClick={() => void loadWorkspace("mtg_alpha_adjudication")}
              className="mt-4 inline-flex min-h-[44px] items-center justify-center rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-400"
            >
              Load Sample Adjudication Meeting
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
            {/* LEFT PANE: Side-by-Side Transcript Editor, DLP Mask Visualizer, Bubble Split & 0-100 Slider (7 cols on lg) */}
            <section
              aria-label="Transcript Dialogue Blocks and Bubble Split Editor"
              className="space-y-4 lg:col-span-7"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-800 bg-slate-900 px-4 py-3">
                <div>
                  <h2 className="text-sm font-bold text-white">
                    Scrubbed Dialogue Blocks ({blocks.length})
                  </h2>
                  <p className="text-xs text-slate-300">
                    Keyboard shortcuts: <kbd className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[11px]">Alt+S</kbd> split at cursor,{" "}
                    <kbd className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[11px]">[</kbd> /{" "}
                    <kbd className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[11px]">]</kbd> adjust score by 5,{" "}
                    <kbd className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[11px]">Alt+E</kbd> explain rationale.
                  </p>
                </div>
                <span className="rounded border border-slate-700 bg-slate-950 px-2.5 py-1 font-mono text-xs text-slate-300">
                  Rollup Latency: {lastRollupDurationMs}ms (&lt;50ms SLA)
                </span>
              </div>

              {blocks.length === 0 ? (
                <div className="rounded-xl border border-slate-800 bg-slate-900 p-8 text-center">
                  <p className="text-sm font-semibold text-slate-200">
                    No Dialogue Blocks Ingested Yet
                  </p>
                  <p className="mt-1 text-xs text-slate-400">
                    This meeting has no scrubbed transcript blocks. Run post-meeting ingestion first.
                  </p>
                </div>
              ) : (
                blocks.map((block, idx) => {
                  const score = Math.round(block.sentiment_score ?? 50);
                  const statusStyle = getPulseScoreStatus(score);
                  const isSelected = activeBlockId === block.block_id;
                  const blockText =
                    editingTextByBlock[block.block_id] ?? block.text_scrubbed;
                  const splitIdx =
                    splitCursorByBlock[block.block_id] ??
                    Math.floor(blockText.length / 2);
                  const xaiData =
                    xaiByBlock[block.block_id] ||
                    (block.xai_attribution?.attributions?.length
                      ? {
                          meeting_id: meeting.meeting_id,
                          block_id: block.block_id,
                          scrubbed_text: block.text_scrubbed,
                          pulse_score: score,
                          rubric_breakdown: block.rubric_scores || {
                            emotional_valence: 12,
                            delivery_alignment: 12,
                            relationship_trust: 13,
                            momentum_commitment: 13,
                          },
                          attributions: block.xai_attribution.attributions,
                          computed_at: block.xai_attribution.computed_at,
                        }
                      : null);

                  const speakerKey =
                    block.ephemeral_speaker_account_id ||
                    block.speaker_alias ||
                    block.display_speaker_label ||
                    "Ephemeral Stripped";

                  return (
                    <article
                      key={block.block_id}
                      onClick={() => setActiveBlockId(block.block_id)}
                      className={`rounded-xl border p-4 transition-colors ${
                        isSelected
                          ? "border-indigo-500 bg-slate-900"
                          : "border-slate-800 bg-slate-900/80 hover:border-slate-700"
                      }`}
                    >
                      {/* Block Header: Sequence, Speaker Alias, DLP Flags, Split Badge */}
                      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-xs font-semibold text-slate-200">
                            #{idx + 1} ({block.block_id})
                          </span>
                          {block.is_split && (
                            <span className="rounded border border-indigo-500/40 bg-indigo-950/60 px-2 py-0.5 font-mono text-[11px] text-indigo-200">
                              Split Child {block.parent_block_id ? `of ${block.parent_block_id}` : ""}
                            </span>
                          )}
                          {block.is_human_overridden && (
                            <span className="rounded border border-emerald-500/40 bg-emerald-950/60 px-2 py-0.5 font-mono text-[11px] text-emerald-200">
                              Human Calibrated
                            </span>
                          )}
                          <span className="text-xs font-semibold text-white">
                            {block.display_speaker_label ||
                              block.speaker_alias ||
                              "Speaker Identity Stripped (Golden Record)"}
                          </span>
                          {block.ephemeral_speaker_account_id && (
                            <span className="font-mono text-[11px] text-slate-400">
                              [{block.ephemeral_speaker_account_id}]
                            </span>
                          )}
                        </div>

                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-xs text-slate-300">
                            {block.word_count} words
                          </span>
                          {block.dlp_redaction_flags &&
                            block.dlp_redaction_flags.length > 0 && (
                              <span
                                className="rounded border border-amber-500/50 bg-amber-950/70 px-2 py-0.5 font-mono text-[11px] font-semibold text-amber-200"
                                title={`Redacted InfoTypes: ${block.dlp_redaction_flags.join(", ")}`}
                              >
                                DLP Redacted ({block.dlp_redaction_flags.join(", ")})
                              </span>
                            )}
                        </div>
                      </div>

                      {/* Side-by-Side Transcript Editor & DLP / XAI Visualizer */}
                      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
                        {/* Left column inside card: Interactive Transcript & Split Cursor Editor */}
                        <div>
                          <label
                            htmlFor={`editor-${block.block_id}`}
                            className="block text-xs font-semibold text-slate-300"
                          >
                            Transcript Editor (Click or select cursor index to Bubble Split)
                          </label>
                          <textarea
                            id={`editor-${block.block_id}`}
                            ref={(el) => {
                              textareaRefs.current[block.block_id] = el;
                            }}
                            rows={4}
                            disabled={isLockedGoldenRecord}
                            value={blockText}
                            onChange={(e) => {
                              const val = e.target.value;
                              setEditingTextByBlock((prev) => ({
                                ...prev,
                                [block.block_id]: val,
                              }));
                            }}
                            onSelect={(e) => {
                              const target = e.currentTarget;
                              if (
                                target.selectionStart > 0 &&
                                target.selectionStart < blockText.length
                              ) {
                                setSplitCursorByBlock((prev) => ({
                                  ...prev,
                                  [block.block_id]: target.selectionStart,
                                }));
                              }
                            }}
                            onBlur={() => void handleSaveBlockText(block)}
                            className="mt-1.5 w-full rounded-lg border border-slate-700 bg-slate-950 p-2.5 text-xs leading-relaxed text-slate-100 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-400 disabled:opacity-60"
                          />
                          <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                            <span className="font-mono text-[11px] text-slate-300">
                              Split Cursor Offset: char {splitIdx} of {blockText.length}
                            </span>
                            <button
                              type="button"
                              disabled={isLockedGoldenRecord || isBusy}
                              onClick={() => void handleBubbleSplit(block)}
                              className="inline-flex min-h-[44px] items-center justify-center rounded-lg border border-indigo-500/50 bg-indigo-950/70 px-3 py-1.5 text-xs font-semibold text-indigo-200 hover:bg-indigo-900/80 focus:outline-none focus:ring-2 focus:ring-indigo-400 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              Split Bubble at Cursor ({splitIdx})
                            </button>
                          </div>
                        </div>

                        {/* Right column inside card: DLP Mask & Verbatim XAI Visualizer */}
                        <div className="flex flex-col justify-between rounded-lg border border-slate-800 bg-slate-950/90 p-3">
                          <div>
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-semibold text-slate-300">
                                DLP Mask &amp; Verbatim Attribution View
                              </span>
                              <button
                                type="button"
                                disabled={loadingXaiBlockId === block.block_id}
                                onClick={() =>
                                  void handleExplainRationale(block.block_id)
                                }
                                className="inline-flex min-h-[44px] items-center justify-center rounded-lg border border-slate-700 bg-slate-800 px-3 py-1 text-xs font-semibold text-slate-200 hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-400"
                              >
                                {loadingXaiBlockId === block.block_id
                                  ? "Analyzing XAI..."
                                  : "Explain Rationale"}
                              </button>
                            </div>
                            <p className="mt-2 text-xs leading-relaxed text-slate-100">
                              {renderDlpAndXaiHighlightedText(
                                block.text_scrubbed,
                                xaiData?.attributions
                              )}
                            </p>
                          </div>

                          {/* Split Preview */}
                          {!isLockedGoldenRecord &&
                            splitIdx > 0 &&
                            splitIdx < blockText.length && (
                              <div className="mt-3 border-t border-slate-800 pt-2 text-[11px] text-slate-300">
                                <span className="font-semibold text-indigo-300">
                                  Split Preview:
                                </span>{" "}
                                &ldquo;{blockText.slice(0, Math.min(28, splitIdx))}
                                ...&rdquo;{" "}
                                <span className="font-mono font-bold text-amber-300">
                                  ||
                                </span>{" "}
                                &ldquo;
                                {blockText.slice(
                                  splitIdx,
                                  Math.min(blockText.length, splitIdx + 28)
                                )}
                                ...&rdquo;
                              </div>
                            )}
                        </div>
                      </div>

                      {/* Group Assignment & 0-100 Pulse Score Slider Controls */}
                      <div className="mt-4 grid grid-cols-1 gap-4 border-t border-slate-800 pt-4 sm:grid-cols-2">
                        {/* In-Session Speaker-to-Group Mapping */}
                        <div>
                          <div className="flex items-center justify-between">
                            <label
                              htmlFor={`group-select-${block.block_id}`}
                              className="text-xs font-semibold text-slate-300"
                            >
                              Canonical Group Assignment
                            </label>
                            <button
                              type="button"
                              disabled={isLockedGoldenRecord}
                              onClick={() => void handleTogglePinBlock(block)}
                              className={`min-h-[44px] rounded px-2 py-1 font-mono text-[11px] font-semibold focus:outline-none focus:ring-2 focus:ring-indigo-400 ${
                                block.is_pinned
                                  ? "border border-amber-500/50 bg-amber-950/60 text-amber-200"
                                  : "border border-slate-700 bg-slate-800 text-slate-300"
                              }`}
                              title="Pinned blocks keep their group when session speaker mapping changes"
                            >
                              {block.is_pinned
                                ? "Pinned (Single Block)"
                                : "Auto-Sync Speaker"}
                            </button>
                          </div>
                          <select
                            id={`group-select-${block.block_id}`}
                            disabled={isLockedGoldenRecord}
                            value={
                              block.group_name ||
                              block.group_id ||
                              canonicalGroups[0]
                            }
                            onChange={(e) =>
                              void handleSessionSpeakerGroupChange(
                                block,
                                e.target.value,
                                !block.is_pinned
                              )
                            }
                            className="mt-1.5 min-h-[44px] w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-400 disabled:opacity-60"
                          >
                            {canonicalGroups.map((grp) => (
                              <option key={grp} value={grp}>
                                {grp}
                              </option>
                            ))}
                          </select>
                          <p className="mt-1 text-[11px] text-slate-400">
                            {block.is_pinned
                              ? "Pinned: only this dialogue block updates."
                              : `Session Auto-Tag: updates all unpinned blocks from ${speakerKey}.`}
                          </p>
                        </div>

                        {/* 0-100 Sentiment Pulse Slider */}
                        <div>
                          <div className="flex items-center justify-between">
                            <label
                              htmlFor={`slider-${block.block_id}`}
                              className="text-xs font-semibold text-slate-300"
                            >
                              Pulse Score Calibration (0 to 100)
                            </label>
                            <span
                              className={`rounded border px-2 py-0.5 font-mono text-xs font-bold ${statusStyle.badgeClass}`}
                            >
                              {score}/100 ({statusStyle.label})
                            </span>
                          </div>
                          <div className="mt-2 flex items-center gap-3">
                            <span className="font-mono text-xs text-slate-400">
                              0
                            </span>
                            <input
                              id={`slider-${block.block_id}`}
                              type="range"
                              min={0}
                              max={100}
                              step={1}
                              disabled={isLockedGoldenRecord}
                              value={score}
                              aria-label={`Pulse Score slider for block ${block.block_id}`}
                              onChange={(e) =>
                                handleSliderChange(
                                  block.block_id,
                                  Number(e.target.value)
                                )
                              }
                              onMouseUp={(e) =>
                                void handleSliderCommit(
                                  block.block_id,
                                  Number(
                                    (e.currentTarget as HTMLInputElement).value
                                  )
                                )
                              }
                              onKeyUp={(e) =>
                                void handleSliderCommit(
                                  block.block_id,
                                  Number(
                                    (e.currentTarget as HTMLInputElement).value
                                  )
                                )
                              }
                              className="h-2.5 flex-1 cursor-pointer appearance-none rounded-lg bg-slate-800 accent-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-400"
                            />
                            <span className="font-mono text-xs text-slate-400">
                              100
                            </span>
                          </div>
                          <div className="mt-1 flex items-center justify-between text-[11px] text-slate-400">
                            <span>
                              AI Initial Score:{" "}
                              {block.ai_initial_score ?? score}/100
                            </span>
                            {block.ai_confidence != null && (
                              <span>
                                Confidence:{" "}
                                {Math.round(block.ai_confidence * 100)}%
                              </span>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Inline XAI Drawer when Explain Rationale is active */}
                      {xaiData && (
                        <div className="mt-4 rounded-lg border border-indigo-500/40 bg-slate-950 p-3">
                          <h3 className="text-xs font-bold text-indigo-200">
                            4-Dimension Rubric Breakdown &amp; Verified Substring Attributions
                          </h3>
                          <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
                            {(
                              [
                                [
                                  "Emotional Valence",
                                  xaiData.rubric_breakdown.emotional_valence,
                                ],
                                [
                                  "Delivery Alignment",
                                  xaiData.rubric_breakdown.delivery_alignment,
                                ],
                                [
                                  "Relationship Trust",
                                  xaiData.rubric_breakdown.relationship_trust,
                                ],
                                [
                                  "Momentum Commitment",
                                  xaiData.rubric_breakdown.momentum_commitment,
                                ],
                              ] as Array<[string, number]>
                            ).map(([dimLabel, dimVal]) => (
                              <div
                                key={dimLabel}
                                className="rounded border border-slate-800 bg-slate-900 p-2"
                              >
                                <div className="text-[11px] text-slate-300">
                                  {dimLabel}
                                </div>
                                <div className="mt-0.5 font-mono text-xs font-bold text-white">
                                  {dimVal}/25
                                </div>
                              </div>
                            ))}
                          </div>
                          {xaiData.attributions.length > 0 && (
                            <ul className="mt-2 space-y-1.5 text-xs">
                              {xaiData.attributions.map((attr, aIdx) => (
                                <li
                                  key={aIdx}
                                  className="flex flex-wrap items-baseline justify-between gap-2 rounded bg-slate-900 px-2.5 py-1.5"
                                >
                                  <div>
                                    <span className="font-mono text-[11px] text-slate-400">
                                      [{attr.start_char}:{attr.end_char}]
                                    </span>{" "}
                                    <span className="font-semibold text-white">
                                      &ldquo;{attr.verbatim_phrase}&rdquo;
                                    </span>{" "}
                                    <span className="text-slate-300">
                                      ({attr.rationale})
                                    </span>
                                  </div>
                                  <span
                                    className={`font-mono text-xs font-bold ${
                                      attr.attribution_weight >= 0
                                        ? "text-emerald-300"
                                        : "text-rose-300"
                                    }`}
                                  >
                                    {attr.attribution_weight >= 0 ? "+" : ""}
                                    {attr.attribution_weight} ({attr.rubric_dimension})
                                  </span>
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      )}
                    </article>
                  );
                })
              )}
            </section>

            {/* RIGHT PANE: Deterministic Group & Meeting Rollups, Session Speaker Map, Draft Risks & Golden Record Commit (5 cols on lg) */}
            <aside
              aria-label="Live Deterministic Score Rollups and Golden Record Commit"
              className="space-y-6 lg:col-span-5"
            >
              {/* Overall Meeting Pulse Score Rollup Card */}
              <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-sm font-bold text-white">
                      Overall Meeting Pulse Score
                    </h2>
                    <p className="text-xs text-slate-300">
                      Arithmetic mean across active canonical groups
                    </p>
                  </div>
                  <div
                    className={`rounded-lg border px-3 py-1.5 font-mono text-base font-bold ${overallStatus.badgeClass}`}
                  >
                    {livePulseScore}/100
                  </div>
                </div>

                <div className="mt-3 h-2.5 w-full overflow-hidden rounded-full bg-slate-800">
                  <div
                    className={`h-full transition-all duration-75 ${overallStatus.barClass}`}
                    style={{
                      width: `${Math.max(0, Math.min(100, livePulseScore))}%`,
                    }}
                  />
                </div>

                {/* Group Pulse Scores (Word-Count Weighted) */}
                <div className="mt-5 space-y-3 border-t border-slate-800 pt-4">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                    Word-Count Weighted Group Pulse Scores
                  </h3>
                  {Object.entries(liveGroupScores).map(([grpName, metric]) => {
                    const grpStatus = getPulseScoreStatus(metric.pulse_score);
                    return (
                      <div
                        key={grpName}
                        className="rounded-lg border border-slate-800 bg-slate-950 p-3"
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <span className="text-xs font-semibold text-white">
                              {grpName}
                            </span>
                            <span className="ml-2 font-mono text-[11px] text-slate-400">
                              ({metric.block_count} blocks)
                            </span>
                          </div>
                          <span
                            className={`rounded border px-2 py-0.5 font-mono text-xs font-bold ${grpStatus.badgeClass}`}
                          >
                            {metric.pulse_score}/100
                          </span>
                        </div>
                        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                          <div
                            className={`h-full ${grpStatus.barClass}`}
                            style={{
                              width: `${Math.max(
                                0,
                                Math.min(100, metric.pulse_score)
                              )}%`,
                            }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Ephemeral Session Speaker-to-Group Map */}
              <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                <h2 className="text-sm font-bold text-white">
                  In-Session Ephemeral Speaker Map
                </h2>
                <p className="mt-1 text-xs text-slate-300">
                  Maps transcript speaker identifiers to canonical Groups only during active adjudication. Permanently stripped upon Golden Record commit.
                </p>

                {isLockedGoldenRecord ? (
                  <div className="mt-3 rounded-lg border border-emerald-500/40 bg-emerald-950/40 p-3 text-xs text-emerald-200">
                    Ephemeral speaker mappings have been permanently stripped for privacy preservation (Golden Record locked).
                  </div>
                ) : Object.keys(ephemeralSpeakerMap).length === 0 ? (
                  <p className="mt-3 text-xs text-slate-400">
                    Assign a Group on any dialogue block to populate the session speaker map.
                  </p>
                ) : (
                  <div className="mt-3 space-y-2">
                    {Object.entries(ephemeralSpeakerMap).map(
                      ([spkId, mappedGroup]) => (
                        <div
                          key={spkId}
                          className="flex items-center justify-between gap-2 rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-xs"
                        >
                          <span className="font-mono text-slate-200">
                            {spkId}
                          </span>
                          <select
                            aria-label={`Session group for speaker ${spkId}`}
                            value={mappedGroup}
                            onChange={(e) => {
                              const sampleBlk = blocks.find(
                                (b) =>
                                  b.ephemeral_speaker_account_id === spkId ||
                                  b.speaker_alias === spkId
                              );
                              if (sampleBlk) {
                                void handleSessionSpeakerGroupChange(
                                  sampleBlk,
                                  e.target.value,
                                  true
                                );
                              }
                            }}
                            className="min-h-[44px] rounded border border-slate-700 bg-slate-900 px-2.5 py-1 text-xs text-slate-100 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-400"
                          >
                            {canonicalGroups.map((g) => (
                              <option key={g} value={g}>
                                {g}
                              </option>
                            ))}
                          </select>
                        </div>
                      )
                    )}
                  </div>
                )}
              </div>

              {/* Minutes of Meeting (MoM) & Draft Risk Approval */}
              <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-4">
                <div>
                  <label
                    htmlFor="mom-summary-textarea"
                    className="block text-sm font-bold text-white"
                  >
                    Minutes of Meeting (MoM) Executive Summary
                  </label>
                  <textarea
                    id="mom-summary-textarea"
                    rows={3}
                    disabled={isLockedGoldenRecord}
                    value={momSummaryText}
                    onChange={(e) => setMomSummaryText(e.target.value)}
                    placeholder="Enter or refine the post-meeting executive summary..."
                    className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 p-2.5 text-xs text-slate-100 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-400 disabled:opacity-60"
                  />
                </div>

                <div className="border-t border-slate-800 pt-4">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                    Draft Risk Candidates ({draftRisks.length})
                  </h3>
                  <p className="mt-1 text-xs text-slate-400">
                    Checked risks promote from DRAFT_PENDING_ADJUDICATION to OPEN upon Golden Record commit.
                  </p>
                  {draftRisks.length === 0 ? (
                    <p className="mt-2 text-xs text-slate-400">
                      No draft risks flagged for this meeting.
                    </p>
                  ) : (
                    <div className="mt-3 space-y-2">
                      {draftRisks.map((risk) => {
                        const checked = approvedRiskIds.has(risk.risk_id);
                        return (
                          <label
                            key={risk.risk_id}
                            className="flex cursor-pointer items-start gap-3 rounded-lg border border-slate-800 bg-slate-950 p-3 text-xs hover:border-slate-700"
                          >
                            <input
                              type="checkbox"
                              disabled={isLockedGoldenRecord}
                              checked={checked}
                              onChange={(e) => {
                                const next = new Set(approvedRiskIds);
                                if (e.target.checked) {
                                  next.add(risk.risk_id);
                                } else {
                                  next.delete(risk.risk_id);
                                }
                                setApprovedRiskIds(next);
                              }}
                              className="mt-1 h-4 w-4 rounded border-slate-600 bg-slate-900 text-indigo-600 focus:ring-indigo-500"
                            />
                            <div className="flex-1">
                              <div className="flex flex-wrap items-center justify-between gap-1">
                                <span className="font-semibold text-white">
                                  {risk.title}
                                </span>
                                <span className="rounded bg-rose-950/80 px-2 py-0.5 font-mono text-[11px] font-semibold text-rose-200">
                                  Severity {risk.severity_score} ({risk.impact}x
                                  {risk.probability})
                                </span>
                              </div>
                              <p className="mt-1 text-slate-300">
                                {risk.description}
                              </p>
                              <div className="mt-1 font-mono text-[11px] text-slate-400">
                                {risk.category} • Status: {risk.status}
                              </div>
                            </div>
                          </label>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Primary Actions: Regenerate Risks & Save Golden Record */}
                <div className="flex flex-col gap-3 border-t border-slate-800 pt-4 sm:flex-row">
                  <button
                    type="button"
                    disabled={isLockedGoldenRecord || isBusy}
                    onClick={() => void handleRegenerateInsights()}
                    className="inline-flex min-h-[44px] flex-1 items-center justify-center rounded-lg border border-slate-700 bg-slate-800 px-4 py-2.5 text-xs font-semibold text-slate-100 hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-400 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Regenerate Risks &amp; MoM
                  </button>
                  <button
                    type="button"
                    disabled={isLockedGoldenRecord || isBusy}
                    onClick={() => void handleCommitGoldenRecord()}
                    className="inline-flex min-h-[44px] flex-1 items-center justify-center rounded-lg bg-emerald-600 px-4 py-2.5 text-xs font-semibold text-white hover:bg-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {isLockedGoldenRecord
                      ? "Golden Record Locked"
                      : isBusy
                        ? "Committing..."
                        : "Commit Golden Record"}
                  </button>
                </div>
              </div>
            </aside>
          </div>
        )}
      </main>

      {drawerXaiBlockId && (
        <XaiRationaleDrawer
          isOpen={!!drawerXaiBlockId}
          onClose={() => setDrawerXaiBlockId(null)}
          blockId={drawerXaiBlockId}
          blockText={
            editingTextByBlock[drawerXaiBlockId] ??
            blocks.find((b) => b.block_id === drawerXaiBlockId)?.text_scrubbed ??
            ""
          }
          pulseScore={
            blocks.find((b) => b.block_id === drawerXaiBlockId)?.sentiment_score
          }
          rubricScores={
            xaiByBlock[drawerXaiBlockId]?.rubric_breakdown
          }
          attributions={
            xaiByBlock[drawerXaiBlockId]?.attributions
          }
          computedAt={xaiByBlock[drawerXaiBlockId]?.computed_at}
          isLoading={loadingXaiBlockId === drawerXaiBlockId}
          onRefreshXai={() => void handleExplainRationale(drawerXaiBlockId)}
        />
      )}
    </div>
  );
};

