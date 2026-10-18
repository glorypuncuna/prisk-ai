import { describe, expect, it } from "vitest";
import {
  calculateDeterministicRollups,
  RollupBlockInput,
  splitDialogueBlockClient,
} from "./rollupUtils";

describe("rollupUtils deterministic rollups & bubble split", () => {
  const sampleBlocks: RollupBlockInput[] = [
    {
      block_id: "blk_1",
      group_name: "INTERNAL",
      text_scrubbed: "one two three four five six seven eight nine ten",
      word_count: 10,
      sentiment_score: 40,
    },
    {
      block_id: "blk_2",
      group_name: "INTERNAL",
      text_scrubbed:
        "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega one two three four five six",
      word_count: 30,
      sentiment_score: 80,
    },
    {
      block_id: "blk_3",
      group_name: "EXTERNAL_CLIENT",
      text_scrubbed:
        "security check passed cleanly across all clusters today now ok",
      word_count: 10,
      sentiment_score: 90,
    },
  ];

  it("computes exact word-count weighted Group and Meeting Pulse Scores in <50ms", () => {
    const t0 = performance.now();
    const result = calculateDeterministicRollups(sampleBlocks);
    const elapsedMs = performance.now() - t0;

    // INTERNAL: (10 * 40 + 30 * 80) / (10 + 30) = 2800 / 40 = 70
    // EXTERNAL_CLIENT: (10 * 90) / 10 = 90
    // Overall (arithmetic mean across active groups): (70 + 90) / 2 = 80
    expect(result.groupScores["INTERNAL"].pulse_score).toBe(70);
    expect(result.groupScores["INTERNAL"].block_count).toBe(2);
    expect(result.groupScores["EXTERNAL_CLIENT"].pulse_score).toBe(90);
    expect(result.overallPulseScore).toBe(80);
    expect(elapsedMs).toBeLessThan(50);
  });

  it("splits a dialogue block at cursor offset, inherits parent sentiment and group, and preserves rollup score", () => {
    const parent = {
      block_id: "blk_0001",
      sequence_index: 0,
      group_name: "INTERNAL",
      start_time_sec: 0,
      end_time_sec: 20,
      text_scrubbed: "First half is great. Second half has severe database risk.",
      word_count: 10,
      sentiment_score: 52,
      is_split: false,
    };

    const splitIdx = "First half is great.".length;
    const updated = splitDialogueBlockClient([parent], "blk_0001", splitIdx);

    expect(updated).toHaveLength(2);
    expect(updated[0].block_id).toBe("blk_0001a");
    expect(updated[1].block_id).toBe("blk_0001b");
    expect(updated[0].text_scrubbed).toBe("First half is great.");
    expect(updated[1].text_scrubbed).toBe(
      "Second half has severe database risk."
    );
    expect(updated[0].sentiment_score).toBe(52);
    expect(updated[1].sentiment_score).toBe(52);
    expect(updated[0].group_name).toBe("INTERNAL");
    expect(updated[1].group_name).toBe("INTERNAL");

    const rollups = calculateDeterministicRollups(updated);
    expect(rollups.overallPulseScore).toBe(52);
  });
});
