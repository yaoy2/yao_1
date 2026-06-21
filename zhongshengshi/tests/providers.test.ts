import { describe, expect, it } from "vitest";
import { buildProviderConfigs, createChatCompletionAdapter } from "../src/lib/providers";

describe("buildProviderConfigs", () => {
  it("builds provider metadata from environment variables without exposing api keys", () => {
    const providers = buildProviderConfigs({
      DEEPSEEK_API_KEY: "secret-deepseek",
      DEEPSEEK_BASE_URL: "https://api.deepseek.example",
      DEEPSEEK_MODEL: "deepseek-chat",
      MIMO_BASE_URL: "https://api.mimo.example",
      MIMO_MODEL: "mimo-chat"
    });

    expect(providers[0]).toMatchObject({
      id: "deepseek",
      displayName: "DeepSeek",
      baseUrl: "https://api.deepseek.example",
      modelName: "deepseek-chat",
      providerType: "openai-compatible",
      isConfigured: true
    });
    expect(providers[0]).not.toHaveProperty("apiKey");
    expect(providers.find((item) => item.id === "mimo")?.isConfigured).toBe(false);
  });
});

describe("createChatCompletionAdapter", () => {
  it("creates an OpenAI-compatible request shape", () => {
    const adapter = createChatCompletionAdapter({
      id: "deepseek",
      displayName: "DeepSeek",
      baseUrl: "https://api.deepseek.example",
      modelName: "deepseek-chat",
      providerType: "openai-compatible",
      isConfigured: true
    });

    expect(
      adapter.buildRequest({
        apiKey: "secret",
        messages: [{ role: "user", content: "你好" }]
      })
    ).toEqual({
      url: "https://api.deepseek.example/chat/completions",
      init: {
        method: "POST",
        headers: {
          Authorization: "Bearer secret",
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          model: "deepseek-chat",
          messages: [{ role: "user", content: "你好" }],
          temperature: 0.7
        })
      }
    });
  });
});
