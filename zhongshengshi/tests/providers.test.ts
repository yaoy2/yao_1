import { describe, expect, it } from "vitest";
import { buildProviderConfigs, createChatCompletionAdapter } from "../src/lib/providers";

describe("buildProviderConfigs", () => {
  it("builds provider metadata from environment variables without exposing api keys", () => {
    const providers = buildProviderConfigs({
      DEEPSEEK_API_KEY: "secret-deepseek",
      DEEPSEEK_BASE_URL: "https://api.deepseek.example",
      DEEPSEEK_MODEL: "deepseek-chat",
      KIMI_API_KEY: "secret-kimi",
      KIMI_BASE_URL: "https://api.kimi.example",
      KIMI_MODEL: "kimi-k2",
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
    expect(providers.find((item) => item.id === "kimi")).toMatchObject({
      displayName: "Kimi",
      baseUrl: "https://api.kimi.example",
      modelName: "kimi-k2",
      isConfigured: true
    });
    expect(providers.find((item) => item.id === "mimo")?.isConfigured).toBe(false);
  });

  it("keeps legacy MINIMAX environment names as a Kimi fallback", () => {
    const providers = buildProviderConfigs({
      MINIMAX_API_KEY: "legacy-secret",
      MINIMAX_BASE_URL: "https://api.kimi-legacy.example",
      MINIMAX_MODEL: "kimi-legacy"
    });

    expect(providers.find((item) => item.id === "kimi")).toMatchObject({
      displayName: "Kimi",
      baseUrl: "https://api.kimi-legacy.example",
      modelName: "kimi-legacy",
      isConfigured: true
    });
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

  it("omits temperature for Kimi K2.7 Code because the API rejects non-default values", () => {
    const adapter = createChatCompletionAdapter({
      id: "kimi",
      displayName: "Kimi",
      baseUrl: "https://api.moonshot.cn/v1",
      modelName: "kimi-k2.7-code",
      providerType: "openai-compatible",
      isConfigured: true
    });

    const request = adapter.buildRequest({
      apiKey: "secret",
      messages: [{ role: "user", content: "hello" }]
    });
    const body = JSON.parse(request.init.body);

    expect(body).toEqual({
      model: "kimi-k2.7-code",
      messages: [{ role: "user", content: "hello" }]
    });
    expect(body).not.toHaveProperty("temperature");
  });
});
