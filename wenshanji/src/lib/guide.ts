export interface GuideSection {
  title: string;
  items: string[];
}

export const projectGuideSections: GuideSection[] = [
  {
    title: "最快跑通",
    items: [
      "可以先保持 mock provider 勾选，输入话题，解析示例席位池，选择 4 到 6 个席位。",
      "点击“生成席位分配”，确认每个模型最多承载 2 个席位。",
      "点击“开始圆桌”，页面会生成一串自由讨论消息；mock 只验证流程，不代表真实讨论质量。"
    ]
  },
  {
    title: "真实模型",
    items: [
      "在 .env.local 填写 DeepSeek、MiMo、Kimi 的 API Key、Base URL 和 Model Name。",
      "要看真实发言质量，请取消 mock provider 后再开始圆桌；API Key 只在服务端读取，不会返回前端。",
      "真实 provider 当前按 OpenAI-compatible Chat Completions 调用，不兼容的服务后续再补 adapter。"
    ]
  },
  {
    title: "席位池格式",
    items: [
      "JSON 顶层可以是数组，也可以包含 seats、席位池、候选席位、seatPool 或 candidates。",
      "每个席位至少需要名称和核心关切；建议补充类型、典型问题、应做/不应做、反驳对象、盲点和发言风格。",
      "系统会把这些字段写入 prompt，让每个席位像有独立判断的人一样接话。"
    ]
  },
  {
    title: "结果解读",
    items: [
      "Transcript 按消息顺序展示 seat、provider、phase 和发言内容。",
      "当前默认 phase 是 freechat，表示短消息自由讨论，不再是固定 opening / debate 排队发言。",
      "某个席位调用失败时会显示错误，但其他席位会继续完成。"
    ]
  },
  {
    title: "当前边界",
    items: [
      "当前先实现自由讨论消息流，还没有主持人总结、缺席视角检测和数据保存。",
      "speaker planner 仍是轻量规则版，只能模拟插话、沉默和重复接话；后续可升级为模型判断谁最该发言。",
      "先不做 Streamlit 适配，等核心圆桌流程稳定后再决定。"
    ]
  }
];
