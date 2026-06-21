import { describe, expect, it } from "vitest";
import { parseSeatPool, validateSeatSelection } from "../src/lib/seats";

describe("parseSeatPool", () => {
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
