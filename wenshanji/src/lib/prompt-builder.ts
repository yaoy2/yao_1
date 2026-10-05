import type { Seat } from "./types";
import type { RoundtableTranscriptItem } from "./roundtable";

export function buildOpeningPrompt({ topic, seat }: { topic: string; seat: Seat }): string {
  return [
    "你正在参加一个多模型圆桌群聊。请严格以指定席位身份发言，不要跳出角色。",
    seatBlock(seat),
    `本次讨论话题：${topic}`,
    seat.openingPrompt ? `席位自带开场要求：${seat.openingPrompt}` : "",
    optionalConstraintBlock(seat, "opening"),
    "请生成 opening 阶段发言，长度控制在 350 到 800 个中文字符。",
    "质量底线：第一句直接给出判断，不要复述题目，不要先铺垫背景。",
    "要求：明确判断，说明理由，必要时给一个贴近讨论场景的小例子。",
    "禁止：复述题目、照抄席位设定、用“要综合看待”“有利有弊”“需要平衡”代替判断、模板化套话和泛泛抒情；尤其要避免空泛赞同。",
    "输出必须包含一个可被其他席位反驳或追问的具体判断。"
  ]
    .filter(Boolean)
    .join("\n\n");
}

export function buildDebatePrompt({
  topic,
  seat,
  transcript
}: {
  topic: string;
  seat: Seat;
  transcript: RoundtableTranscriptItem[];
}): string {
  return [
    "你正在参加一个多模型圆桌群聊。现在进入 debate 阶段。",
    seatBlock(seat),
    `本次讨论话题：${topic}`,
    seat.debatePrompt ? `席位自带交锋要求：${seat.debatePrompt}` : "",
    optionalConstraintBlock(seat, "debate"),
    "前面 transcript：",
    renderTranscript(transcript),
    "请读取前面 transcript，并对其他席位的具体观点进行回应、反驳、补充或追问。",
    "请生成 debate 阶段发言，长度控制在 350 到 800 个中文字符。",
    "质量底线：必须点名回应至少一个席位的具体观点，不能只说同意，不能复述题目；不要复述前文。",
    "要求：提出新的区分、反例、现实约束或追问，并说明这个回应如何改变前面的判断。",
    "不合格输出：只总结大家观点；只说“我同意”；只说“要综合看待”；只重复自己的 core_concern；只给没有对象的空泛建议。",
    "请用一段完整发言输出，不要列提纲。"
  ]
    .filter(Boolean)
    .join("\n\n");
}

export function buildFreechatPrompt({
  topic,
  seat,
  transcript,
  messageIndex,
  totalMessages
}: {
  topic: string;
  seat: Seat;
  transcript: RoundtableTranscriptItem[];
  messageIndex: number;
  totalMessages: number;
}): string {
  return [
    "你正在参加一个自由圆桌聊天。你不是写作文，不是提交正式发言，而是在群聊里自然说一段。",
    seatBlock(seat),
    `本次话题：${topic}`,
    `当前是第 ${messageIndex} / ${totalMessages} 条消息。`,
    "前面聊天：",
    renderTranscript(transcript.slice(-8)),
    "请以这个席位像一个活人一样回应现场。可以反驳、追问、换个角度、把话拉回现实，也可以承认对方一部分道理后指出边界。",
    "长度控制在 80 到 220 个中文字符。只输出这一条聊天消息，不要写标题，不要列提纲。",
    "禁止：复述题目、完整总结大家观点、用“我认为/我的判断”开头写小作文、套用固定结构、说“综合看待”。",
    "不要用固定口头禅开头，尤其不要反复说“我接一句”“我补一句”。开头要根据上一条内容自然变化，可以直接提出判断、场景、证据或疑问。"
  ]
    .filter(Boolean)
    .join("\n\n");
}

function seatBlock(seat: Seat): string {
  return [
    `seat_name：${seat.name}`,
    `type：${seat.type || "未填写"}`,
    `core_concern：${seat.coreConcern || "未填写"}`,
    `typical_questions：${formatList(seat.typicalQuestions)}`,
    `must_do：${seat.mustDo || "未填写"}`,
    `must_not_do：${seat.mustNotDo || "未填写"}`,
    `likely_opponents：${formatList(seat.likelyOpponents)}`,
    `blind_spots：${formatList(seat.blindSpots)}`,
    `speaking_style：${seat.speakingStyle || "未填写"}`,
    `example_preference：${seat.examplePreference || "未填写"}`
  ].join("\n");
}

function optionalConstraintBlock(seat: Seat, phase: "opening" | "debate"): string {
  const constraints: string[] = [];

  if (!seat.likelyOpponents.length) {
    constraints.push("likely_opponents 未填写：不主动假设反驳对象，先从 transcript 中寻找具体可回应观点。");
  }
  if (!seat.blindSpots.length) {
    constraints.push("盲点未填写：发言时主动承认本席位可能看不到的另一面。");
  }
  if (!seat.examplePreference) {
    constraints.push("example_preference 未填写：只在能帮助判断变清楚时使用简短、贴近校园或竞赛场景的例子。");
  }
  if (phase === "opening" && !seat.openingPrompt) {
    constraints.push("opening_prompt 未填写：先给出基本判断，再说明理由和边界。");
  }
  if (phase === "debate" && !seat.debatePrompt) {
    constraints.push("没有自定义交锋提示时，请选择最值得回应的一个具体观点，明确回应、修正、反驳或追问。");
  }

  if (!constraints.length) {
    return "";
  }

  return ["通用约束：", ...constraints.map((item) => `- ${item}`)].join("\n");
}

function renderTranscript(transcript: RoundtableTranscriptItem[]): string {
  if (transcript.length === 0) {
    return "暂无前序发言。";
  }

  return transcript
    .map((item) => `[${item.phase}] ${item.providerName}｜${item.seatName}：${item.content}`)
    .join("\n");
}

function formatList(items: string[]): string {
  return items.length ? items.join("、") : "未填写";
}
