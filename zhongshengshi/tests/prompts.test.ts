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

  it("fills generic constraints when optional prompt fields are missing", () => {
    const compactSeat: Seat = {
      id: "compact-1",
      name: "就业能力迁移派",
      type: "能力迁移",
      coreConcern: "非对口竞赛能否训练通用表达、协作和作品化能力",
      typicalQuestions: ["能力是否能迁移到专业学习？"],
      mustDo: "说明可迁移能力和边界",
      mustNotDo: "不要把所有竞赛都说成有用",
      likelyOpponents: [],
      blindSpots: [],
      speakingStyle: "务实、分寸清楚",
      examplePreference: "",
      openingPrompt: "",
      debatePrompt: ""
    };

    const openingPrompt = buildOpeningPrompt({ topic: "低相关竞赛利弊", seat: compactSeat });
    const debatePrompt = buildDebatePrompt({ topic: "低相关竞赛利弊", seat: compactSeat, transcript: [] });

    expect(openingPrompt).toContain("通用约束");
    expect(openingPrompt).toContain("不主动假设反驳对象");
    expect(openingPrompt).toContain("盲点未填写");
    expect(debatePrompt).toContain("没有自定义交锋提示时");
    expect(debatePrompt).toContain("请选择最值得回应的一个具体观点");
  });
});
