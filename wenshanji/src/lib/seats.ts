import type { Seat } from "./types";

type RawSeat = Record<string, unknown>;

const arrayKeys = ["seats", "席位池", "候选席位", "seatPool", "candidates"];

export function parseSeatPool(input: string): Seat[] {
  let parsed: unknown;

  try {
    parsed = JSON.parse(input);
  } catch {
    throw new Error("席位池不是合法 JSON，请检查复制内容是否完整。");
  }

  const rawSeats = findSeatArray(parsed);
  if (!rawSeats) {
    throw new Error("没有找到席位数组，请使用 seats、席位池或候选席位作为数组字段。");
  }

  const seats = rawSeats.map(normalizeSeat).filter((seat) => seat.name && seat.coreConcern);
  if (seats.length === 0) {
    throw new Error("席位池里没有可识别的席位，请确认每个席位至少包含名称和核心关切。");
  }

  return seats;
}

export function validateSeatSelection(selectedSeatIds: string[]): { ok: true } | { ok: false; message: string } {
  if (selectedSeatIds.length < 4 || selectedSeatIds.length > 6) {
    return { ok: false, message: "请选择 4 到 6 个席位进入本局。" };
  }

  return { ok: true };
}

function findSeatArray(value: unknown): RawSeat[] | null {
  if (Array.isArray(value)) {
    return value.filter(isRawSeat);
  }

  if (!isRawSeat(value)) {
    return null;
  }

  for (const key of arrayKeys) {
    const candidate = value[key];
    if (Array.isArray(candidate)) {
      return candidate.filter(isRawSeat);
    }
  }

  return null;
}

function normalizeSeat(raw: RawSeat, index: number): Seat {
  const name = text(raw, ["name", "seat_name", "seatName", "席位名称", "名称", "席位"]);

  return {
    id: text(raw, ["id", "seat_id", "seatId"]) || `seat-${index + 1}`,
    name,
    type: text(raw, ["type", "seat_type", "seatType", "席位类型", "类型"]),
    coreConcern: text(raw, ["coreConcern", "core_concern", "核心关切", "关切"]),
    typicalQuestions: list(raw, ["typicalQuestions", "typical_questions", "典型问题"]),
    mustDo: text(raw, ["mustDo", "must_do", "应当做", "应该做"]),
    mustNotDo: text(raw, ["mustNotDo", "must_not_do", "应当避免", "不应做"]),
    likelyOpponents: list(raw, ["likelyOpponents", "likely_opponents", "可能反驳对象", "可能反驳谁"]),
    blindSpots: list(raw, ["blindSpots", "blind_spots", "典型盲点", "盲点"]),
    speakingStyle: text(raw, ["speakingStyle", "speaking_style", "发言风格"]),
    examplePreference: text(raw, ["examplePreference", "example_preference", "例子偏好"]),
    openingPrompt: text(raw, ["openingPrompt", "opening_prompt", "开场提示词"]),
    debatePrompt: text(raw, ["debatePrompt", "debate_prompt", "交锋提示词"])
  };
}

function text(raw: RawSeat, keys: string[]): string {
  for (const key of keys) {
    const value = raw[key];
    if (typeof value === "string") {
      return value.trim();
    }
    if (Array.isArray(value)) {
      return value.map(String).join("；").trim();
    }
  }

  return "";
}

function list(raw: RawSeat, keys: string[]): string[] {
  for (const key of keys) {
    const value = raw[key];
    if (Array.isArray(value)) {
      return value.map(String).map((item) => item.trim()).filter(Boolean);
    }
    if (typeof value === "string") {
      return value
        .split(/[；;、,\n]/)
        .map((item) => item.trim())
        .filter(Boolean);
    }
  }

  return [];
}

function isRawSeat(value: unknown): value is RawSeat {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
