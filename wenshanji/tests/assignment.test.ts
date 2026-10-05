import { describe, expect, it } from "vitest";
import { assignSeatsToProviders } from "../src/lib/assignment";
import type { Seat } from "../src/lib/types";

const seat = (id: string, name: string, type: string, coreConcern: string): Seat => ({
  id,
  name,
  type,
  coreConcern,
  typicalQuestions: [],
  mustDo: "",
  mustNotDo: "",
  likelyOpponents: [],
  blindSpots: [],
  speakingStyle: "",
  examplePreference: "",
  openingPrompt: "",
  debatePrompt: ""
});

describe("assignSeatsToProviders", () => {
  it("assigns selected seats by provider preference while keeping at most two per provider", () => {
    const assignments = assignSeatsToProviders([
      seat("s1", "制度分析者", "制度分析", "治理结构和责任边界"),
      seat("s2", "基层教师现实主义", "现实批判", "行政任务挤压教学"),
      seat("s3", "叙事伦理观察者", "伦理叙事", "人的感受和角色关系"),
      seat("s4", "人际协调者", "人际沟通", "关系修复"),
      seat("s5", "工程实务派", "方案工程", "可执行步骤"),
      seat("s6", "操作推理者", "实务推理", "流程和操作约束")
    ]);

    expect(assignments).toHaveLength(6);
    expect(assignments.filter((item) => item.providerId === "deepseek")).toHaveLength(2);
    expect(assignments.filter((item) => item.providerId === "kimi")).toHaveLength(2);
    expect(assignments.filter((item) => item.providerId === "mimo")).toHaveLength(2);
    expect(assignments.find((item) => item.seatId === "s1")?.providerId).toBe("deepseek");
    expect(assignments.find((item) => item.seatId === "s3")?.providerId).toBe("kimi");
    expect(assignments.find((item) => item.seatId === "s5")?.providerId).toBe("mimo");
  });
});
