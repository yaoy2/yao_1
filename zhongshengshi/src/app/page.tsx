"use client";

import { useEffect, useState } from "react";
import { assignSeatsToProviders } from "@/lib/assignment";
import { parseRoundtableDraft, roundtableDraftStorageKey, serializeRoundtableDraft } from "@/lib/draft-state";
import { projectGuideSections } from "@/lib/guide";
import { getPresetSeatPoolText, lowRelevanceCompetitionPreset } from "@/lib/preset-seat-pools";
import { parseSeatPool, validateSeatSelection } from "@/lib/seats";
import type { RoundtableError, RoundtableProviderStatus, RoundtableStatus, RoundtableTranscriptItem } from "@/lib/roundtable";
import type { ModelProvider, Seat, SeatAssignment } from "@/lib/types";

const sampleSeatPool = JSON.stringify(
  {
    seats: [
      {
        id: "s1",
        "席位名称": "基层教师现实主义",
        "席位类型": "现实批判",
        "核心关切": "行政任务如何挤压真实教学",
        "典型问题": ["谁承担额外劳动？", "制度压力如何传导到课堂？"],
        "可能反驳对象": ["古典教育伦理"],
        "典型盲点": ["容易低估长期教育理想"],
        "发言风格": "直接、具体、有现场感"
      },
      {
        id: "s2",
        "席位名称": "古典教育伦理",
        "席位类型": "伦理叙事",
        "核心关切": "教育是否仍然守住人的完整成长",
        "可能反驳对象": ["绩效主义管理者"],
        "典型盲点": ["容易忽略行政资源约束"],
        "发言风格": "稳重、价值导向"
      },
      {
        id: "s3",
        "席位名称": "制度分析者",
        "席位类型": "制度分析",
        "核心关切": "责任、权力与激励如何错位",
        "可能反驳对象": ["单纯情绪化批判"],
        "典型盲点": ["可能低估个体情绪"],
        "发言风格": "结构化、冷静"
      },
      {
        id: "s4",
        "席位名称": "工程实务派",
        "席位类型": "方案工程",
        "核心关切": "如何把讨论变成可执行流程",
        "可能反驳对象": ["只提出价值判断者"],
        "典型盲点": ["可能过度工具化"],
        "发言风格": "步骤清楚、可落地"
      }
    ]
  },
  null,
  2
);

interface RoundtableRunResponse {
  status: "success" | "failed";
  transcript: RoundtableTranscriptItem[];
  errors: RoundtableError[];
  providerStatus: RoundtableProviderStatus[];
}

export default function Home() {
  const [topic, setTopic] = useState("");
  const [seatPoolText, setSeatPoolText] = useState(sampleSeatPool);
  const [seats, setSeats] = useState<Seat[]>([]);
  const [selectedSeatIds, setSelectedSeatIds] = useState<string[]>([]);
  const [assignments, setAssignments] = useState<SeatAssignment[]>([]);
  const [providers, setProviders] = useState<ModelProvider[]>([]);
  const [message, setMessage] = useState("");
  const [showSeatPoolEditor, setShowSeatPoolEditor] = useState(true);
  const [useMock, setUseMock] = useState(true);
  const [runStatus, setRunStatus] = useState<RoundtableStatus>("pending");
  const [transcript, setTranscript] = useState<RoundtableTranscriptItem[]>([]);
  const [errors, setErrors] = useState<RoundtableError[]>([]);
  const [providerStatus, setProviderStatus] = useState<RoundtableProviderStatus[]>([]);
  const [hasLoadedDraft, setHasLoadedDraft] = useState(false);

  const selectedSeats = seats.filter((seat) => selectedSeatIds.includes(seat.id));
  const configuredProviderCount = providers.filter((provider) => provider.isConfigured).length;
  const activeAssignments = assignments.length ? assignments : assignSeatsToProviders(selectedSeats);

  useEffect(() => {
    const savedDraft = parseRoundtableDraft(window.localStorage.getItem(roundtableDraftStorageKey));
    if (savedDraft) {
      setTopic(savedDraft.topic);
      setSeatPoolText(savedDraft.seatPoolText);
      setSeats(savedDraft.seats);
      setSelectedSeatIds(savedDraft.selectedSeatIds);
      setAssignments(savedDraft.assignments);
      setUseMock(savedDraft.useMock);
      setShowSeatPoolEditor(savedDraft.showSeatPoolEditor);
      setMessage("已恢复上次未完成的圆桌草稿。");
    }
    setHasLoadedDraft(true);
  }, []);

  useEffect(() => {
    fetch("/api/providers")
      .then((response) => response.json())
      .then((data: { providers: ModelProvider[] }) => setProviders(data.providers))
      .catch(() => setMessage("模型配置状态读取失败，请检查本地服务。"));
  }, []);

  useEffect(() => {
    if (!hasLoadedDraft) {
      return;
    }

    window.localStorage.setItem(
      roundtableDraftStorageKey,
      serializeRoundtableDraft({
        topic,
        seatPoolText,
        seats,
        selectedSeatIds,
        assignments,
        useMock,
        showSeatPoolEditor
      })
    );
  }, [assignments, hasLoadedDraft, seats, seatPoolText, selectedSeatIds, showSeatPoolEditor, topic, useMock]);

  function handleParseSeats() {
    try {
      const parsed = parseSeatPool(seatPoolText);
      setSeats(parsed);
      setSelectedSeatIds([]);
      setAssignments([]);
      setTranscript([]);
      setErrors([]);
      setProviderStatus([]);
      setRunStatus("pending");
      setShowSeatPoolEditor(false);
      setMessage(`已解析 ${parsed.length} 个候选席位。`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "席位池解析失败。");
    }
  }

  function handleLoadPresetSeatPool() {
    const nextSeatPoolText = getPresetSeatPoolText(lowRelevanceCompetitionPreset);
    const parsed = parseSeatPool(nextSeatPoolText);

    setTopic(lowRelevanceCompetitionPreset.topic);
    setSeatPoolText(nextSeatPoolText);
    setSeats(parsed);
    setSelectedSeatIds([]);
    setAssignments([]);
    setTranscript([]);
    setErrors([]);
    setProviderStatus([]);
    setRunStatus("pending");
    setShowSeatPoolEditor(false);
    setMessage(`已载入示例席位池：${parsed.length} 个短席位。`);
  }

  function toggleSeat(seatId: string) {
    setSelectedSeatIds((current) => {
      if (current.includes(seatId)) {
        return current.filter((id) => id !== seatId);
      }
      if (current.length >= 6) {
        setMessage("最多选择 6 个席位。");
        return current;
      }
      return [...current, seatId];
    });
  }

  function handleAssignSeats() {
    const selection = validateSeatSelection(selectedSeatIds);
    if (!selection.ok) {
      setMessage(selection.message);
      return;
    }

    const nextAssignments = assignSeatsToProviders(selectedSeats);
    setAssignments(nextAssignments);
    setMessage("已生成席位分配。");
  }

  async function handleStartRoundtable() {
    const selection = validateBeforeRun();
    if (!selection.ok) {
      setMessage(selection.message);
      return;
    }

    const nextAssignments = assignments.length ? assignments : assignSeatsToProviders(selectedSeats);
    setAssignments(nextAssignments);
    window.localStorage.setItem(
      roundtableDraftStorageKey,
      serializeRoundtableDraft({
        topic,
        seatPoolText,
        seats,
        selectedSeatIds,
        assignments: nextAssignments,
        useMock,
        showSeatPoolEditor
      })
    );
    setRunStatus("running");
    setTranscript([]);
    setErrors([]);
    setProviderStatus([]);
    setMessage("自由圆桌运行中：短消息接话、反驳、补充和追问。");

    try {
      const response = await fetch("/api/roundtable/run", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          topic,
          selectedSeats,
          providerAssignments: nextAssignments,
          mode: "freechat",
          messageBudget: 14,
          rounds: 1,
          useMock
        })
      });

      const payload = (await response.json()) as RoundtableRunResponse | { error?: string };
      if (!response.ok) {
        throw new Error("error" in payload && payload.error ? payload.error : "圆桌运行失败。");
      }

      const result = payload as RoundtableRunResponse;
      setTranscript(result.transcript);
      setErrors(result.errors);
      setProviderStatus(result.providerStatus);
      setRunStatus(result.status);
      setMessage(result.status === "success" ? "自由圆桌已完成。" : "自由圆桌已完成，但部分席位调用失败。");
    } catch (error) {
      setRunStatus("failed");
      setMessage(error instanceof Error ? error.message : "圆桌运行失败。");
    }
  }

  function validateBeforeRun(): { ok: true } | { ok: false; message: string } {
    if (!topic.trim()) {
      return { ok: false, message: "请先输入讨论话题。" };
    }

    const selection = validateSeatSelection(selectedSeatIds);
    if (!selection.ok) {
      return selection;
    }

    if (!useMock && configuredProviderCount < 2) {
      return { ok: false, message: "真实运行至少需要配置 2 个可用模型；本地验证可以先打开 mock provider。" };
    }

    return { ok: true };
  }

  return (
    <main className="min-h-screen bg-mist px-4 py-5 text-ink md:px-8">
      <div className="mx-auto flex max-w-7xl flex-col gap-4">
        <header className="flex flex-wrap items-end justify-between gap-3 border-b border-ink/10 pb-4">
          <div>
            <p className="text-sm font-semibold text-rust">本地 MVP · 最小圆桌链路</p>
            <h1 className="text-3xl font-bold">众声室</h1>
          </div>
          <div className="text-sm text-ink/70">自由讨论 · 短消息流</div>
        </header>

        <Panel title="项目说明书 / 使用指南">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            {projectGuideSections.map((section) => (
              <section key={section.title} className="rounded border border-ink/10 bg-paper p-3">
                <h3 className="mb-2 text-sm font-semibold text-moss">{section.title}</h3>
                <ol className="space-y-1 pl-4 text-sm leading-6 text-ink/75">
                  {section.items.map((item) => (
                    <li key={item} className="list-decimal">
                      {item}
                    </li>
                  ))}
                </ol>
              </section>
            ))}
          </div>
        </Panel>

        <section className="grid gap-4 lg:grid-cols-[1fr_1.1fr]">
          <Panel title="话题输入">
            <textarea
              className="h-28 w-full resize-none rounded border border-ink/15 bg-paper p-3 text-sm outline-none focus:border-moss"
              placeholder="输入本次圆桌讨论的话题"
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
            />
          </Panel>

          <Panel title="席位池">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <button type="button" className="rounded bg-moss px-4 py-2 text-sm font-semibold text-white" onClick={handleLoadPresetSeatPool}>
                载入示例席位池
              </button>
              <button type="button" className="rounded border border-ink/15 bg-paper px-4 py-2 text-sm" onClick={() => setShowSeatPoolEditor((current) => !current)}>
                {showSeatPoolEditor ? "收起 JSON" : "编辑/粘贴 JSON"}
              </button>
              <span className="text-sm text-ink/60">支持 compact seats 数组，不需要粘贴完整 12 席位长 JSON。</span>
            </div>
            {showSeatPoolEditor ? (
              <textarea
                className="h-52 w-full resize-none rounded border border-ink/15 bg-paper p-3 font-mono text-xs outline-none focus:border-moss"
                value={seatPoolText}
                onChange={(event) => setSeatPoolText(event.target.value)}
              />
            ) : (
              <div className="rounded border border-dashed border-ink/20 bg-paper p-3 text-sm text-ink/65">
                JSON 已收起。解析后请在下方席位卡片中查看和选择；需要修改时点击“编辑/粘贴 JSON”。
              </div>
            )}
            <div className="mt-3 flex items-center gap-3">
              <button type="button" className="rounded bg-moss px-4 py-2 text-sm font-semibold text-white" onClick={handleParseSeats}>
                解析席位池
              </button>
              <span className="text-sm text-ink/65">{seats.length ? `${seats.length} 个候选席位` : "等待解析"}</span>
            </div>
          </Panel>
        </section>

        <section className="grid gap-4 xl:grid-cols-[1.4fr_0.9fr]">
          <Panel title={`席位选择 · 已选 ${selectedSeatIds.length}/6`}>
            <div className="grid gap-3 md:grid-cols-2">
              {seats.map((seat) => (
                <article
                  key={seat.id}
                  className={`rounded border p-3 text-left transition ${
                    selectedSeatIds.includes(seat.id) ? "border-moss bg-moss/10" : "border-ink/10 bg-paper"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <strong className="text-base">{seat.name}</strong>
                    <div className="flex shrink-0 items-center gap-2">
                      <span className="rounded bg-ink/10 px-2 py-1 text-xs">{seat.type || "未分类"}</span>
                      <button type="button" className="rounded border border-ink/15 bg-white px-2 py-1 text-xs" onClick={() => toggleSeat(seat.id)}>
                        {selectedSeatIds.includes(seat.id) ? "取消" : "选择"}
                      </button>
                    </div>
                  </div>
                  <p className="mt-2 text-sm text-ink/75">{seat.coreConcern}</p>
                  <p className="mt-2 text-xs text-ink/60">发言风格：{seat.speakingStyle || "未填写"}</p>
                  <details className="mt-3 text-xs text-ink/65">
                    <summary className="cursor-pointer font-semibold text-moss">展开</summary>
                    <div className="mt-2 space-y-1">
                      <p>典型问题：{seat.typicalQuestions.join("、") || "未填写"}</p>
                      <p>应当做：{seat.mustDo || "未填写"}</p>
                      <p>应当避免：{seat.mustNotDo || "未填写"}</p>
                    </div>
                  </details>
                </article>
              ))}
              {!seats.length && <EmptyState text="先粘贴并解析席位池 JSON。" />}
            </div>
          </Panel>

          <Panel title="模型配置">
            <div className="space-y-3">
              {providers.map((provider) => (
                <div key={provider.id} className="rounded border border-ink/10 bg-paper p-3">
                  <div className="flex items-center justify-between">
                    <strong>{provider.displayName}</strong>
                    <span className={`rounded px-2 py-1 text-xs ${provider.isConfigured ? "bg-moss/15 text-moss" : "bg-rust/10 text-rust"}`}>
                      {provider.isConfigured ? "已配置" : "待配置"}
                    </span>
                  </div>
                  <dl className="mt-2 grid grid-cols-[92px_1fr] gap-1 text-xs text-ink/65">
                    <dt>Provider</dt>
                    <dd>{provider.providerType}</dd>
                    <dt>Base URL</dt>
                    <dd>{provider.baseUrl || "读取 .env.local"}</dd>
                    <dt>Model</dt>
                    <dd>{provider.modelName || "读取 .env.local"}</dd>
                    <dt>API Key</dt>
                    <dd>仅后端/环境变量保存</dd>
                  </dl>
                </div>
              ))}
              <label className="flex items-center gap-2 text-sm text-ink/70">
                <input type="checkbox" checked={useMock} onChange={(event) => setUseMock(event.target.checked)} />
                使用 mock provider 只做流程测试，不消耗真实 API；要看真实讨论质量请取消勾选
              </label>
              {useMock && (
                <p className="rounded border border-rust/20 bg-rust/10 p-3 text-xs leading-5 text-rust">
                  当前是 mock 模式：发言由本地样例生成，只用于检查席位、分配、错误处理和 transcript 展示。真实质量请关闭 mock 后调用 DeepSeek / MiMo / Kimi。
                </p>
              )}
            </div>
          </Panel>
        </section>

        <section className="grid gap-4 xl:grid-cols-[1fr_1fr]">
          <Panel title="席位分配">
            <button type="button" className="rounded bg-rust px-4 py-2 text-sm font-semibold text-white" onClick={handleAssignSeats}>
              生成席位分配
            </button>
            <div className="mt-3 grid gap-2">
              {activeAssignments.map((assignment) => {
                const seat = seats.find((item) => item.id === assignment.seatId);
                const provider = providers.find((item) => item.id === assignment.providerId);
                return (
                  <div key={assignment.id} className="rounded border border-ink/10 bg-paper p-3 text-sm">
                    <strong>{provider?.displayName ?? assignment.providerId}</strong>｜{seat?.name}
                    <p className="mt-1 text-xs text-ink/60">{assignment.reason}</p>
                  </div>
                );
              })}
              {!selectedSeats.length && <EmptyState text="选择 4 到 6 个席位后生成分配。" />}
            </div>
          </Panel>

          <Panel title="运行日志">
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                className="rounded bg-moss px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-ink/30"
                onClick={handleStartRoundtable}
                disabled={runStatus === "running"}
              >
                {runStatus === "running" ? "运行中" : "开始圆桌"}
              </button>
              <StatusBadge status={runStatus} />
            </div>
            <div className="mt-4 grid gap-2 text-sm">
              {providerStatus.map((item) => (
                <div key={item.providerId} className="rounded border border-ink/10 bg-paper p-3">
                  <strong>{item.providerName}</strong>：{item.status}，调用 {item.calls} 次，失败 {item.failures} 次
                </div>
              ))}
              {errors.map((error) => (
                <div key={`${error.phase}-${error.round}-${error.seatId}`} className="rounded border border-rust/30 bg-rust/10 p-3 text-rust">
                  {error.phase} R{error.round}｜{error.providerName}｜{error.seatName}：{error.message}
                </div>
              ))}
              {!providerStatus.length && !errors.length && <EmptyState text="点击开始后，这里显示 provider 调用状态和错误。" />}
            </div>
          </Panel>
        </section>

        <ChatTranscript transcript={transcript} />

        <footer className="flex flex-wrap items-center justify-between gap-2 rounded bg-paper px-4 py-3 text-sm text-ink/70">
          <span>{message || "准备就绪。"}</span>
          <span>话题：{topic.trim() ? "已填写" : "未填写"} · 可用模型：{configuredProviderCount}</span>
        </footer>
      </div>
    </main>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded border border-ink/10 bg-white p-4 shadow-sm">
      <h2 className="mb-3 text-lg font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function EmptyState({ text }: { text: string }) {
  return <div className="rounded border border-dashed border-ink/20 bg-paper p-4 text-sm text-ink/55">{text}</div>;
}

function ChatTranscript({ transcript }: { transcript: RoundtableTranscriptItem[] }) {
  return (
    <section className="overflow-hidden rounded bg-[#ededed] shadow-[0_1px_8px_rgba(15,23,42,0.08)] ring-1 ring-ink/10">
      <div className="flex h-12 items-center justify-between border-b border-[#dedede] bg-[#f7f7f7] px-4">
        <h2 className="truncate text-[15px] font-semibold text-ink">众声室圆桌群聊{transcript.length ? `（${transcript.length}）` : ""}</h2>
        <div className="flex items-center gap-4 text-xl leading-none text-ink/50" aria-hidden="true">
          <span className="-mt-1">⌕</span>
          <span>⋯</span>
        </div>
      </div>

      <div className="min-h-[640px] max-h-[780px] overflow-y-auto bg-[#ededed] px-4 py-6 sm:px-8">
        {transcript.length ? (
          <div className="space-y-5">
            {transcript.map((item, index) => (
              <div key={item.id}>
                {shouldShowTimeDivider(index) && <ChatTimeDivider label={formatChatTime(index)} />}
                <ChatMessage item={item} />
              </div>
            ))}
          </div>
        ) : (
          <div className="flex min-h-[500px] items-center justify-center text-sm text-ink/40">等待圆桌开始</div>
        )}
      </div>
    </section>
  );
}

function ChatMessage({ item }: { item: RoundtableTranscriptItem }) {
  const failed = item.status === "failed";
  const speakerName = `${item.seatName} - ${item.providerName}`;

  return (
    <article className="flex items-start gap-3">
      <div className={`mt-5 flex h-10 w-10 shrink-0 items-center justify-center rounded-[4px] text-sm font-semibold shadow-sm ${avatarClassName(item.providerId, failed)}`}>
        {item.seatName.trim().slice(0, 1) || "席"}
      </div>
      <div className="min-w-0 max-w-[min(620px,calc(100%-3.5rem))]">
        <div className="mb-1 min-h-4 text-xs leading-4 text-[#8a8a8a]">
          <span>{speakerName}</span>
          {failed && <span className="ml-2 font-semibold text-rust">调用失败</span>}
        </div>
        <div className={`relative rounded-[4px] px-3.5 py-2.5 shadow-[0_1px_1px_rgba(0,0,0,0.04)] before:absolute before:left-[-5px] before:top-3 before:h-2.5 before:w-2.5 before:rotate-45 ${bubbleClassName(item.providerId, failed)}`}>
          <p className="whitespace-pre-wrap text-[15px] leading-[1.75]">{failed ? item.error : item.content}</p>
        </div>
      </div>
    </article>
  );
}

function ChatTimeDivider({ label }: { label: string }) {
  return <div className="mb-5 text-center text-xs text-[#a7a7a7]">{label}</div>;
}

function shouldShowTimeDivider(index: number) {
  return index === 0 || index % 5 === 0;
}

function formatChatTime(index: number) {
  const baseMinutes = 22 * 60 + 18 + Math.floor(index / 5) * 7;
  const hours = Math.floor(baseMinutes / 60) % 24;
  const minutes = baseMinutes % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

function avatarClassName(providerId: string, failed: boolean) {
  if (failed) {
    return "bg-rust/15 text-rust";
  }

  switch (providerId) {
    case "deepseek":
      return "bg-[#dfeadf] text-moss";
    case "mimo":
      return "bg-[#dfe6ef] text-[#3d5f86]";
    case "kimi":
      return "bg-[#eadff0] text-[#72508c]";
    default:
      return "bg-ink/10 text-ink";
  }
}

function bubbleClassName(providerId: string, failed: boolean) {
  if (failed) {
    return "bg-rust/10 text-rust before:bg-rust/10";
  }

  return "bg-white text-ink before:bg-white";
}

function StatusBadge({ status }: { status: RoundtableStatus }) {
  const className =
    status === "success"
      ? "bg-moss/15 text-moss"
      : status === "failed"
        ? "bg-rust/10 text-rust"
        : status === "running"
          ? "bg-ink/10 text-ink"
          : "bg-ink/5 text-ink/60";

  return <span className={`rounded px-2 py-1 text-xs font-semibold ${className}`}>{status}</span>;
}
