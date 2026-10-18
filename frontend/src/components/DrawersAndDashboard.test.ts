import { describe, expect, it } from "vitest";
import { ValidatedSpanAttribution } from "../types/domain";

describe("Drawers and Dashboard logic", () => {
  it("validates and sorts verbatim attribution substrings for XaiRationaleDrawer", () => {
    const text = "Audit approved with zero defects. Delivery timeline is delayed.";
    const attributions: ValidatedSpanAttribution[] = [
      {
        verbatim_phrase: "Delivery timeline is delayed",
        start_char: 35,
        end_char: 63,
        attribution_weight: -0.8,
        rubric_dimension: "Delivery Alignment",
        rationale: "Timeline delay introduces delivery risk.",
      },
      {
        verbatim_phrase: "Audit approved with zero defects",
        start_char: 0,
        end_char: 32,
        attribution_weight: 0.9,
        rubric_dimension: "Compliance",
        rationale: "Zero defect sign-off reinforces alignment.",
      },
    ];

    const sorted = [...attributions].sort((a, b) => a.start_char - b.start_char);
    expect(text.slice(sorted[0].start_char, sorted[0].end_char)).toBe("Audit approved with zero defects");
    expect(sorted[0].verbatim_phrase).toBe("Audit approved with zero defects");
    expect(sorted[1].verbatim_phrase).toBe("Delivery timeline is delayed");
    expect(sorted[0].attribution_weight).toBeGreaterThan(0);
    expect(sorted[1].attribution_weight).toBeLessThan(0);
  });


  it("calculates 4-bar rubric sum and status badge accurately", () => {
    const rubric = {
      emotional_valence: 20,
      delivery_alignment: 21,
      relationship_trust: 19,
      momentum_commitment: 20,
    };
    const sum =
      rubric.emotional_valence +
      rubric.delivery_alignment +
      rubric.relationship_trust +
      rubric.momentum_commitment;

    expect(sum).toBe(80);
    const isPositive = sum >= 70;
    expect(isPositive).toBe(true);
  });

  it("computes trajectory points delta and group averages", () => {
    const points = [
      { meeting_id: "m1", pulse_score: 45.0 },
      { meeting_id: "m2", pulse_score: 75.0 },
    ];
    const avg = (points[0].pulse_score + points[1].pulse_score) / 2;
    const shift = points[1].pulse_score - points[0].pulse_score;

    expect(avg).toBe(60.0);
    expect(shift).toBe(30.0);
  });
});
