import type { ProviderClient, ProviderGenerateInput, ProviderGenerateResult } from "./roundtable";

export function createMockProviderClient(options: { failSeatIds?: string[] } = {}): ProviderClient {
  const failSeatIds = new Set(options.failSeatIds ?? []);

  return {
    async generate(input: ProviderGenerateInput): Promise<ProviderGenerateResult> {
      if (failSeatIds.has(input.seat.id)) {
        throw new Error(`Mock provider failed for ${input.seat.name}`);
      }

      const action =
        input.phase === "opening"
          ? "先给出基本判断，并说明这个席位为什么这样看"
          : "回应前面席位的观点，提出一个新的区分或追问";

      return {
        content: `【Mock ${input.provider.displayName}｜${input.seat.name}｜${input.phase}】围绕“${input.topic}”，我会${action}。我的核心关切是${input.seat.coreConcern || "当前讨论的关键约束"}。这是一段用于本地验证的圆桌发言，证明 prompt、席位分配、错误处理和 transcript 展示链路已经连通。`,
        usage: {
          promptTokens: input.prompt.length,
          completionTokens: 80
        }
      };
    }
  };
}
