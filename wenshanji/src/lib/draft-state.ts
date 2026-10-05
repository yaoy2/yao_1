import type { Seat, SeatAssignment } from "./types";

export const roundtableDraftStorageKey = "zhongshengshi:roundtable-draft:v1";

export interface RoundtableDraftState {
  topic: string;
  seatPoolText: string;
  seats: Seat[];
  selectedSeatIds: string[];
  assignments: SeatAssignment[];
  useMock: boolean;
  showSeatPoolEditor: boolean;
}

export function serializeRoundtableDraft(draft: RoundtableDraftState): string {
  return JSON.stringify(draft);
}

export function parseRoundtableDraft(raw: string | null): RoundtableDraftState | null {
  if (!raw) {
    return null;
  }

  try {
    const parsed = JSON.parse(raw) as Partial<RoundtableDraftState>;
    if (
      typeof parsed.topic !== "string" ||
      typeof parsed.seatPoolText !== "string" ||
      !Array.isArray(parsed.seats) ||
      !Array.isArray(parsed.selectedSeatIds) ||
      !Array.isArray(parsed.assignments) ||
      typeof parsed.useMock !== "boolean" ||
      typeof parsed.showSeatPoolEditor !== "boolean"
    ) {
      return null;
    }

    return {
      topic: parsed.topic,
      seatPoolText: parsed.seatPoolText,
      seats: parsed.seats,
      selectedSeatIds: parsed.selectedSeatIds.filter((id): id is string => typeof id === "string"),
      assignments: parsed.assignments,
      useMock: parsed.useMock,
      showSeatPoolEditor: parsed.showSeatPoolEditor
    };
  } catch {
    return null;
  }
}
