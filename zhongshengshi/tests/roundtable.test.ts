import { describe, expect, it } from "vitest";
import { assignSeatsToProviders } from "../src/lib/assignment";
import { createMockProviderClient } from "../src/lib/mock-provider";
import { runRoundtable } from "../src/lib/roundtable";
import type { ModelProvider, Seat } from "../src/lib/types";

const seats: Seat[] = Array.from({ length: 4 }, (_, index) => ({
  id: `s${index + 1}`,
  name: [`制度分析者`, `古典教育伦理`, `工程实务派`, `基层教师现实主义`][index],
  type: [`制度分析`, `伦理叙事`, `方案工程`, `现实批判`][index],
  coreConcern: [`责任边界`, `人的成长`, `执行路径`, `行政挤压`][index],
  typicalQuestions: ["关键问题是什么？"],
  mustDo: "提出清楚判断",
  mustNotDo: "不要空话",
  likelyOpponents: ["其他席位"],
  blindSpots: ["可能忽略另一侧"],
  speakingStyle: "清楚直接",
  examplePreference: "高校场景",
  openingPrompt: "",
  debatePrompt: ""
}));

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

describe("runRoundtable", () => {
  it("runs opening and one debate round for each selected seat", async () => {
    const result = await runRoundtable({
      topic: "高校行政流程如何减负",
      selectedSeats: seats,
      providerAssignments: assignSeatsToProviders(seats),
      providers,
      rounds: 1,
      providerClientFactory: () => createMockProviderClient()
    });

    expect(result.status).toBe("success");
    expect(result.transcript).toHaveLength(8);
    expect(result.transcript.filter((item) => item.phase === "opening")).toHaveLength(4);
    expect(result.transcript.filter((item) => item.phase === "debate")).toHaveLength(4);
    expect(result.errors).toHaveLength(0);
    expect(result.providerStatus.every((item) => item.calls > 0)).toBe(true);
  });

  it("mock speeches avoid plumbing-test filler and keep phase-specific substance", async () => {
    const result = await runRoundtable({
      topic: "学院专业竞赛少且难，参加低相关竞赛利大还是弊大",
      selectedSeats: seats,
      providerAssignments: assignSeatsToProviders(seats),
      providers,
      rounds: 1,
      providerClientFactory: () => createMockProviderClient()
    });

    const successfulMessages = result.transcript.filter((item) => item.status === "success");
    expect(successfulMessages).toHaveLength(8);
    expect(successfulMessages.some((item) => item.content.includes("链路"))).toBe(false);
    expect(successfulMessages.some((item) => item.content.includes("本地验证"))).toBe(false);
    expect(successfulMessages.some((item) => item.content.includes("围绕"))).toBe(false);
    expect(successfulMessages.every((item) => item.content.length > 80)).toBe(true);
    expect(result.transcript.find((item) => item.phase === "opening")?.content).toContain("我的判断");
    expect(result.transcript.find((item) => item.phase === "debate")?.content).toContain("我回应");
    expect(new Set(result.transcript.filter((item) => item.phase === "opening").map((item) => item.content.slice(0, 36))).size).toBeGreaterThan(1);
  });

  it("records a failed seat call and continues the remaining seats", async () => {
    const result = await runRoundtable({
      topic: "高校行政流程如何减负",
      selectedSeats: seats,
      providerAssignments: assignSeatsToProviders(seats),
      providers,
      rounds: 1,
      providerClientFactory: () => createMockProviderClient({ failSeatIds: ["s2"] })
    });

    expect(result.status).toBe("failed");
    expect(result.errors.some((error) => error.seatId === "s2")).toBe(true);
    expect(result.transcript.some((item) => item.seatId === "s1" && item.status === "success")).toBe(true);
    expect(result.transcript.some((item) => item.seatId === "s2" && item.status === "failed")).toBe(true);
  });
});
