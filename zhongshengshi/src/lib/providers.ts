import type { ModelProvider, ProviderId } from "./types";

type Env = Record<string, string | undefined>;

interface ProviderDefinition {
  id: ProviderId;
  displayName: string;
  baseUrlKeys: string[];
  modelKeys: string[];
  apiKeyKeys: string[];
}

interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

const providerDefinitions: ProviderDefinition[] = [
  {
    id: "deepseek",
    displayName: "DeepSeek",
    baseUrlKeys: ["DEEPSEEK_BASE_URL"],
    modelKeys: ["DEEPSEEK_MODEL"],
    apiKeyKeys: ["DEEPSEEK_API_KEY"]
  },
  {
    id: "mimo",
    displayName: "MiMo",
    baseUrlKeys: ["MIMO_BASE_URL"],
    modelKeys: ["MIMO_MODEL"],
    apiKeyKeys: ["MIMO_API_KEY"]
  },
  {
    id: "kimi",
    displayName: "Kimi",
    baseUrlKeys: ["KIMI_BASE_URL", "MINIMAX_BASE_URL"],
    modelKeys: ["KIMI_MODEL", "MINIMAX_MODEL"],
    apiKeyKeys: ["KIMI_API_KEY", "MINIMAX_API_KEY"]
  }
];

export function getProviderSecret(providerId: ProviderId, env: Env = process.env): string {
  const definition = providerDefinitions.find((item) => item.id === providerId);
  if (!definition) {
    return "";
  }

  return readFirstEnvValue(env, definition.apiKeyKeys);
}

export function buildProviderConfigs(env: Env = process.env): ModelProvider[] {
  return providerDefinitions.map((definition) => {
    const baseUrl = readFirstEnvValue(env, definition.baseUrlKeys);
    const modelName = readFirstEnvValue(env, definition.modelKeys);
    const apiKey = readFirstEnvValue(env, definition.apiKeyKeys);

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

function readFirstEnvValue(env: Env, keys: string[]): string {
  for (const key of keys) {
    const value = env[key]?.trim();
    if (value) {
      return value;
    }
  }

  return "";
}
