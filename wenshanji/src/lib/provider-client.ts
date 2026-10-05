import { createMockProviderClient } from "./mock-provider";
import { createChatCompletionAdapter, getProviderSecret } from "./providers";
import type { ProviderClient, ProviderGenerateInput, ProviderGenerateResult } from "./roundtable";
import type { ModelProvider } from "./types";

export function createProviderClient(provider: ModelProvider, env: Record<string, string | undefined> = process.env): ProviderClient {
  if (provider.providerType === "mock" || provider.baseUrl.startsWith("mock://")) {
    return createMockProviderClient();
  }

  return {
    async generate(input: ProviderGenerateInput): Promise<ProviderGenerateResult> {
      const apiKey = getProviderSecret(provider.id, env);
      if (!apiKey) {
        throw new Error(`${provider.displayName} 未配置 API Key`);
      }

      const adapter = createChatCompletionAdapter(provider);
      const request = adapter.buildRequest({
        apiKey,
        messages: [{ role: "user", content: input.prompt }]
      });

      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), input.timeoutMs);

      try {
        const response = await fetch(request.url, {
          ...request.init,
          signal: controller.signal
        });

        if (!response.ok) {
          throw new Error(`${provider.displayName} HTTP ${response.status}`);
        }

        const payload = (await response.json()) as {
          choices?: Array<{ message?: { content?: string } }>;
          usage?: { prompt_tokens?: number; completion_tokens?: number };
        };
        const content = payload.choices?.[0]?.message?.content?.trim();
        if (!content) {
          throw new Error(`${provider.displayName} 返回内容为空`);
        }

        return {
          content,
          usage: {
            promptTokens: payload.usage?.prompt_tokens,
            completionTokens: payload.usage?.completion_tokens
          }
        };
      } catch (error) {
        if (error instanceof Error && error.name === "AbortError") {
          throw new Error(`${provider.displayName} 调用超时`);
        }
        throw error;
      } finally {
        clearTimeout(timer);
      }
    }
  };
}
