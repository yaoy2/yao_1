import { describe, expect, it } from "vitest";
import { parseSeatPool, validateSeatSelection } from "../src/lib/seats";

describe("parseSeatPool", () => {
  it("accepts a compact seat pool with only the runtime-required fields", () => {
    const input = JSON.stringify({
      seats: [
        {
          seat_name: "竞赛机会现实派",
          type: "现实评估",
          core_concern: "低相关竞赛是否仍能带来可迁移能力",
          typical_questions: ["学生投入是否值得？", "获奖难度是否可承受？"],
          must_do: "比较收益和机会成本",
          must_not_do: "不要只用竞赛数量判断价值",
          speaking_style: "克制、具体、重证据"
        }
      ]
    });

    const seats = parseSeatPool(input);

    expect(seats).toHaveLength(1);
    expect(seats[0]).toMatchObject({
      name: "竞赛机会现实派",
      type: "现实评估",
      coreConcern: "低相关竞赛是否仍能带来可迁移能力",
      typicalQuestions: ["学生投入是否值得？", "获奖难度是否可承受？"],
      mustDo: "比较收益和机会成本",
      mustNotDo: "不要只用竞赛数量判断价值",
      speakingStyle: "克制、具体、重证据",
      likelyOpponents: [],
      blindSpots: []
    });
  });

  it("normalizes a copied GPT seat pool with Chinese and English field names", () => {
    const input = JSON.stringify({
      seats: [
        {
          id: "s1",
          "席位名称": "基层教师现实主义",
          type: "现实批判",
          "核心关切": "行政任务挤压教学",
          typicalQuestions: ["谁承担额外劳动？"],
          mustDo: "指出现实约束",
          mustNotDo: "不要只谈理想",
          "可能反驳对象": ["古典教育伦理"],
          "典型盲点": ["容易忽略长期愿景"],
          speakingStyle: "直接、具体",
          examplePreference: "校园真实场景"
        }
      ]
    });

    const seats = parseSeatPool(input);

    expect(seats).toHaveLength(1);
    expect(seats[0]).toMatchObject({
      id: "s1",
      name: "基层教师现实主义",
      type: "现实批判",
      coreConcern: "行政任务挤压教学",
      likelyOpponents: ["古典教育伦理"],
      blindSpots: ["容易忽略长期愿景"]
    });
  });

  it("reports a useful error when JSON is not a seat array", () => {
    expect(() => parseSeatPool("{\"topic\":\"no seats\"}")).toThrow("没有找到席位数组");
  });
});

describe("validateSeatSelection", () => {
  it("accepts 4 to 6 selected seats", () => {
    expect(validateSeatSelection(["a", "b", "c", "d"])).toEqual({ ok: true });
    expect(validateSeatSelection(["a", "b", "c", "d", "e", "f"])).toEqual({ ok: true });
  });

  it("rejects too few or too many selected seats", () => {
    expect(validateSeatSelection(["a", "b", "c"])).toEqual({
      ok: false,
      message: "请选择 4 到 6 个席位进入本局。"
    });
    expect(validateSeatSelection(["a", "b", "c", "d", "e", "f", "g"])).toEqual({
      ok: false,
      message: "请选择 4 到 6 个席位进入本局。"
    });
  });
});
