import { describe, expect, it } from "vitest";
import { getPresetSeatPoolText, lowRelevanceCompetitionPreset } from "../src/lib/preset-seat-pools";
import { parseSeatPool } from "../src/lib/seats";

describe("low relevance competition preset", () => {
  it("loads a compact six-seat preset that can be parsed directly", () => {
    expect(lowRelevanceCompetitionPreset.topic).toBe("学院四个专业对口竞赛少且难，参加艺术设计大赛、AI微摄影大赛、知识竞赛，对学生利大还是弊大。");
    expect(lowRelevanceCompetitionPreset.seats).toHaveLength(6);

    const parsedSeats = parseSeatPool(getPresetSeatPoolText(lowRelevanceCompetitionPreset));

    expect(parsedSeats).toHaveLength(6);
    expect(parsedSeats[0]).toMatchObject({
      name: "竞赛机会现实派",
      type: "现实评估"
    });
  });
});
