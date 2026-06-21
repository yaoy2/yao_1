import type { ModelProvider, ProviderId } from "./types";

type Env = Record<string, string | undefined>;

interface ProviderDefinition {
  id: ProviderId;
  displayName: string;
  baseUrlKey: string;
  modelKey: string;
  apiKeyKey: string;
}

interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

const providerDefinitions: ProviderDefinition[] = [
  {
    id: "deepseek",
    displayName: "DeepSeek",
    baseUrlKey: "DEEPSEEK_BASE_URL",
    modelKey: "DEEPSEEK_MODEL",
    apiKeyKey: "DEEPSEEK_API_KEY"
  },
  {
    id: "mimo",
    displayName: "MiMo",
    baseUrlKey: "MIMO_BASE_URL",
    modelKey: "MIMO_MODEL",
    apiKeyKey: "MIMO_API_KEY"
  },
  {
    id: "minimax",
    displayName: "MiniMax",
    baseUrlKey: "MINIMAX_BASE_URL",
    modelKey: "MINIMAX_MODEL",
    apiKeyKey: "MINIMAX_API_KEY"
  }
];

export function getProviderSecret(providerId: ProviderId, env: Env = process.env): string {
  const definition = providerDefinitions.find((item) => item.id === providerId);
  if (!definition) {
    return "";
  }

  return env[definition.apiKeyKey]?.trim() ?? "";
}

export function buildProviderConfigs(env: Env = process.env): ModelProvider[] {
  return providerDefinitions.map((definition) => {
    const baseUrl = env[definition.baseUrlKey]?.trim() ?? "";
    const modelName = env[definition.modelKey]?.trim() ?? "";
    const apiKey = env[definition.apiKeyKey]?.trim() ?? "";

    return {
      id: definition.id,
      displayName: definition.displayName,
      baseUrl,
      modelName,
      providerType: "openai-compatible",
      isConfigured: Boolean(baseUrl && modelName && apiKey)
    };
  });
}

export function createChatCompletionAdapter(provider: ModelProvider) {
  return {
    buildRequest({ apiKey, messages, temperature = 0.7 }: { apiKey: string; messages: ChatMessage[]; temperature?: number }) {
      return {
        url: `${provider.baseUrl.replace(/\/$/, "")}/chat/completions`,
        init: {
          method: "POST",
          headers: {
            Authorization: `Bearer ${apiKey}`,
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            model: provider.modelName,
            messages,
            temperature
          })
        }
      };
    }
  };
}
