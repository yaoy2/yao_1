import { describe, expect, it } from "vitest";
import { buildDebatePrompt, buildOpeningPrompt } from "../src/lib/prompt-builder";
import type { RoundtableTranscriptItem } from "../src/lib/roundtable";
import type { Seat } from "../src/lib/types";

const seat: Seat = {
  id: "s1",
  name: "基层教师现实主义",
  type: "现实批判",
  coreConcern: "行政任务挤压真实教学",
  typicalQuestions: ["谁承担额外劳动？"],
  mustDo: "指出现实约束",
  mustNotDo: "不要只谈宏大理想",
  likelyOpponents: ["古典教育伦理"],
  blindSpots: ["容易低估长期愿景"],
  speakingStyle: "直接、具体、有现场感",
  examplePreference: "校园真实场景",
  openingPrompt: "先给出基本判断",
  debatePrompt: "必须回应其他席位"
};

describe("prompt builder", () => {
  it("builds opening prompts from every required seat field", () => {
    const prompt = buildOpeningPrompt({ topic: "高校行政流程如何减负", seat });

    expect(prompt).toContain("基层教师现实主义");
    expect(prompt).toContain("现实批判");
    expect(prompt).toContain("行政任务挤压真实教学");
    expect(prompt).toContain("谁承担额外劳动？");
    expect(prompt).toContain("指出现实约束");
    expect(prompt).toContain("不要只谈宏大理想");
    expect(prompt).toContain("古典教育伦理");
    expect(prompt).toContain("容易低估长期愿景");
    expect(prompt).toContain("直接、具体、有现场感");
    expect(prompt).toContain("校园真实场景");
    expect(prompt).toContain("350 到 800 个中文字符");
    expect(prompt).toContain("避免空泛赞同");
  });

  it("builds debate prompts with transcript context and response constraints", () => {
    const transcript: RoundtableTranscriptItem[] = [
      {
        id: "m1",
        round: 1,
        phase: "opening",
        seatId: "s2",
        seatName: "古典教育伦理",
        providerId: "minimax",
        providerName: "MiniMax",
        status: "success",
        content: "教育要守住人的完整成长。",
        createdAt: "2026-06-21T00:00:00.000Z"
      }
    ];

    const prompt = buildDebatePrompt({ topic: "高校行政流程如何减负", seat, transcript });

    expect(prompt).toContain("前面 transcript");
    expect(prompt).toContain("古典教育伦理");
    expect(prompt).toContain("教育要守住人的完整成长");
    expect(prompt).toContain("回应、反驳、补充或追问");
    expect(prompt).toContain("不要复述前文");
  });
});
