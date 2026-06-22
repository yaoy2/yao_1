import type { ProviderClient, ProviderGenerateInput, ProviderGenerateResult } from "./roundtable";

export function createMockProviderClient(options: { failSeatIds?: string[] } = {}): ProviderClient {
  const failSeatIds = new Set(options.failSeatIds ?? []);

  return {
    async generate(input: ProviderGenerateInput): Promise<ProviderGenerateResult> {
      if (failSeatIds.has(input.seat.id)) {
        throw new Error(`Mock provider failed for ${input.seat.name}`);
      }

      const content = input.phase === "opening" ? buildOpeningSample(input) : buildDebateSample(input);

      return {
        content,
        usage: {
          promptTokens: input.prompt.length,
          completionTokens: Math.ceil(content.length / 2)
        }
      };
    }
  };
}

function buildOpeningSample(input: ProviderGenerateInput): string {
  const concern = input.seat.coreConcern || "这件事的真实收益和真实代价";
  const mustDo = input.seat.mustDo || "把判断落到具体对象、具体成本和具体收益";
  const mustNotDo = input.seat.mustNotDo || "不要用漂亮口号代替判断";
  const question = input.seat.typicalQuestions[0] || "谁真正受益，谁承担代价？";

  return [
    `我的判断：这个问题不能按“参赛就是好事”处理，必须先看${concern}。`,
    `站在「${input.seat.name}」这个席位，我会把重点放在一笔具体账上：学生投入的时间、教师指导精力、竞赛结果能否转化为作品、简历材料或专业能力。`,
    `如果收益只是多一项活动经历，却挤掉专业作业、实习准备和必要休息，那就是弊大；如果能被限定为小规模试水，并且产出可复用作品或表达训练，才可能利大。`,
    `所以我会坚持一条边界：${mustDo}；同时避免${mustNotDo}。`,
    `我想先追问：${question}这个问题如果答不清，圆桌就不该急着给“鼓励参加”的结论。`
  ].join("");
}

function buildDebateSample(input: ProviderGenerateInput): string {
  const target = findPriorTarget(input);
  const concern = input.seat.coreConcern || "当前方案是否真的可执行";
  const question = input.seat.typicalQuestions[0] || "这个判断如何落到学生和教师的真实安排上？";

  return [
    `我回应「${target.seatName}」刚才的观点：${target.summary}`,
    `这个说法有价值，但从「${input.seat.name}」的角度看，还少了一道筛选条件：不能只证明竞赛“可能有用”，还要证明它对这批学生、这个专业阶段、这段时间窗口值得投入。`,
    `我的分歧是，${concern}如果没有被量化，所谓机会就会变成额外任务。比如同样是低相关竞赛，能形成作品集素材和表达训练的，可以作为自愿试点；只能换来参与截图和新闻稿素材的，就应该果断压缩。`,
    `因此我补充一个判断标准：先设退出线和复盘线，再谈鼓励参与。`,
    `我追问一句：${question}如果回答仍然停留在“综合看有意义”，那就还没有进入真正的决策。`
  ].join("");
}

function findPriorTarget(input: ProviderGenerateInput): { seatName: string; summary: string } {
  const prior = [...input.transcript].reverse().find((item) => item.status === "success" && item.seatId !== input.seat.id);
  if (!prior) {
    return {
      seatName: "前一位席位",
      summary: "需要把抽象判断落到可执行的标准上。"
    };
  }

  return {
    seatName: prior.seatName,
    summary: summarize(prior.content)
  };
}

function summarize(content: string): string {
  const normalized = content.replace(/\s+/g, "");
  return normalized.length > 52 ? `${normalized.slice(0, 52)}...` : normalized;
}
