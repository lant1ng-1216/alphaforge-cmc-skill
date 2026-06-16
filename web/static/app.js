const input = document.getElementById("intent-input");
const btn = document.getElementById("generate-btn");
const statusLine = document.getElementById("status-line");
const downloadLink = document.getElementById("download-link");

document.querySelectorAll(".example-btn").forEach(b => {
  b.addEventListener("click", () => { input.value = b.dataset.text; input.focus(); });
});

document.querySelectorAll(".tab-btn").forEach(b => {
  b.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach(x => x.classList.remove("active"));
    b.classList.add("active");
    renderDetailsTab(b.dataset.tab);
  });
});

btn.addEventListener("click", generate);
input.addEventListener("keydown", e => {
  if (e.key === "Enter") generate();
});

let lastResult = null;

function esc(s) {
  return String(s).replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

// Adaptive-precision price formatting: fixed 4-decimal rounding reads as
// "0.0000" for sub-cent memecoins (PEPE, SHIB, BONK...) even though the
// real price is e.g. 0.0000089 — show enough decimals to keep significant figures.
function fmtPrice(v) {
  if (v === null || v === undefined || isNaN(v)) return "N/A";
  v = Number(v);
  if (v === 0) return "0.0000";
  if (Math.abs(v) >= 1) return v.toLocaleString(undefined, { maximumFractionDigits: 4 });
  const decimals = Math.max(4, -Math.floor(Math.log10(Math.abs(v))) + 3);
  return v.toFixed(decimals);
}

function fill(id, html) {
  document.getElementById(id).innerHTML = html;
}

async function generate() {
  const text = input.value.trim();
  if (!text) { input.focus(); return; }

  btn.disabled = true;
  statusLine.className = "status-line";
  statusLine.textContent = "Generating...";

  let result;
  try {
    const res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input: text }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Request failed (${res.status})`);
    }
    result = await res.json();
  } catch (e) {
    statusLine.className = "status-line error";
    statusLine.textContent = `Error: ${e.message}`;
    btn.disabled = false;
    return;
  }

  lastResult = result;
  statusLine.textContent = "Done.";
  renderAll(result);
  btn.disabled = false;
}

function renderAll(r) {
  renderIntent(r);
  renderMarket(r);
  renderFeatures(r);
  renderRegime(r);
  renderSpec(r);
  renderMetrics(r);
  renderChart(r);
  renderDetailsTab(document.querySelector(".tab-btn.active")?.dataset.tab || "explanation");
  renderDownload(r);
}

function renderIntent(r) {
  const i = r.intent;
  const v = r.validation;
  fill("sec-intent", `
    <div class="kv-list">
      <div><span class="k">asset</span><span class="v">${esc(i.asset)}</span></div>
      <div><span class="k">timeframe</span><span class="v">${esc(i.timeframe)}</span></div>
      <div><span class="k">style</span><span class="v">${esc(i.style)}</span></div>
      <div><span class="k">risk_profile</span><span class="v">${esc(i.risk_profile)}</span></div>
      <div><span class="k">constraints</span><span class="v">${esc(JSON.stringify(i.constraints))}</span></div>
    </div>
    <span class="badge ${v.valid ? "badge-pass" : "badge-fail"}">${v.valid ? "SPEC VALID" : "SPEC INVALID"}</span>`);
}

function renderMarket(r) {
  const m = r.market_context;
  fill("sec-market", `
    <div class="kv-list">
      <div><span class="k">price</span><span class="v">$${fmtPrice(m.price)}</span></div>
      <div><span class="k">24h</span><span class="v">${m.price_change_24h >= 0 ? "+" : ""}${m.price_change_24h.toFixed(2)}%</span></div>
      <div><span class="k">7d</span><span class="v">${m.price_change_7d >= 0 ? "+" : ""}${m.price_change_7d.toFixed(2)}%</span></div>
      <div><span class="k">fear_greed</span><span class="v">${m.fear_greed_score} (${esc(m.fear_greed_label)})</span></div>
      <div><span class="k">btc_dominance</span><span class="v">${m.btc_dominance.toFixed(1)}%</span></div>
      <div><span class="k">ohlcv_points</span><span class="v">${m.data_points}</span></div>
    </div>`);
}

function renderFeatures(r) {
  const s = r.regime.signals;
  const fmt = v => (typeof v === "number" ? v.toFixed(4) : "N/A");
  fill("sec-features", `
    <div class="kv-list">
      <div><span class="k">ema_20</span><span class="v">${fmtPrice(s.ema_20)}</span></div>
      <div><span class="k">ema_50</span><span class="v">${fmtPrice(s.ema_50)}</span></div>
      <div><span class="k">rsi_14</span><span class="v">${fmt(s.rsi_14)}</span></div>
      <div><span class="k">macd_hist</span><span class="v">${fmtPrice(s.macd_histogram)}</span></div>
      <div><span class="k">volume_zscore</span><span class="v">${fmt(s.volume_zscore)}</span></div>
      <div><span class="k">realized_vol</span><span class="v">${fmt(s.realized_volatility)}</span></div>
    </div>`);
}

function renderRegime(r) {
  const g = r.regime;
  fill("sec-regime", `
    <div class="regime-badge">
      ${esc(g.primary.replace(/_/g, " ").toUpperCase())}
      <span class="confidence-pill">conf ${(g.confidence * 100).toFixed(0)}%</span>
    </div>
    <p class="explanation-text">${esc(g.explanation)}</p>
    ${g.secondary && g.secondary.length ? `<p class="explanation-text">Secondary: ${g.secondary.map(esc).join(", ")}</p>` : ""}`);
}

function renderSpec(r) {
  const spec = r.spec;
  const entry = (spec.entry_rules && spec.entry_rules.all) || [];
  const exit = (spec.exit_rules && spec.exit_rules.any) || [];
  const rm = spec.risk_management || {};
  const yamlLines = [
    `strategy_type: ${spec.strategy_type}`,
    `market_regime: ${spec.market_regime?.primary ?? ""}`,
    `entry_rules:`,
    ...entry.map(rule => `  - ${rule}`),
    `exit_rules:`,
    ...exit.map(rule => `  - ${rule}`),
    `risk_management:`,
    `  max_position_size_pct: ${rm.max_position_size_pct}`,
    `  stop_loss_pct: ${rm.stop_loss_pct}`,
    `  max_strategy_drawdown_pct: ${rm.max_strategy_drawdown_pct}`,
  ];
  fill("sec-spec", `<pre class="code-block">${esc(yamlLines.join("\n"))}</pre>`);
}

function tileValue(metric, text, cls) {
  const el = document.querySelector(`.metric-tile[data-metric="${metric}"] .metric-tile-value`);
  el.textContent = text;
  el.className = "metric-tile-value" + (cls ? ` ${cls}` : "");
}

function renderMetrics(r) {
  const bt = r.backtest;
  tileValue("total_return", `${bt.total_return_pct >= 0 ? "+" : ""}${bt.total_return_pct.toFixed(2)}%`, bt.total_return_pct >= 0 ? "pos" : "neg");
  tileValue("bah_return", `${bt.buy_and_hold_return_pct >= 0 ? "+" : ""}${bt.buy_and_hold_return_pct.toFixed(2)}%`, bt.buy_and_hold_return_pct >= 0 ? "pos" : "neg");
  tileValue("max_dd", `-${bt.max_drawdown_pct.toFixed(2)}%`, "neg");
  tileValue("sharpe", bt.sharpe_ratio.toFixed(2));
  tileValue("win_rate", `${bt.win_rate_pct.toFixed(1)}%`);
  tileValue("trades", bt.number_of_trades);
  tileValue("exposure", `${bt.exposure_time_pct.toFixed(1)}%`);
  tileValue("equity", `$${Math.round(bt.final_equity).toLocaleString()}`);
}

function renderChart(r) {
  const body = document.getElementById("chart-body");
  if (r.chart_url) {
    const src = `${r.chart_url}?t=${Date.now()}`;
    const downloadName = r.chart_download_name || "alphaforge_chart.png";
    body.innerHTML = `<img src="${src}" alt="AlphaForge chart"><div class="chart-hint">Click to expand</div>`;
    body.querySelector("img").addEventListener("click", () => openLightbox(src, downloadName));
  } else {
    body.innerHTML = `<div class="chart-placeholder">Chart unavailable for this run.</div>`;
  }
}

const lightbox = document.getElementById("lightbox");
const lightboxImg = document.getElementById("lightbox-img");
const lightboxDownload = document.getElementById("lightbox-download");
const lightboxClose = document.getElementById("lightbox-close");

function openLightbox(src, downloadName) {
  lightboxImg.src = src;
  lightboxDownload.href = src;
  lightboxDownload.setAttribute("download", downloadName);
  lightbox.classList.remove("hidden");
}

function closeLightbox() {
  lightbox.classList.add("hidden");
}

lightboxClose.addEventListener("click", closeLightbox);
lightbox.addEventListener("click", e => { if (e.target === lightbox) closeLightbox(); });
document.addEventListener("keydown", e => { if (e.key === "Escape") closeLightbox(); });

function renderDetailsTab(tab) {
  const content = document.getElementById("details-content");
  if (!lastResult) {
    content.innerHTML = `<div class="empty">Run a strategy to see the explanation and failure modes.</div>`;
    return;
  }
  if (tab === "failure") {
    content.innerHTML = `<ul class="failure-list">${lastResult.failure_modes.map(f => `<li>${esc(f)}</li>`).join("")}</ul>`;
  } else {
    content.innerHTML = `<p>${esc(lastResult.explanation).replace(/\n\n/g, "</p><p>")}</p>`;
  }
}

function renderDownload(r) {
  const blob = new Blob([JSON.stringify(r, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  downloadLink.href = url;
  downloadLink.classList.remove("disabled");
}
