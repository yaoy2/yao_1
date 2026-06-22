import { describe, expect, it } from "vitest";
import { buildDebatePrompt, buildOpeningPrompt } from "../src/lib/prompt-builder";
import type { RoundtableTranscriptItem } from "../src/lib/roundtable";
import type { Seat } from "../src/lib/types";

const seat: Seat = {
  id: "quality-seat",
  name: "学生时间成本亲历者",
  type: "学生发展",
  coreConcern: "低相关竞赛是否挤压专业学习、实习准备和休息时间",
  typicalQuestions: ["学生真正获得了什么？", "代价由谁承担？"],
  mustDo: "把判断落到学生时间账本和能力收益",
  mustNotDo: "不要用综合看待代替判断",
  likelyOpponents: ["泛竞赛机会辩护者"],
  blindSpots: ["可能低估少量竞赛带来的表达训练"],
  speakingStyle: "具体、克制、带现场感",
  examplePreference: "学生备赛、专业作业和实习准备冲突的例子",
  openingPrompt: "",
  debatePrompt: ""
};

const transcript: RoundtableTranscriptItem[] = [
  {
    id: "m1",
    round: 1,
    phase: "opening",
    seatId: "s2",
    seatName: "泛竞赛机会辩护者",
    providerId: "kimi",
    providerName: "Kimi",
    status: "success",
    content: "低相关竞赛至少给学生补足表达训练和简历素材，不该只看专业对口程度。",
    createdAt: "2026-06-21T00:00:00.000Z"
  }
];

describe("prompt quality rules", () => {
  it("requires opening speeches to start with a judgment and avoid topic repetition", () => {
    const prompt = buildOpeningPrompt({ topic: "学院专业竞赛少且难，参加低相关竞赛利大还是弊大", seat });

    expect(prompt).toContain("第一句直接给出判断");
    expect(prompt).toContain("不要复述题目");
    expect(prompt).toContain("禁止");
    expect(prompt).toContain("综合看待");
  });

  it("requires debate speeches to respond to a concrete prior view instead of generic agreement", () => {
    const prompt = buildDebatePrompt({ topic: "学院专业竞赛少且难，参加低相关竞赛利大还是弊大", seat, transcript });

    expect(prompt).toContain("点名回应");
    expect(prompt).toContain("不能只说同意");
    expect(prompt).toContain("不合格");
    expect(prompt).toContain("泛竞赛机会辩护者");
  });
});
