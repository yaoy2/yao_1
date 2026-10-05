import { buildDebatePrompt, buildFreechatPrompt, buildOpeningPrompt } from "./prompt-builder";
import type { ModelProvider, ProviderId, Seat, SeatAssignment } from "./types";

export type RoundtablePhase = "opening" | "debate" | "freechat";
export type RoundtableStatus = "pending" | "running" | "success" | "failed";
export type RoundtableMode = "structured" | "freechat";

export interface RoundtableTranscriptItem {
  id: string;
  round: number;
  phase: RoundtablePhase;
  seatId: string;
  seatName: string;
  providerId: ProviderId;
  providerName: string;
  status: "success" | "failed";
  content: string;
  error?: string;
  createdAt: string;
}

export interface RoundtableError {
  round: number;
  phase: RoundtablePhase;
  seatId: string;
  seatName: string;
  providerId: ProviderId;
  providerName: string;
  message: string;
}

export interface RoundtableProviderStatus {
  providerId: ProviderId;
  providerName: string;
  status: "idle" | "success" | "failed";
  calls: number;
  failures: number;
  promptTokens?: number;
  completionTokens?: number;
}

export interface ProviderGenerateInput {
  topic: string;
  seat: Seat;
  provider: ModelProvider;
  phase: RoundtablePhase;
  round: number;
  prompt: string;
  transcript: RoundtableTranscriptItem[];
  timeoutMs: number;
}

export interface ProviderGenerateResult {
  content: string;
  usage?: {
    promptTokens?: number;
    completionTokens?: number;
  };
}

export interface ProviderClient {
  generate(input: ProviderGenerateInput): Promise<ProviderGenerateResult>;
}

export interface RunRoundtableInput {
  topic: string;
  selectedSeats: Seat[];
  providerAssignments: SeatAssignment[];
  providers: ModelProvider[];
  rounds?: number;
  mode?: RoundtableMode;
  messageBudget?: number;
  timeoutMs?: number;
  providerClientFactory: (provider: ModelProvider) => ProviderClient;
}

export interface RunRoundtableResult {
  status: "success" | "failed";
  transcript: RoundtableTranscriptItem[];
  errors: RoundtableError[];
  providerStatus: RoundtableProviderStatus[];
}

export async function runRoundtable(input: RunRoundtableInput): Promise<RunRoundtableResult> {
  const rounds = Math.max(1, input.rounds ?? 1);
  const timeoutMs = input.timeoutMs ?? 45_000;
  const transcript: RoundtableTranscriptItem[] = [];
  const errors: RoundtableError[] = [];
  const providerStatus = new Map<ProviderId, RoundtableProviderStatus>();

  for (const provider of input.providers) {
    providerStatus.set(provider.id, {
      providerId: provider.id,
      providerName: provider.displayName,
      status: "idle",
      calls: 0,
      failures: 0
    });
  }

  if (input.mode === "freechat") {
    await runFreechat({
      input,
      transcript,
      errors,
      providerStatus,
      timeoutMs,
      messageBudget: input.messageBudget ?? 14
    });

    return {
      status: errors.length ? "failed" : "success",
      transcript,
      errors,
      providerStatus: Array.from(providerStatus.values())
    };
  }

  for (const seat of input.selectedSeats) {
    await runSeatCall({
      topic: input.topic,
      seat,
      phase: "opening",
      round: 1,
      prompt: buildOpeningPrompt({ topic: input.topic, seat }),
      input,
      transcript,
      errors,
      providerStatus,
      timeoutMs
    });
  }

  for (let round = 1; round <= rounds; round += 1) {
    for (const seat of input.selectedSeats) {
      await runSeatCall({
        topic: input.topic,
        seat,
        phase: "debate",
        round,
        prompt: buildDebatePrompt({ topic: input.topic, seat, transcript }),
        input,
        transcript,
        errors,
        providerStatus,
        timeoutMs
      });
    }
  }

  return {
    status: errors.length ? "failed" : "success",
    transcript,
    errors,
    providerStatus: Array.from(providerStatus.values())
  };
}

async function runFreechat({
  input,
  transcript,
  errors,
  providerStatus,
  timeoutMs,
  messageBudget
}: {
  input: RunRoundtableInput;
  transcript: RoundtableTranscriptItem[];
  errors: RoundtableError[];
  providerStatus: Map<ProviderId, RoundtableProviderStatus>;
  timeoutMs: number;
  messageBudget: number;
}) {
  const speakerQueue = planFreechatSpeakers(input.selectedSeats, input.providerAssignments, messageBudget);

  for (let index = 0; index < speakerQueue.length; index += 1) {
    const seat = speakerQueue[index];
    await runSeatCall({
      topic: input.topic,
      seat,
      phase: "freechat",
      round: index + 1,
      prompt: buildFreechatPrompt({
        topic: input.topic,
        seat,
        transcript,
        messageIndex: index + 1,
        totalMessages: speakerQueue.length
      }),
      input,
      transcript,
      errors,
      providerStatus,
      timeoutMs
    });
  }
}

function planFreechatSpeakers(seats: Seat[], providerAssignments: SeatAssignment[], messageBudget: number): Seat[] {
  if (seats.length === 0) {
    return [];
  }

  const activeSeats = selectFreechatActiveSeats(seats, providerAssignments);
  const pattern = [0, 1, 0, 2, 1, 0, 2, 2, 0, 1, 2, 0, 1, 0, 2, 1, 0, 2];

  const speakerQueue: Seat[] = [];

  for (let index = 0; index < messageBudget; index += 1) {
    const preferredIndex = pattern[index % pattern.length] % activeSeats.length;
    const previousSeat = speakerQueue[speakerQueue.length - 1];
    const preferredSeat = activeSeats[preferredIndex];

    if (activeSeats.length > 1 && previousSeat?.id === preferredSeat.id) {
      speakerQueue.push(activeSeats[(preferredIndex + 1) % activeSeats.length]);
    } else {
      speakerQueue.push(preferredSeat);
    }
  }

  return speakerQueue;
}

function selectFreechatActiveSeats(seats: Seat[], providerAssignments: SeatAssignment[]): Seat[] {
  const seatsById = new Map(seats.map((seat) => [seat.id, seat]));
  const providerRepresentatives: Seat[] = [];
  const seenProviders = new Set<ProviderId>();

  for (const assignment of providerAssignments) {
    if (seenProviders.has(assignment.providerId)) {
      continue;
    }

    const seat = seatsById.get(assignment.seatId);
    if (seat) {
      providerRepresentatives.push(seat);
      seenProviders.add(assignment.providerId);
    }
  }

  if (providerRepresentatives.length > 0) {
    return providerRepresentatives;
  }

  const activeSeatCount = Math.max(1, Math.min(seats.length, seats.length > 3 ? seats.length - 1 : seats.length));
  return seats.slice(0, activeSeatCount);
}

async function runSeatCall({
  topic,
  seat,
  phase,
  round,
  prompt,
  input,
  transcript,
  errors,
  providerStatus,
  timeoutMs
}: {
  topic: string;
  seat: Seat;
  phase: RoundtablePhase;
  round: number;
  prompt: string;
  input: RunRoundtableInput;
  transcript: RoundtableTranscriptItem[];
  errors: RoundtableError[];
  providerStatus: Map<ProviderId, RoundtableProviderStatus>;
  timeoutMs: number;
}) {
  const assignment = input.providerAssignments.find((item) => item.seatId === seat.id);
  const provider = assignment ? input.providers.find((item) => item.id === assignment.providerId) : undefined;

  if (!provider) {
    const providerId = assignment?.providerId ?? "deepseek";
    const error = {
      round,
      phase,
      seatId: seat.id,
      seatName: seat.name,
      providerId,
      providerName: providerId,
      message: "没有找到该席位对应的 provider 配置"
    };
    errors.push(error);
    transcript.push(failedTranscriptItem(error));
    return;
  }

  const status = providerStatus.get(provider.id);
  if (status) {
    status.calls += 1;
  }

  try {
    const client = input.providerClientFactory(provider);
    const result = await client.generate({
      topic,
      seat,
      provider,
      phase,
      round,
      prompt,
      transcript: [...transcript],
      timeoutMs: resolveProviderTimeout(provider, timeoutMs)
    });

    if (status) {
      status.status = "success";
      status.promptTokens = (status.promptTokens ?? 0) + (result.usage?.promptTokens ?? 0);
      status.completionTokens = (status.completionTokens ?? 0) + (result.usage?.completionTokens ?? 0);
    }

    transcript.push({
      id: `${phase}-${round}-${seat.id}`,
      round,
      phase,
      seatId: seat.id,
      seatName: seat.name,
      providerId: provider.id,
      providerName: provider.displayName,
      status: "success",
      content: result.content,
      createdAt: new Date().toISOString()
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "未知调用错误";
    const roundtableError = {
      round,
      phase,
      seatId: seat.id,
      seatName: seat.name,
      providerId: provider.id,
      providerName: provider.displayName,
      message
    };

    if (status) {
      status.status = "failed";
      status.failures += 1;
    }

    errors.push(roundtableError);
    transcript.push(failedTranscriptItem(roundtableError));
  }
}

function resolveProviderTimeout(provider: ModelProvider, defaultTimeoutMs: number) {
  if (provider.id === "kimi" && /^kimi-k2\.(7|6|5)/.test(provider.modelName)) {
    return Math.max(defaultTimeoutMs, 90_000);
  }

  return defaultTimeoutMs;
}

function failedTranscriptItem(error: RoundtableError): RoundtableTranscriptItem {
  return {
    id: `${error.phase}-${error.round}-${error.seatId}-failed`,
    round: error.round,
    phase: error.phase,
    seatId: error.seatId,
    seatName: error.seatName,
    providerId: error.providerId,
    providerName: error.providerName,
    status: "failed",
    content: "",
    error: error.message,
    createdAt: new Date().toISOString()
  };
}
