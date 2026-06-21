import { describe, expect, it } from "vitest";
import { POST } from "../src/app/api/roundtable/run/route";
import { assignSeatsToProviders } from "../src/lib/assignment";
import type { Seat } from "../src/lib/types";

const seats: Seat[] = Array.from({ length: 4 }, (_, index) => ({
  id: `s${index + 1}`,
  name: `测试席位${index + 1}`,
  type: "mock",
  coreConcern: "测试圆桌链路",
  typicalQuestions: ["如何测试？"],
  mustDo: "返回可读内容",
  mustNotDo: "不要泄露密钥",
  likelyOpponents: [],
  blindSpots: [],
  speakingStyle: "简洁",
  examplePreference: "本地测试",
  openingPrompt: "",
  debatePrompt: ""
}));

describe("POST /api/roundtable/run", () => {
  it("returns transcript and provider status without api keys when mock mode is used", async () => {
    const request = new Request("http://localhost/api/roundtable/run", {
      method: "POST",
      body: JSON.stringify({
        topic: "测试话题",
        selectedSeats: seats,
        providerAssignments: assignSeatsToProviders(seats),
        rounds: 1,
        useMock: true
      })
    });

    const response = await POST(request);
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.transcript).toHaveLength(8);
    expect(JSON.stringify(payload)).not.toContain("API_KEY");
    expect(JSON.stringify(payload)).not.toContain("secret");
    expect(payload.providerStatus.length).toBeGreaterThan(0);
  });
});
