import React, { useEffect, useState } from "react";
import { RubricBreakdown, ValidatedSpanAttribution } from "../types/domain";

export interface XaiRationaleDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  blockText: string;
  blockId?: string;
  pulseScore?: number | null;
  rubricScores?: RubricBreakdown | null;
  attributions?: ValidatedSpanAttribution[];
  computedAt?: string | null;
  isLoading?: boolean;
  onRefreshXai?: () => void;
}

export const XaiRationaleDrawer: React.FC<XaiRationaleDrawerProps> = ({
  isOpen,
  onClose,
  blockText,
  blockId,
  pulseScore,
  rubricScores,
  attributions = [],
  computedAt,
  isLoading = false,
  onRefreshXai,
}) => {
  const [selectedAttrIndex, setSelectedAttrIndex] = useState<number | null>(
    null
  );

  // Close drawer on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const validAttributions = [...attributions]
    .filter(
      (a) =>
        a.start_char >= 0 &&
        a.end_char <= blockText.length &&
        a.start_char < a.end_char
    )
    .sort((a, b) => a.start_char - b.start_char);

  const ev = rubricScores?.emotional_valence ?? 12;
  const da = rubricScores?.delivery_alignment ?? 12;
  const rt = rubricScores?.relationship_trust ?? 13;
  const mc = rubricScores?.momentum_commitment ?? 13;
  const totalScore =
    pulseScore !== null && pulseScore !== undefined
      ? Math.round(pulseScore)
      : ev + da + rt + mc;

  // Render text with interactive verbatim span highlights
  const renderHighlightedText = () => {
    if (!blockText) {
      return (
        <span className="italic text-slate-400">
          No dialogue text available.
        </span>
      );
    }

    if (validAttributions.length === 0) {
      return <span className="text-slate-100">{blockText}</span>;
    }

    const segments: React.ReactNode[] = [];
    let cursor = 0;

    validAttributions.forEach((attr, idx) => {
      if (attr.start_char < cursor) return;

      if (attr.start_char > cursor) {
        segments.push(
          <span key={`plain-${idx}`} className="text-slate-200">
            {blockText.slice(cursor, attr.start_char)}
          </span>
        );
      }

      const isPositive = attr.attribution_weight >= 0;
      const isSelected = selectedAttrIndex === idx;

      segments.push(
        <mark
          key={`span-${idx}`}
          onClick={() => setSelectedAttrIndex(isSelected ? null : idx)}
          title={`${attr.rubric_dimension} (${
            attr.attribution_weight >= 0 ? "+" : ""
          }${attr.attribution_weight.toFixed(2)}): ${attr.rationale}`}
          className={`cursor-pointer rounded px-1.5 py-0.5 font-medium transition-all ${
            isPositive
              ? isSelected
                ? "bg-emerald-600 text-white ring-2 ring-emerald-300"
                : "bg-emerald-950/90 text-emerald-200 underline decoration-emerald-400 decoration-2 hover:bg-emerald-900"
              : isSelected
              ? "bg-rose-600 text-white ring-2 ring-rose-300"
              : "bg-rose-950/90 text-rose-200 underline decoration-rose-400 decoration-2 hover:bg-rose-900"
          }`}
        >
          {blockText.slice(attr.start_char, attr.end_char)}
          <span className="ml-1 rounded bg-black/40 px-1 text-[10px] font-mono">
            {attr.attribution_weight >= 0 ? "+" : ""}
            {attr.attribution_weight.toFixed(2)}
          </span>
        </mark>
      );
      cursor = attr.end_char;
    });

    if (cursor < blockText.length) {
      segments.push(
        <span key="plain-tail" className="text-slate-200">
          {blockText.slice(cursor)}
        </span>
      );
    }

    return segments;
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="xai-drawer-title"
      className="fixed inset-0 z-50 flex justify-end bg-black/75 backdrop-blur-sm transition-opacity"
      onClick={onClose}
    >
      <div
        className="flex h-full w-full max-w-2xl flex-col bg-slate-900 shadow-2xl border-l border-slate-800 text-slate-100 sm:max-w-xl md:max-w-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-5 bg-slate-950/90">
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded bg-indigo-500/20 px-2 py-0.5 font-mono text-xs font-semibold text-indigo-300 border border-indigo-500/30">
                XAI Rationale
              </span>
              {blockId && (
                <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-300">
                  {blockId}
                </span>
              )}
            </div>
            <h2
              id="xai-drawer-title"
              className="mt-1 text-base font-bold text-white tracking-tight"
            >
              Explainable AI Rubric &amp; Verbatim Attributions
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close XAI drawer"
            className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg border border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
          >
            ✕
          </button>
        </div>

        {/* Scrollable Content */}
        <div className="flex-1 space-y-6 overflow-y-auto px-6 py-6">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-16 space-y-3">
              <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-500 border-t-transparent" />
              <p className="text-xs text-slate-300">
                Extracting verbatim substring attributions with Gemini 2.5 Flash...
              </p>
            </div>
          ) : (
            <>
              {/* Overall Pulse Badge & Metadata */}
              <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-800 bg-slate-950 p-4">
                <div>
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Net Pulse Score
                  </span>
                  <div className="flex items-baseline gap-2 mt-1">
                    <span className="text-2xl font-black text-white">
                      {totalScore}
                    </span>
                    <span className="text-xs text-slate-400">/ 100</span>
                    <span
                      className={`ml-2 rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                        totalScore >= 70
                          ? "bg-emerald-950 text-emerald-300 border border-emerald-500/40"
                          : totalScore >= 40
                          ? "bg-amber-950 text-amber-300 border border-amber-500/40"
                          : "bg-rose-950 text-rose-300 border border-rose-500/40"
                      }`}
                    >
                      {totalScore >= 70
                        ? "Positive / Aligned"
                        : totalScore >= 40
                        ? "Guarded / Neutral"
                        : "Critical / Negative"}
                    </span>
                  </div>
                </div>

                {onRefreshXai && (
                  <button
                    type="button"
                    onClick={onRefreshXai}
                    className="flex min-h-[44px] items-center gap-1.5 rounded-lg border border-indigo-500/40 bg-indigo-950/40 px-3 py-2 text-xs font-semibold text-indigo-200 hover:bg-indigo-900/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
                  >
                    <span>↻</span> Re-Analyze
                  </button>
                )}
              </div>

              {/* 4-Bar Rubric Breakdown */}
              <div className="rounded-xl border border-slate-800 bg-slate-950 p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                    4-Dimension Sentiment Rubric (0–25 each)
                  </h3>
                  <span className="text-xs font-mono text-slate-400">
                    Sum = {ev + da + rt + mc} / 100
                  </span>
                </div>

                <div className="space-y-3">
                  {/* Emotional Valence */}
                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="font-semibold text-sky-300">
                        Emotional Valence
                      </span>
                      <span className="font-mono text-slate-200">{ev} / 25</span>
                    </div>
                    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
                      <div
                        className="h-full bg-sky-500 transition-all duration-300"
                        style={{ width: `${(ev / 25) * 100}%` }}
                      />
                    </div>
                  </div>

                  {/* Delivery Alignment */}
                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="font-semibold text-emerald-300">
                        Delivery Alignment
                      </span>
                      <span className="font-mono text-slate-200">{da} / 25</span>
                    </div>
                    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
                      <div
                        className="h-full bg-emerald-500 transition-all duration-300"
                        style={{ width: `${(da / 25) * 100}%` }}
                      />
                    </div>
                  </div>

                  {/* Relationship Trust */}
                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="font-semibold text-purple-300">
                        Relationship Trust
                      </span>
                      <span className="font-mono text-slate-200">{rt} / 25</span>
                    </div>
                    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
                      <div
                        className="h-full bg-purple-500 transition-all duration-300"
                        style={{ width: `${(rt / 25) * 100}%` }}
                      />
                    </div>
                  </div>

                  {/* Momentum & Commitment */}
                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="font-semibold text-amber-300">
                        Momentum &amp; Commitment
                      </span>
                      <span className="font-mono text-slate-200">{mc} / 25</span>
                    </div>
                    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
                      <div
                        className="h-full bg-amber-500 transition-all duration-300"
                        style={{ width: `${(mc / 25) * 100}%` }}
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* Verbatim Substring Highlighter */}
              <div className="rounded-xl border border-slate-800 bg-slate-950 p-5 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                    Verbatim Substring Attribution Span Highlighter
                  </h3>
                  <span className="text-[11px] text-slate-400">
                    Click span to highlight rationale
                  </span>
                </div>
                <div className="rounded-lg border border-slate-800 bg-slate-900 p-4 text-sm leading-relaxed whitespace-pre-wrap select-text">
                  {renderHighlightedText()}
                </div>
              </div>

              {/* Attribution Details List */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                    Verified Attributions ({validAttributions.length})
                  </h3>
                  <div className="flex items-center gap-3 text-[11px]">
                    <span className="flex items-center gap-1 text-emerald-300">
                      <span className="inline-block h-2 w-2 rounded-full bg-emerald-400" />
                      Positive
                    </span>
                    <span className="flex items-center gap-1 text-rose-300">
                      <span className="inline-block h-2 w-2 rounded-full bg-rose-400" />
                      Negative
                    </span>
                  </div>
                </div>

                {validAttributions.length === 0 ? (
                  <div className="rounded-xl border border-slate-800 bg-slate-950 p-6 text-center text-xs text-slate-400">
                    No span attributions generated for this dialogue block.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {validAttributions.map((attr, idx) => {
                      const isPositive = attr.attribution_weight >= 0;
                      const isSelected = selectedAttrIndex === idx;

                      return (
                        <div
                          key={`attr-card-${idx}`}
                          onClick={() =>
                            setSelectedAttrIndex(isSelected ? null : idx)
                          }
                          className={`cursor-pointer rounded-xl border p-4 transition-all ${
                            isSelected
                              ? "border-indigo-500 bg-indigo-950/30 ring-1 ring-indigo-400"
                              : "border-slate-800 bg-slate-950 hover:border-slate-700 hover:bg-slate-900/60"
                          }`}
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span
                              className={`rounded-full px-2.5 py-0.5 text-xs font-bold font-mono ${
                                isPositive
                                  ? "bg-emerald-950 text-emerald-300 border border-emerald-500/40"
                                  : "bg-rose-950 text-rose-300 border border-rose-500/40"
                              }`}
                            >
                              {attr.attribution_weight >= 0 ? "+" : ""}
                              {attr.attribution_weight.toFixed(2)} Weight
                            </span>
                            <span className="rounded bg-slate-800 px-2 py-0.5 text-[11px] font-medium text-slate-300">
                              {attr.rubric_dimension}
                            </span>
                            <span className="text-[11px] font-mono text-slate-400">
                              chars [{attr.start_char}:{attr.end_char}]
                            </span>
                          </div>

                          <blockquote className="mt-2 text-xs font-semibold text-slate-200 border-l-2 border-slate-700 pl-2 italic">
                            &ldquo;{attr.verbatim_phrase}&rdquo;
                          </blockquote>

                          <p className="mt-2 text-xs text-slate-300">
                            {attr.rationale}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {computedAt && (
                <div className="text-right text-[11px] text-slate-400">
                  Attributions validated at {new Date(computedAt).toLocaleString()}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-slate-800 bg-slate-950/90 px-6 py-4 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="min-h-[44px] rounded-lg bg-slate-800 px-5 py-2 text-xs font-semibold text-slate-100 hover:bg-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
          >
            Close Drawer
          </button>
        </div>
      </div>
    </div>
  );
};
