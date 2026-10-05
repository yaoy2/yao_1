import { describe, expect, it } from "vitest";
import { projectGuideSections } from "../src/lib/guide";

describe("projectGuideSections", () => {
  it("documents the freechat workflow and key safety boundary", () => {
    const guideText = JSON.stringify(projectGuideSections);

    expect(guideText).toContain("mock provider");
    expect(guideText).toContain("开始圆桌");
    expect(guideText).toContain("API Key 只在服务端读取");
    expect(guideText).toContain("freechat");
    expect(guideText).toContain("不再是固定 opening / debate 排队发言");
    expect(guideText).toContain("先不做 Streamlit 适配");
  });
});
