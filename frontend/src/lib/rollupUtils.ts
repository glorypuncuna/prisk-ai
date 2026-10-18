export interface RollupBlockInput {
  block_id: string;
  group_name?: string | null;
  group_id?: string | null;
  sentiment_score?: number | null;
  word_count?: number | null;
  text_scrubbed: string;
}

export interface GroupPulseRollupMetric {
  pulse_score: number;
  block_count: number;
  top_liked_words: string[];
  top_disliked_words: string[];
}

export interface DeterministicRollupResult {
  overallPulseScore: number;
  groupScores: Record<string, GroupPulseRollupMetric>;
}

/**
 * Deterministically compute word-count-weighted Group Pulse Scores and arithmetic mean Overall Meeting Pulse Score (<50ms).
 */
export function calculateDeterministicRollups(
  blocks: RollupBlockInput[],
  existingGroupScores?: Record<string, Partial<GroupPulseRollupMetric>>
): DeterministicRollupResult {
  const existingMap = existingGroupScores || {};
  const weightedSums: Record<string, number> = {};
  const totalWeights: Record<string, number> = {};
  const counts: Record<string, number> = {};

  for (const blk of blocks) {
    const groupName = blk.group_name || blk.group_id || "INTERNAL";
    const score =
      typeof blk.sentiment_score === "number" && !Number.isNaN(blk.sentiment_score)
        ? blk.sentiment_score
        : 50.0;
    const rawWords = (blk.text_scrubbed || "")
      .trim()
      .split(/\s+/)
      .filter(Boolean).length;
    const weight = Math.max(1, blk.word_count && blk.word_count > 0 ? blk.word_count : rawWords);

    weightedSums[groupName] = (weightedSums[groupName] || 0) + score * weight;
    totalWeights[groupName] = (totalWeights[groupName] || 0) + weight;
    counts[groupName] = (counts[groupName] || 0) + 1;
  }

  const groupScores: Record<string, GroupPulseRollupMetric> = {};
  const activeGroups = Object.keys(weightedSums);

  for (const grp of activeGroups) {
    const w = Math.max(1, totalWeights[grp] || 1);
    const pulse = Math.round((weightedSums[grp] / w) * 10) / 10;
    const prev = existingMap[grp] || {};
    groupScores[grp] = {
      pulse_score: pulse,
      block_count: counts[grp] || 1,
      top_liked_words: Array.isArray(prev.top_liked_words) ? prev.top_liked_words : [],
      top_disliked_words: Array.isArray(prev.top_disliked_words) ? prev.top_disliked_words : [],
    };
  }

  let overallPulseScore = 50.0;
  if (activeGroups.length > 0) {
    const sumGroupPulses = activeGroups.reduce(
      (acc, g) => acc + groupScores[g].pulse_score,
      0
    );
    overallPulseScore = Math.round((sumGroupPulses / activeGroups.length) * 10) / 10;
  }

  return {
    overallPulseScore,
    groupScores,
  };
}

/**
 * Perform an immediate client-side Bubble Split inheriting parent score, rubric, and group assignment.
 */
export function splitDialogueBlockClient<
  T extends {
    block_id: string;
    sequence_index: number;
    parent_block_id?: string | null;
    start_time_sec?: number | null;
    end_time_sec?: number | null;
    text_scrubbed: string;
    word_count: number;
    is_split?: boolean;
  }
>(blocks: T[], targetBlockId: string, splitCharIndex: number): T[] {
  const targetIndex = blocks.findIndex((b) => b.block_id === targetBlockId);
  if (targetIndex === -1) return blocks;

  const parent = blocks[targetIndex];
  const fullText = parent.text_scrubbed || "";
  if (splitCharIndex <= 0 || splitCharIndex >= fullText.length) {
    return blocks;
  }

  const leftText = fullText.slice(0, splitCharIndex).trim();
  const rightText = fullText.slice(splitCharIndex).trim();
  if (!leftText || !rightText) {
    return blocks;
  }

  const startSec = parent.start_time_sec ?? 0;
  const endSec = parent.end_time_sec ?? startSec + 6;
  const ratio = splitCharIndex / Math.max(1, fullText.length);
  const midSec = Math.round((startSec + (endSec - startSec) * ratio) * 100) / 100;

  const childA: T = {
    ...parent,
    block_id: `${parent.block_id}a`,
    sequence_index: parent.sequence_index,
    parent_block_id: parent.block_id,
    start_time_sec: startSec,
    end_time_sec: midSec,
    text_scrubbed: leftText,
    word_count: Math.max(1, leftText.split(/\s+/).filter(Boolean).length),
    is_split: true,
  };

  const childB: T = {
    ...parent,
    block_id: `${parent.block_id}b`,
    sequence_index: parent.sequence_index + 1,
    parent_block_id: parent.block_id,
    start_time_sec: midSec,
    end_time_sec: endSec,
    text_scrubbed: rightText,
    word_count: Math.max(1, rightText.split(/\s+/).filter(Boolean).length),
    is_split: true,
  };

  const nextBlocks: T[] = [];
  for (let i = 0; i < blocks.length; i++) {
    if (i < targetIndex) {
      nextBlocks.push(blocks[i]);
    } else if (i === targetIndex) {
      nextBlocks.push(childA, childB);
    } else {
      nextBlocks.push({
        ...blocks[i],
        sequence_index: blocks[i].sequence_index + 1,
      });
    }
  }
  return nextBlocks;
}
