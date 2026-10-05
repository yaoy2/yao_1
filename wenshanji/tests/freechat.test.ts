import { describe, expect, it } from "vitest";
import { assignSeatsToProviders } from "../src/lib/assignment";
import { createMockProviderClient } from "../src/lib/mock-provider";
import { runRoundtable } from "../src/lib/roundtable";
import type { ModelProvider, Seat } from "../src/lib/types";

const seats: Seat[] = [
  makeSeat("s1", "用人单位观察者", "就业反馈", "竞赛经历在就业筛选中是否能证明岗位能力"),
  makeSeat("s2", "学生时间成本亲历者", "学生发展", "低相关竞赛是否挤压专业学习和休息时间"),
  makeSeat("s3", "泛竞赛机会辩护者", "机会辩护", "泛竞赛是否提供表达训练和简历补充机会"),
  makeSeat("s4", "绩效治理批判者", "治理批判", "低相关竞赛是否变成学院绩效和新闻稿生产工具")
];

const providers: ModelProvider[] = [
  {
    id: "deepseek",
    displayName: "DeepSeek",
    baseUrl: "mock://deepseek",
    modelName: "mock-deepseek",
    providerType: "mock",
    isConfigured: true
  },
  {
    id: "mimo",
    displayName: "MiMo",
    baseUrl: "mock://mimo",
    modelName: "mock-mimo",
    providerType: "mock",
    isConfigured: true
  },
  {
    id: "kimi",
    displayName: "Kimi",
    baseUrl: "mock://kimi",
    modelName: "mock-kimi",
    providerType: "mock",
    isConfigured: true
  }
];

describe("freechat roundtable mode", () => {
  it("runs a short conversational message stream instead of fixed opening/debate turns", async () => {
    const result = await runRoundtable({
      topic: "低相关竞赛对学生利大还是弊大",
      selectedSeats: seats,
      providerAssignments: assignSeatsToProviders(seats),
      providers,
      mode: "freechat",
      messageBudget: 12,
      providerClientFactory: () => createMockProviderClient()
    });

    expect(result.status).toBe("success");
    expect(result.transcript).toHaveLength(12);
    expect(result.transcript.every((item) => item.phase === "freechat")).toBe(true);
    expect(result.transcript.every((item) => item.content.length >= 45 && item.content.length <= 260)).toBe(true);

    const speakerSequence = result.transcript.map((item) => item.seatId);
    expect(speakerSequence.slice(0, 4)).not.toEqual(seats.map((seat) => seat.id));
    expect(new Set(speakerSequence).size).toBeLessThan(seats.length);
    expect(speakerSequence.slice(1).every((seatId, index) => seatId !== speakerSequence[index])).toBe(true);
    expect(result.transcript.filter((item) => /我接一句|我补一句/.test(item.content))).toHaveLength(0);
    expect(result.transcript.some((item) => /别急|先看|问题在于|这里真正/.test(item.content))).toBe(true);
  });
  it("calls every provider that has assigned seats during freechat", async () => {
    const sixSeats = [
      ...seats,
      makeSeat("s5", "mimo plan seat", "plan", "execution flow"),
      makeSeat("s6", "mimo operation seat", "operation", "implementation steps")
    ];
    const providerAssignments = [
      { id: "assignment-1", seatId: "s1", providerId: "deepseek" as const, reason: "test" },
      { id: "assignment-2", seatId: "s2", providerId: "kimi" as const, reason: "test" },
      { id: "assignment-3", seatId: "s3", providerId: "deepseek" as const, reason: "test" },
      { id: "assignment-4", seatId: "s4", providerId: "kimi" as const, reason: "test" },
      { id: "assignment-5", seatId: "s5", providerId: "mimo" as const, reason: "test" },
      { id: "assignment-6", seatId: "s6", providerId: "mimo" as const, reason: "test" }
    ];

    const result = await runRoundtable({
      topic: "low relevance competitions",
      selectedSeats: sixSeats,
      providerAssignments,
      providers,
      mode: "freechat",
      messageBudget: 14,
      providerClientFactory: () => createMockProviderClient()
    });

    expect(result.providerStatus.find((item) => item.providerId === "deepseek")?.calls).toBeGreaterThan(0);
    expect(result.providerStatus.find((item) => item.providerId === "kimi")?.calls).toBeGreaterThan(0);
    expect(result.providerStatus.find((item) => item.providerId === "mimo")?.calls).toBeGreaterThan(0);
  });
});

function makeSeat(id: string, name: string, type: string, coreConcern: string): Seat {
  return {
    id,
    name,
    type,
    coreConcern,
    typicalQuestions: ["这个判断落到学生身上会发生什么？"],
    mustDo: "说具体代价和收益",
    mustNotDo: "不要空泛综合看待",
    likelyOpponents: [],
    blindSpots: [],
    speakingStyle: "短促、直接、像真实讨论",
    examplePreference: "",
    openingPrompt: "",
    debatePrompt: ""
  };
}
