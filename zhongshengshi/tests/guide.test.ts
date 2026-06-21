import { describe, expect, it } from "vitest";
import { projectGuideSections } from "../src/lib/guide";

describe("projectGuideSections", () => {
  it("documents the minimum local workflow and key safety boundary", () => {
    const guideText = JSON.stringify(projectGuideSections);

    expect(guideText).toContain("mock provider");
    expect(guideText).toContain("开始圆桌");
    expect(guideText).toContain("API Key 只在服务端读取");
    expect(guideText).toContain("opening + 1 轮 debate");
    expect(guideText).toContain("先不做 Streamlit 适配");
  });
});
