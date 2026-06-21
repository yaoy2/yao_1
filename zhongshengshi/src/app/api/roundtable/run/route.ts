import { NextResponse } from "next/server";
import { assignSeatsToProviders } from "../../../../lib/assignment";
import { createMockProviderClient } from "../../../../lib/mock-provider";
import { createProviderClient } from "../../../../lib/provider-client";
import { buildProviderConfigs } from "../../../../lib/providers";
import { runRoundtable } from "../../../../lib/roundtable";
import type { ModelProvider, Seat, SeatAssignment } from "../../../../lib/types";

interface RoundtableRunBody {
  topic?: string;
  selectedSeats?: Seat[];
  providerAssignments?: SeatAssignment[];
  rounds?: number;
  useMock?: boolean;
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as RoundtableRunBody;
    const topic = body.topic?.trim() ?? "";
    const selectedSeats = Array.isArray(body.selectedSeats) ? body.selectedSeats : [];

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
      rounds: body.rounds ?? 1,
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
