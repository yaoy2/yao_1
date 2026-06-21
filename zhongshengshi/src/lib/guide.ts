export interface GuideSection {
  title: string;
  items: string[];
}

export const projectGuideSections: GuideSection[] = [
  {
    title: "最快跑通",
    items: [
      "先保持 mock provider 勾选，输入话题，解析示例席位池，选择 4 到 6 个席位。",
      "点击“生成席位分配”，确认每个模型最多承载 2 个席位。",
      "点击“开始圆桌”，页面会生成 opening 和 1 轮 debate 的 transcript。"
    ]
  },
  {
    title: "真实模型",
    items: [
      "在 .env.local 填写 DeepSeek、MiMo、MiniMax 的 API Key、Base URL 和 Model Name。",
      "取消 mock provider 后再开始圆桌；API Key 只在服务端读取，不会返回前端。",
      "真实 provider 当前按 OpenAI-compatible Chat Completions 调用，不兼容的服务后续再补 adapter。"
    ]
  },
  {
    title: "席位池格式",
    items: [
      "JSON 顶层可以是数组，也可以包含 seats、席位池、候选席位、seatPool 或 candidates。",
      "每个席位至少需要名称和核心关切；建议补充类型、典型问题、应做/不应做、反驳对象、盲点和发言风格。",
      "系统会把这些字段写入 prompt，约束模型按席位身份发言。"
    ]
  },
  {
    title: "结果解读",
    items: [
      "Transcript 按 round、phase、seat、provider 展示每条发言。",
      "运行日志显示 provider 调用次数和失败次数。",
      "某个席位调用失败时会显示错误，但其他席位会继续完成。"
    ]
  },
  {
    title: "当前边界",
    items: [
      "当前只实现 opening + 1 轮 debate，还没有总结、缺席视角检测和数据保存。",
      "下一阶段适合做发言价值评估，让交锋轮不必每个席位都发言。",
      "先不做 Streamlit 适配，等核心圆桌流程稳定后再决定。"
    ]
  }
];
