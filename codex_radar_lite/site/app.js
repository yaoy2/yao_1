async function loadRadar() {
  const target = new URL("../../data/codex_radar_current.json", window.location.href);
  const response = await fetch(target, { cache: "no-store" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function statusText(status) {
  const labels = {
    normal: "正常",
    watch: "观察",
    high_probability: "高概率",
    open: "窗口开启",
    closed: "窗口关闭"
  };
  return labels[status] || status;
}

function render(data) {
  document.getElementById("status").textContent = statusText(data.status);
  document.getElementById("status").dataset.status = data.status;
  document.getElementById("reason").textContent = data.reason || "暂无判断说明。";
  document.getElementById("p24").textContent = `${data.probability_24h}%`;
  document.getElementById("p48").textContent = `${data.probability_48h}%`;
  document.getElementById("checked").textContent = `最近检查：${data.checked_at}`;

  const box = document.getElementById("signals");
  box.innerHTML = "";
  const signals = Array.isArray(data.signals) ? data.signals : [];
  if (!signals.length) {
    box.innerHTML = '<p class="empty">暂时没有关键证据，等待下一轮采集。</p>';
    return;
  }
  for (const signal of signals.slice(0, 10)) {
    const item = document.createElement("article");
    item.className = "signal";
    const title = document.createElement("a");
    title.href = signal.url || "#";
    title.textContent = signal.title || "未命名信号";
    title.target = "_blank";
    title.rel = "noopener noreferrer";
    const meta = document.createElement("p");
    meta.textContent = `${signal.source_name || signal.source_id} · ${signal.observed_at || ""}`;
    const summary = document.createElement("p");
    summary.textContent = signal.summary || "";
    item.append(title, meta, summary);
    box.appendChild(item);
  }
}

loadRadar().then(render).catch((error) => {
  document.getElementById("reason").textContent = `读取失败：${error.message}`;
});

