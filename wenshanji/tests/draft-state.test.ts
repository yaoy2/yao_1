import { describe, expect, it } from "vitest";
import { parseRoundtableDraft, serializeRoundtableDraft } from "../src/lib/draft-state";
import type { Seat, SeatAssignment } from "../src/lib/types";

const seats: Seat[] = [
  {
    id: "s1",
    name: "现实主义教师",
    type: "现实批判",
    coreConcern: "任务是否挤压真实教学",
    typicalQuestions: ["谁承担额外劳动？"],
    mustDo: "讲具体场景",
    mustNotDo: "不要空泛抱怨",
    likelyOpponents: [],
    blindSpots: [],
    speakingStyle: "直接",
    examplePreference: "",
    openingPrompt: "",
    debatePrompt: ""
  }
];

const assignments: SeatAssignment[] = [
  {
    id: "a1",
    seatId: "s1",
    providerId: "kimi",
    reason: "匹配表达型席位"
  }
];

describe("roundtable draft state", () => {
  it("round-trips topic, seat pool, selected seats, assignments, and mock mode", () => {
    const serialized = serializeRoundtableDraft({
      topic: "讨论题",
      seatPoolText: "{\"seats\":[]}",
      seats,
      selectedSeatIds: ["s1"],
      assignments,
      useMock: false,
      showSeatPoolEditor: false
    });

    expect(parseRoundtableDraft(serialized)).toEqual({
      topic: "讨论题",
      seatPoolText: "{\"seats\":[]}",
      seats,
      selectedSeatIds: ["s1"],
      assignments,
      useMock: false,
      showSeatPoolEditor: false
    });
  });

  it("returns null for invalid or incomplete persisted data", () => {
    expect(parseRoundtableDraft("not json")).toBeNull();
    expect(parseRoundtableDraft(JSON.stringify({ topic: "missing arrays" }))).toBeNull();
  });
});
