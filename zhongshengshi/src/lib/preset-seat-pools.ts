import lowRelevanceCompetition from "../presets/low_relevance_competition.json";

export interface CompactSeatPreset {
  topic: string;
  seats: Array<{
    id?: string;
    seat_name: string;
    type: string;
    core_concern: string;
    typical_questions: string[];
    must_do: string;
    must_not_do: string;
    speaking_style: string;
  }>;
}

export const lowRelevanceCompetitionPreset = lowRelevanceCompetition as CompactSeatPreset;

export function getPresetSeatPoolText(preset: CompactSeatPreset): string {
  return JSON.stringify({ seats: preset.seats }, null, 2);
}
