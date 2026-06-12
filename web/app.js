const state = {
  status: null,
  groups: null,
  matches: [],
  prediction: null,
  sources: [],
  factors: [],
  teamNames: {},
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

function setText(selector, value) {
  const node = $(selector);
  if (node) node.textContent = value;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let message = `请求失败：${response.status}`;
    try {
      const payload = await response.json();
      if (payload.error) {
        message = payload.error;
      }
    } catch {
      // Keep the generic HTTP message when the server did not return JSON.
    }
    throw new Error(message);
  }
  return response.json();
}

function renderStatus() {
  const status = state.status;
  if (!status) return;

  setText("#groupStatus", status.groupsLoaded ? "正式分组已加载" : "分组未加载");
  setText("#llmStatus", status.llmStatus === "configured" ? "LLM 已连接" : "LLM 未配置");
  setText("#teamCount", `${status.teamCount} 支球队`);
  const sourceLabel = status.dataMode === "official_groups_full_history" ? "完整国际比赛历史数据" : "样例历史数据";
  setText("#dataMode", `正式分组已就绪；当前使用${sourceLabel}（${status.historySource || "未知来源"}）。`);
}

function loadLlmSessionConfig() {
  try {
    return JSON.parse(sessionStorage.getItem("worldcup_llm_config") || "{}");
  } catch {
    return {};
  }
}

function saveLlmSessionConfig(config) {
  const safeConfig = {
    base_url: config.base_url || "",
    api_key: config.api_key || "",
    model: config.model || "",
    verify_ssl: config.verify_ssl !== false,
  };
  sessionStorage.setItem("worldcup_llm_config", JSON.stringify(safeConfig));
}

function hydrateLlmForm() {
  const config = loadLlmSessionConfig();
  const baseUrl = $("#llmBaseUrl");
  const apiKey = $("#llmApiKey");
  const model = $("#llmModel");
  const skipSsl = $("#llmSkipSsl");
  if (baseUrl) baseUrl.value = config.base_url || "";
  if (apiKey) apiKey.value = config.api_key || "";
  if (model) model.value = config.model || "";
  if (skipSsl) skipSsl.checked = config.verify_ssl === false;
}

function collectLlmForm() {
  return {
    base_url: $("#llmBaseUrl")?.value.trim() || "",
    api_key: $("#llmApiKey")?.value.trim() || "",
    model: $("#llmModel")?.value.trim() || "",
    verify_ssl: !$("#llmSkipSsl")?.checked,
  };
}

function setLlmResult(message, tone = "muted") {
  const node = $("#llmTestResult");
  if (!node) return;
  node.textContent = message;
  node.dataset.tone = tone;
}

function setSourceResult(message, tone = "muted") {
  const node = $("#sourceResult");
  if (!node) return;
  node.textContent = message;
  node.dataset.tone = tone;
}

function teamLabel(team) {
  return state.teamNames?.[team] || team || "未知球队";
}

async function testLlmConnection(event) {
  event?.preventDefault();
  const button = $("#testLlmButton");
  const config = collectLlmForm();
  saveLlmSessionConfig(config);
  if (button) {
    button.disabled = true;
    button.textContent = "测试中...";
  }
  setLlmResult("正在连接 LLM 服务...", "muted");
  try {
    const result = await fetchJson("/api/llm/test", {
      method: "POST",
      body: JSON.stringify(config),
    });
    setLlmResult(`连接成功：${result.message || "服务可用"}`, "success");
    await refreshApp();
  } catch (error) {
    setLlmResult(error.message, "error");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "测试连接";
    }
  }
}

function clearLlmConfig() {
  sessionStorage.removeItem("worldcup_llm_config");
  hydrateLlmForm();
  setLlmResult("已清除本页保存的配置。后端内存中的连接状态会在重启应用后清空。", "muted");
}

function renderSources() {
  const list = $("#sourceList");
  if (!list) return;
  if (!state.sources.length) {
    list.innerHTML = `<div class="mini-empty">还没有信息源。</div>`;
    return;
  }
  list.innerHTML = state.sources
    .map(
      (source) => `
        <article class="source-item">
          <div>
            <strong>${source.title}</strong>
            <p>${source.type} · ${source.fetch_status}${source.warning ? ` · ${source.warning}` : ""}</p>
          </div>
          <div class="source-actions">
            <button class="ghost extract-button" data-source-id="${source.id}">提取因素</button>
            <button class="ghost danger delete-source-button" data-source-id="${source.id}">删除</button>
          </div>
        </article>
      `
    )
    .join("");

  $$(".extract-button").forEach((button) => {
    button.addEventListener("click", () => extractSourceFactors(button.dataset.sourceId));
  });
  $$(".delete-source-button").forEach((button) => {
    button.addEventListener("click", () => deleteSource(button.dataset.sourceId));
  });
}

function renderFactors() {
  const list = $("#factorList");
  if (!list) return;
  if (!state.factors.length) {
    list.innerHTML = `<div class="mini-empty">还没有 AI 提取结果。</div>`;
    return;
  }
  list.innerHTML = state.factors
    .map(
      (factor) => {
        const adjustment = Number(factor.rating_adjustment || 0);
        const adjustmentText = !factor.applied_to_model
          ? "未匹配球队，不调整模型"
          : adjustment === 0
          ? "不调整模型"
          : `模型调整：${adjustment > 0 ? "+" : ""}${adjustment} Elo`;
        return `
        <article class="factor-item">
          <div class="factor-head">
            <strong>${teamLabel(factor.team)}</strong>
            <span class="pill muted">${factor.category || "other"} · ${factor.direction || "neutral"}</span>
          </div>
          <p>${factor.evidence || "无证据文本"}</p>
          <small>严重程度：${factor.severity || "low"} · 置信度：${Math.round(Number(factor.confidence || 0) * 100)}% · ${adjustmentText}</small>
        </article>
      `;
      }
    )
    .join("");
}

async function saveSource(event) {
  event?.preventDefault();
  const button = $("#saveSourceButton");
  const payload = {
    title: $("#sourceTitle")?.value.trim() || "",
    type: $("#sourceType")?.value || "news",
    url: $("#sourceUrl")?.value.trim() || "",
    text: $("#sourceText")?.value.trim() || "",
  };
  if (button) {
    button.disabled = true;
    button.textContent = "保存中...";
  }
  try {
    const result = await fetchJson("/api/sources", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.sources = result.sources;
    renderSources();
    setSourceResult("信息源已保存。可以点击“提取因素”让 LLM 分析。", "success");
    $("#sourceForm")?.reset();
  } catch (error) {
    setSourceResult(error.message, "error");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "保存信息源";
    }
  }
}

async function extractSourceFactors(sourceId) {
  if (!sourceId) return;
  setSourceResult("正在调用 LLM 提取影响因素...", "muted");
  try {
    const result = await fetchJson(`/api/sources/${sourceId}/extract`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    state.factors = state.factors.filter((factor) => factor.source_id !== sourceId).concat(result.factors);
    renderFactors();
    const count = result.factors.length;
    setSourceResult(`提取完成：${count} 个影响因子。${result.summary || ""}`, "success");
  } catch (error) {
    setSourceResult(error.message, "error");
  }
}

async function deleteSource(sourceId) {
  if (!sourceId) return;
  const source = state.sources.find((item) => item.id === sourceId);
  const confirmed = window.confirm(`删除信息源“${source?.title || sourceId}”？相关 AI 影响因子也会一起删除。`);
  if (!confirmed) return;
  setSourceResult("正在删除信息源...", "muted");
  try {
    const result = await fetchJson(`/api/sources/${sourceId}`, {
      method: "DELETE",
    });
    state.sources = result.sources || [];
    state.factors = result.factors || [];
    renderSources();
    renderFactors();
    setSourceResult(`已删除信息源，并移除 ${result.deleted_factors || 0} 个影响因子。`, "success");
  } catch (error) {
    setSourceResult(error.message, "error");
  }
}

function renderGroups() {
  const grid = $("#groupsGrid");
  if (!grid || !state.groups) return;

  grid.innerHTML = Object.entries(state.groups)
    .map(([group, teams]) => {
      const items = teams.map((team) => `<li>${team}</li>`).join("");
      return `
        <article class="group-card">
          <div class="group-title">
            <strong>${group} 组</strong>
            <span class="pill muted">${teams.length} 队</span>
          </div>
          <ul class="team-list">${items}</ul>
        </article>
      `;
    })
    .join("");
}

function groupMatchesByGroup() {
  return state.matches.reduce((acc, match) => {
    if (!acc[match.group]) acc[match.group] = [];
    acc[match.group].push(match);
    return acc;
  }, {});
}

function renderMatches() {
  const grid = $("#scoreGrid");
  if (!grid) return;
  const grouped = groupMatchesByGroup();
  grid.innerHTML = Object.entries(grouped)
    .map(([group, matches]) => {
      const rows = matches
        .map((match) => {
          const home = match.home_score ?? "";
          const away = match.away_score ?? "";
          return `
            <div class="score-row" data-match-id="${match.id}">
              <span class="team-name">${match.home_team_name || teamLabel(match.home_team)}</span>
              <input class="score-input" type="number" min="0" max="30" inputmode="numeric" value="${home}" aria-label="${match.home_team_name || teamLabel(match.home_team)} 进球">
              <span class="score-separator">-</span>
              <input class="score-input" type="number" min="0" max="30" inputmode="numeric" value="${away}" aria-label="${match.away_team_name || teamLabel(match.away_team)} 进球">
              <span class="team-name away">${match.away_team_name || teamLabel(match.away_team)}</span>
            </div>
          `;
        })
        .join("");
      return `
        <article class="score-card">
          <div class="group-title">
            <strong>${group} 组</strong>
            <span class="pill muted">${matches.length} 场</span>
          </div>
          <div class="score-list">${rows}</div>
        </article>
      `;
    })
    .join("");
}

function collectMatchesFromForm() {
  const byId = Object.fromEntries(state.matches.map((match) => [match.id, { ...match }]));
  $$(".score-row").forEach((row) => {
    const id = row.dataset.matchId;
    const inputs = row.querySelectorAll("input");
    const home = inputs[0].value.trim();
    const away = inputs[1].value.trim();
    if (home === "" || away === "") {
      byId[id].home_score = null;
      byId[id].away_score = null;
      byId[id].status = "scheduled";
    } else {
      byId[id].home_score = Number(home);
      byId[id].away_score = Number(away);
      byId[id].status = "finished";
    }
  });
  return Object.values(byId);
}

async function saveScores() {
  const matches = collectMatchesFromForm();
  const payload = await fetchJson("/api/matches", {
    method: "POST",
    body: JSON.stringify({ matches }),
  });
  state.matches = payload.matches;
  renderMatches();
  setText("#predictionMeta", "比分已保存。点击重新预测查看变化。");
}

async function clearScores() {
  state.matches = state.matches.map((match) => ({
    ...match,
    home_score: null,
    away_score: null,
    status: "scheduled",
  }));
  renderMatches();
  await saveScores();
}

function formatPct(value) {
  const number = Number(value || 0);
  return number >= 0.1 ? `${(number * 100).toFixed(1)}%` : `${(number * 100).toFixed(2)}%`;
}

function getSimulationCount() {
  const input = $("#simulationCount");
  const raw = Number(input?.value || 1000);
  const count = Math.max(100, Math.min(10000, Math.round(raw / 100) * 100));
  if (input) input.value = String(count);
  return count;
}

function renderPrediction() {
  const prediction = state.prediction;
  const ranking = $("#rankingList");
  const table = $("#stageTable");
  if (!prediction || !ranking || !table) return;

  const topRows = prediction.rows.slice(0, 10);
  const maxChampion = Math.max(...topRows.map((row) => row.champion), 0.001);
  ranking.innerHTML = topRows
    .map((row, index) => {
      const width = Math.round((row.champion / maxChampion) * 100);
      const name = row.team_name || teamLabel(row.team);
      return `
        <div class="rank-row">
          <span class="rank-number">${index + 1}</span>
          <span class="rank-team">${name}</span>
          <span class="rank-bar"><i style="width:${width}%"></i></span>
          <strong>${formatPct(row.champion)}</strong>
        </div>
      `;
    })
    .join("");

  table.innerHTML = prediction.rows
    .slice(0, 16)
    .map(
      (row) => `
        <tr>
          <td>${row.team_name || teamLabel(row.team)}</td>
          <td>${formatPct(row.champion)}</td>
          <td>${formatPct(row.final)}</td>
          <td>${formatPct(row.sf)}</td>
          <td>${formatPct(row.qf)}</td>
          <td>${formatPct(row.r16)}</td>
          <td>${formatPct(row.r32)}</td>
        </tr>
      `
    )
    .join("");

  setText(
    "#predictionMeta",
    `已生成 ${prediction.simulations} 次模拟；已纳入 ${prediction.finishedMatches} 场已结束比分；AI 影响因子：${prediction.aiFactorsApplied || 0} 条；历史数据：${prediction.historySource}`
  );
}

async function runPrediction() {
  const button = $("#predictButton");
  const simulations = getSimulationCount();
  if (button) {
    button.disabled = true;
    button.textContent = "预测中...";
  }
  setText("#predictionMeta", `正在请求后台重新预测，模拟 ${simulations} 次...`);
  activateTab("overview");
  try {
    const prediction = await fetchJson("/api/predict", {
      method: "POST",
      body: JSON.stringify({ simulations }),
    });
    state.prediction = prediction;
    renderPrediction();
  } catch (error) {
    setText("#predictionMeta", `预测失败：${error.message}`);
    activateTab("overview");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "重新预测";
    }
  }
}

async function generateReport() {
  const button = $("#generateReportButton");
  const resultNode = $("#reportResult");
  const simulations = getSimulationCount();
  if (button) {
    button.disabled = true;
    button.textContent = "生成中...";
  }
  if (resultNode) {
    resultNode.innerHTML = `<strong>正在生成报告</strong><p>系统会先运行 ${simulations} 次本地模拟，再整理信息源和影响因子。</p>`;
  }
  try {
    const result = await fetchJson("/api/report/generate", {
      method: "POST",
      body: JSON.stringify({ simulations }),
    });
    state.prediction = result.prediction;
    renderPrediction();
    if (resultNode) {
      resultNode.innerHTML = `
        <strong>${result.report.title}</strong>
        <p>生成时间：${result.report.createdAt}</p>
        <a class="report-link" href="${result.report.url}" target="_blank" rel="noreferrer">打开 HTML 报告</a>
      `;
    }
  } catch (error) {
    if (resultNode) {
      resultNode.innerHTML = `<strong>报告生成失败</strong><p>${error.message}</p>`;
    }
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "生成报告";
    }
  }
}

async function refreshApp() {
  try {
    const [status, groupsPayload, matchesPayload, sourcesPayload, factorsPayload] = await Promise.all([
      fetchJson("/api/status"),
      fetchJson("/api/groups"),
      fetchJson("/api/matches"),
      fetchJson("/api/sources"),
      fetchJson("/api/factors"),
    ]);
    state.status = status;
    state.groups = groupsPayload.groups;
    state.teamNames = groupsPayload.teamNames || {};
    state.matches = matchesPayload.matches;
    state.sources = sourcesPayload.sources;
    state.factors = factorsPayload.factors;
    renderStatus();
    renderGroups();
    renderMatches();
    renderSources();
    renderFactors();
  } catch (error) {
    setText("#groupStatus", "本地数据读取失败");
    setText("#dataMode", error.message);
  }
}

function activateTab(id) {
  $$(".tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.tab === id);
  });
  $$(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === id);
  });
}

function bindEvents() {
  $$(".tab").forEach((tab) => {
    tab.addEventListener("click", () => activateTab(tab.dataset.tab));
  });

  $$("[data-tab-target]").forEach((button) => {
    button.addEventListener("click", () => activateTab(button.dataset.tabTarget));
  });

  $("#refreshButton")?.addEventListener("click", refreshApp);
  $("#saveScoresButton")?.addEventListener("click", saveScores);
  $("#clearScoresButton")?.addEventListener("click", clearScores);
  $("#predictButton")?.addEventListener("click", runPrediction);
  $("#llmForm")?.addEventListener("submit", testLlmConnection);
  $("#clearLlmButton")?.addEventListener("click", clearLlmConfig);
  $("#sourceForm")?.addEventListener("submit", saveSource);
  $("#generateReportButton")?.addEventListener("click", generateReport);
}

hydrateLlmForm();
bindEvents();
refreshApp();
