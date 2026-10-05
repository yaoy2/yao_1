import { NextResponse } from "next/server";
import { assignSeatsToProviders } from "../../../../lib/assignment";
import { createMockProviderClient } from "../../../../lib/mock-provider";
import { createProviderClient } from "../../../../lib/provider-client";
import { buildProviderConfigs } from "../../../../lib/providers";
import { runRoundtable, type RoundtableMode } from "../../../../lib/roundtable";
import type { ModelProvider, Seat, SeatAssignment } from "../../../../lib/types";

interface RoundtableRunBody {
  topic?: string;
  selectedSeats?: Seat[];
  providerAssignments?: SeatAssignment[];
  rounds?: number;
  mode?: RoundtableMode;
  messageBudget?: number;
  useMock?: boolean;
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as RoundtableRunBody;
    if (!body || typeof body !== "object" || Array.isArray(body)) {
      return NextResponse.json({ error: "请求内容必须是对象。" }, { status: 400 });
    }
    const topic = typeof body.topic === "string" ? body.topic.trim() : "";
    const selectedSeats = Array.isArray(body.selectedSeats) ? body.selectedSeats : [];
    const rounds = body.rounds === undefined ? 1 : body.rounds;
    const messageBudget = body.messageBudget === undefined ? 14 : body.messageBudget;

    if (!Number.isInteger(rounds) || rounds < 1 || rounds > 3 ||
        !Number.isInteger(messageBudget) || messageBudget < 1 || messageBudget > 24) {
      return NextResponse.json({ error: "轮数须为 1–3 的整数，消息预算须为 1–24 的整数。" }, { status: 400 });
    }
    if (body.mode !== undefined && body.mode !== "structured" && body.mode !== "freechat") {
      return NextResponse.json({ error: "讨论模式无效。" }, { status: 400 });
    }

    if (!topic) {
      return NextResponse.json({ error: "请先输入讨论话题。" }, { status: 400 });
    }
    if (selectedSeats.length < 4 || selectedSeats.length > 6) {
      return NextResponse.json({ error: "请选择 4 到 6 个席位。" }, { status: 400 });
    }

    const providers = body.useMock ? buildMockProviders() : buildProviderConfigs(process.env);
    const providerAssignments = body.providerAssignments?.length ? body.providerAssignments : assignSeatsToProviders(selectedSeats);

    const result = await runRoundtable({
      topic,
      selectedSeats,
      providerAssignments,
      providers,
      mode: body.mode ?? "structured",
      messageBudget,
      rounds,
      providerClientFactory: (provider) => (body.useMock ? createMockProviderClient() : createProviderClient(provider, process.env))
    });

    return NextResponse.json(result);
  } catch (error) {
    return NextResponse.json(
      {
        status: "failed",
        transcript: [],
        errors: [
          {
            round: 0,
            phase: "opening",
            seatId: "",
            seatName: "",
            providerId: "deepseek",
            providerName: "",
            message: error instanceof Error ? error.message : "圆桌运行失败"
          }
        ],
        providerStatus: []
      },
      { status: 500 }
    );
  }
}

function buildMockProviders(): ModelProvider[] {
  return [
    {
      id: "deepseek",
      displayName: "DeepSeek Mock",
      baseUrl: "mock://deepseek",
      modelName: "mock-deepseek",
      providerType: "mock",
      isConfigured: true
    },
    {
      id: "mimo",
      displayName: "MiMo Mock",
      baseUrl: "mock://mimo",
      modelName: "mock-mimo",
      providerType: "mock",
      isConfigured: true
    },
    {
      id: "kimi",
      displayName: "Kimi Mock",
      baseUrl: "mock://kimi",
      modelName: "mock-kimi",
      providerType: "mock",
      isConfigured: true
    }
  ];
}
