export type ProviderId = "deepseek" | "mimo" | "minimax";

export type ProviderType = "openai-compatible";

export interface Topic {
  id: string;
  title: string;
  createdAt: string;
}

export interface Room {
  id: string;
  topicId: string;
  title: string;
  status: "draft" | "ready" | "running" | "paused" | "finished";
  createdAt: string;
}

export interface Seat {
  id: string;
  name: string;
  type: string;
  coreConcern: string;
  typicalQuestions: string[];
  mustDo: string;
  mustNotDo: string;
  likelyOpponents: string[];
  blindSpots: string[];
  speakingStyle: string;
  examplePreference: string;
  openingPrompt: string;
  debatePrompt: string;
}

export interface ModelProvider {
  id: ProviderId;
  displayName: string;
  baseUrl: string;
  modelName: string;
  providerType: ProviderType;
  isConfigured: boolean;
}

export interface SeatAssignment {
  id: string;
  seatId: string;
  providerId: ProviderId;
  reason: string;
}

export interface Message {
  id: string;
  roomId: string;
  speakerType: "user" | "seat" | "system";
  seatId?: string;
  modelProviderId?: ProviderId;
  phase: "opening" | "debate" | "missing_view" | "summary";
  content: string;
  replyToSeatId?: string;
  createdAt: string;
}

export interface RoundState {
  roomId: string;
  phase: "draft" | "opening" | "debate" | "missing_view" | "summary";
  roundNumber: number;
  activeSeats: string[];
  speakerQueue: string[];
  maxMessages: number;
  status: "draft" | "ready" | "running" | "paused" | "finished";
}

export interface Summary {
  id: string;
  roomId: string;
  content: string;
  createdAt: string;
}
