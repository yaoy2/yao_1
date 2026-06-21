import type { ProviderId, Seat, SeatAssignment } from "./types";

const providerOrder: ProviderId[] = ["deepseek", "minimax", "mimo"];

const preferenceKeywords: Record<ProviderId, string[]> = {
  deepseek: ["逻辑", "拆解", "现实", "批判", "制度", "分析", "反驳", "治理", "结构"],
  minimax: ["伦理", "人际", "角色", "叙事", "长文", "表达", "情感", "关系", "感受"],
  mimo: ["方案", "工程", "实务", "推理", "操作", "流程", "执行", "改良", "步骤"]
};

export function assignSeatsToProviders(seats: Seat[]): SeatAssignment[] {
  const counts = new Map<ProviderId, number>(providerOrder.map((id) => [id, 0]));

  return seats.map((seat, index) => {
    const providerId = chooseProvider(seat, counts);
    counts.set(providerId, (counts.get(providerId) ?? 0) + 1);

    return {
      id: `assignment-${index + 1}`,
      seatId: seat.id,
      providerId,
      reason: buildReason(seat, providerId)
    };
  });
}

function chooseProvider(seat: Seat, counts: Map<ProviderId, number>): ProviderId {
  const scored = providerOrder
    .filter((providerId) => (counts.get(providerId) ?? 0) < 2)
    .map((providerId) => ({
      providerId,
      score: scoreSeatForProvider(seat, providerId),
      count: counts.get(providerId) ?? 0
    }))
    .sort((a, b) => b.score - a.score || a.count - b.count || providerOrder.indexOf(a.providerId) - providerOrder.indexOf(b.providerId));

  const top = scored[0];
  if (!top) {
    throw new Error("所选席位超过当前 3 个模型可承载上限，请最多选择 6 个席位。");
  }

  if (top.score === 0) {
    return [...scored].sort((a, b) => a.count - b.count || providerOrder.indexOf(a.providerId) - providerOrder.indexOf(b.providerId))[0].providerId;
  }

  return top.providerId;
}

function scoreSeatForProvider(seat: Seat, providerId: ProviderId): number {
  const haystack = [seat.name, seat.type, seat.coreConcern, seat.mustDo, seat.speakingStyle].join(" ");
  return preferenceKeywords[providerId].reduce((score, keyword) => score + (haystack.includes(keyword) ? 1 : 0), 0);
}

function buildReason(seat: Seat, providerId: ProviderId): string {
  const providerName = {
    deepseek: "DeepSeek",
    mimo: "MiMo",
    minimax: "MiniMax"
  }[providerId];

  return `${providerName} 与「${seat.name}」的类型和核心关切匹配；同时保持每个模型最多 2 个席位。`;
}
