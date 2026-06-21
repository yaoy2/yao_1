import type { Seat } from "./types";
import type { RoundtableTranscriptItem } from "./roundtable";

export function buildOpeningPrompt({ topic, seat }: { topic: string; seat: Seat }): string {
  return [
    "你正在参加一个多模型圆桌群聊。请严格以指定席位身份发言，不要跳出角色。",
    seatBlock(seat),
    `本次讨论话题：${topic}`,
    seat.openingPrompt ? `席位自带开场要求：${seat.openingPrompt}` : "",
    "请生成 opening 阶段发言，长度控制在 350 到 800 个中文字符。",
    "要求：明确判断，说明理由，必要时给一个贴近讨论场景的小例子。",
    "避免空泛赞同、复述题目、模板化套话和泛泛抒情。"
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
    "前面 transcript：",
    renderTranscript(transcript),
    "请读取前面 transcript，并对其他席位的具体观点进行回应、反驳、补充或追问。",
    "请生成 debate 阶段发言，长度控制在 350 到 800 个中文字符。",
    "要求：必须点名回应至少一个席位，提出新的区分、反例、现实约束或追问。",
    "不要复述前文，不要只说同意，不要用空泛大词逃避交锋。"
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
