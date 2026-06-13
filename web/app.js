const state = {
  status: null,
  groups: null,
  matches: [],
  prediction: null,
  sources: [],
  factors: [],
  teamNames: {},
  scheduleView: "list",
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
  const modeLabel = status.appMode === "hosted" ? "网站模式，比分由服务端数据源固定" : "本地模式，可手动录入未确认比分";
  setText("#dataMode", `正式分组已就绪；当前使用${sourceLabel}（${status.historySource || "未知来源"}）。${modeLabel}。`);

  $$("[data-requires-score-input]").forEach((node) => {
    node.hidden = !status.allowUserScoreInput;
  });
  if (!status.allowUserScoreInput && $("#scores")?.classList.contains("active")) {
    activateTab("overview");
  }
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

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
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
      (source) => {
        const url = source.url ? escapeHtml(source.url) : "";
        const text = escapeHtml(source.text || "");
        const warning = source.warning ? escapeHtml(source.warning) : "";
        const statusLine = [
          escapeHtml(source.type || "other"),
          escapeHtml(source.fetch_status || "manual"),
          source.content_type ? escapeHtml(source.content_type) : "",
        ]
          .filter(Boolean)
          .join(" · ");
        return `
        <article class="source-item">
          <div class="source-main">
            <strong>${escapeHtml(source.title || "未命名信息源")}</strong>
            <p>${statusLine}${warning ? ` · ${warning}` : ""}</p>
            ${url ? `<a class="source-url" href="${url}" target="_blank" rel="noreferrer">${url}</a>` : ""}
            <details class="source-body">
              <summary>查看正文</summary>
              <pre>${text || "没有可展示的正文。"}</pre>
            </details>
          </div>
          <div class="source-actions">
            <button class="ghost extract-button" data-source-id="${escapeHtml(source.id)}">提取因素</button>
            <button class="ghost danger delete-source-button" data-source-id="${escapeHtml(source.id)}">删除</button>
          </div>
        </article>
      `;
      }
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

function matchRoundNumber(match) {
  const value = Number(match.round || String(match.id || "").split("-").pop() || 0);
  return Number.isFinite(value) ? value : 0;
}

function matchScoreLabel(match) {
  if (match.status !== "finished") return "未开始";
  const home = match.home_score ?? "-";
  const away = match.away_score ?? "-";
  return `${home} - ${away}`;
}

function scoreSourceLabel(match) {
  if (match.score_source === "official") return "已确认赛果";
  if (match.score_source === "user") return "本地录入比分";
  if (state.status?.appMode === "hosted") return "等待赛果更新";
  return "待赛，预测时由模型模拟";
}

function matchSortValue(match) {
  const date = String(match.display_date || "");
  const time = String(match.display_time || "00:00");
  if (date) return `${date}T${time.padStart(5, "0")}`;
  return `9999-12-31T${String(match.match_number || matchRoundNumber(match)).padStart(4, "0")}`;
}

function kickoffLabel(match) {
  const date = String(match.display_date || "");
  const time = String(match.display_time || "");
  if (!date && !time) return escapeHtml(match.date_range || "时间待定");
  const shortDate = date.replace(/^2026-0?/, "").replace("-", "月") + (date ? "日" : "");
  return escapeHtml(`${shortDate}${time ? ` ${time}` : ""}`);
}

function isKnockoutStageFilter(value) {
  return ["stage:knockout", "stage:r32", "stage:r16", "stage:qf", "stage:sf", "stage:third_place", "stage:final"].includes(value);
}

function syncScheduleViewButtons() {
  const stageFilter = $("#scheduleStageFilter")?.value || "all";
  const bracketAvailable = isKnockoutStageFilter(stageFilter);
  if (!bracketAvailable) {
    state.scheduleView = "list";
  }
  $$("[data-schedule-view]").forEach((button) => {
    const isBracketButton = button.dataset.scheduleView === "bracket";
    button.disabled = isBracketButton && !bracketAvailable;
    button.classList.toggle("active", button.dataset.scheduleView === state.scheduleView);
  });
}

function compactSlotLabel(label) {
  const value = String(label || "待定")
    .replace(/\s+/g, "")
    .replaceAll("组第一", "")
    .replaceAll("组第二", "")
    .replaceAll("组最佳第三", "")
    .replaceAll("最佳第三", "")
    .replaceAll("第", "")
    .replaceAll("场胜者", "")
    .replaceAll("场负者", "");
  if (String(label || "").includes("负者") && /^\d+$/.test(value)) return `L${value}`;
  if (/^\d+$/.test(value)) return `W${value}`;
  if (/^[A-L]$/.test(value)) return label.includes("第一") ? `1${value}` : label.includes("第二") ? `2${value}` : value;
  if (/^[A-L](\/[A-L])+$/.test(value)) return value.split("/").map((group) => `3${group}`).join("/");
  return value || "待定";
}

function bracketCard(match, options = {}) {
  if (!match) return `<div class="bracket-card placeholder"></div>`;
  const home = escapeHtml(compactSlotLabel(match.home_label || match.home_slot));
  const away = escapeHtml(compactSlotLabel(match.away_label || match.away_slot));
  const date = escapeHtml(match.display_date || match.date_range || "日期待定");
  const time = escapeHtml(match.display_time || "");
  const matchNumber = escapeHtml(match.match_number || String(match.id || "").replace("M", ""));
  const title = options.title ? `<strong class="bracket-title">${escapeHtml(options.title)}</strong>` : "";
  const focusClass = options.focused === false ? " dimmed" : "";
  return `
    <article class="bracket-card${options.final ? " final" : ""}${focusClass}" data-match-id="${escapeHtml(match.id)}">
      ${title}
      <div class="bracket-meta">
        <span>${date}</span>
        <span>${time}</span>
      </div>
      <div class="bracket-teams">
        <span>${home}</span>
        <span>${away}</span>
      </div>
      <div class="bracket-foot">
        <span>${match.status === "finished" ? escapeHtml(matchScoreLabel(match)) : "即将开始"}</span>
        <b>M${matchNumber}</b>
      </div>
    </article>
  `;
}

function renderKnockoutBracket(matches, stageFilter = "all", statusFilter = "all") {
  const byId = Object.fromEntries(matches.map((match) => [match.id, match]));
  const selectedStage = stageFilter.startsWith("stage:") ? stageFilter.slice(6) : "";
  const shouldFocus = (match) => {
    if (!match) return false;
    const stageOk = !selectedStage || selectedStage === "knockout" ? true : match.stage === selectedStage;
    const statusOk = statusFilter === "all" || match.status === statusFilter;
    return stageOk && statusOk;
  };
  const column = (title, ids, side = "") => `
    <section class="bracket-column ${side}">
      <h3>${escapeHtml(title)}</h3>
      <div class="bracket-stack">
        ${ids.map((id) => bracketCard(byId[id], { focused: shouldFocus(byId[id]) })).join("")}
      </div>
    </section>
  `;
  return `
    <div class="bracket-board" role="region" aria-label="淘汰赛晋级树">
      ${column("32 强赛", ["M77", "M74", "M73", "M75", "M83", "M84", "M81", "M82"], "left edge")}
      ${column("16 强赛", ["M90", "M89", "M93", "M94"], "left")}
      ${column("四分之一决赛", ["M97", "M98"], "left")}
      ${column("半决赛", ["M101"], "left")}
      <section class="bracket-column center">
        <h3>决赛</h3>
        <div class="bracket-stack center-stack">
          ${bracketCard(byId.M104, { title: "决赛", final: true, focused: shouldFocus(byId.M104) })}
          ${bracketCard(byId.M103, { title: "三四名决赛", focused: shouldFocus(byId.M103) })}
        </div>
      </section>
      ${column("半决赛", ["M102"], "right")}
      ${column("四分之一决赛", ["M99", "M100"], "right")}
      ${column("16 强赛", ["M91", "M92", "M95", "M96"], "right")}
      ${column("32 强赛", ["M78", "M76", "M79", "M80", "M86", "M88", "M85", "M87"], "right edge")}
    </div>
  `;
}

function renderScheduleFilters() {
  const stageFilter = $("#scheduleStageFilter");
  if (!stageFilter || !state.groups) return;
  const currentValue = stageFilter.value || "all";
  const groupOptions = Object.keys(state.groups)
    .map((group) => `<option value="group:${escapeHtml(group)}">${escapeHtml(group)} 组</option>`)
    .join("");
  const stageOptions = [
    ["stage:group", "小组赛"],
    ["stage:knockout", "淘汰赛"],
    ["stage:r32", "32 强"],
    ["stage:r16", "16 强"],
    ["stage:qf", "八强"],
    ["stage:sf", "四强"],
    ["stage:third_place", "三四名决赛"],
    ["stage:final", "决赛"],
  ]
    .map(([value, label]) => `<option value="${value}">${label}</option>`)
    .join("");
  const validValues = new Set(["all", ...Object.keys(state.groups).map((group) => `group:${group}`), "stage:group", "stage:knockout", "stage:r32", "stage:r16", "stage:qf", "stage:sf", "stage:third_place", "stage:final"]);
  stageFilter.innerHTML = `<option value="all">全部赛程</option><optgroup label="按阶段">${stageOptions}</optgroup><optgroup label="按小组">${groupOptions}</optgroup>`;
  stageFilter.value = validValues.has(currentValue) ? currentValue : "all";
}

function renderSchedule() {
  const list = $("#scheduleList");
  const summary = $("#scheduleSummary");
  if (!list || !summary) return;

  const stageFilter = $("#scheduleStageFilter")?.value || "all";
  const statusFilter = $("#scheduleStatusFilter")?.value || "all";
  const filtered = state.matches
    .filter((match) => {
      if (stageFilter === "all") return true;
      if (stageFilter.startsWith("group:")) return match.group === stageFilter.slice(6);
      if (stageFilter === "stage:knockout") return match.stage !== "group";
      if (stageFilter.startsWith("stage:")) return match.stage === stageFilter.slice(6);
      return true;
    })
    .filter((match) => statusFilter === "all" || match.status === statusFilter)
    .sort((a, b) => {
      const timeCompare = matchSortValue(a).localeCompare(matchSortValue(b));
      if (timeCompare !== 0) return timeCompare;
      return Number(a.match_number || matchRoundNumber(a)) - Number(b.match_number || matchRoundNumber(b));
    });

  const knockoutMatches = state.matches.filter((match) => match.stage !== "group");
  const canShowBracket = state.scheduleView === "bracket" && isKnockoutStageFilter(stageFilter);
  const summaryMatches = canShowBracket
    ? knockoutMatches
        .filter((match) => {
          if (stageFilter === "stage:knockout") return true;
          return match.stage === stageFilter.slice(6);
        })
        .filter((match) => statusFilter === "all" || match.status === statusFilter)
    : filtered;
  const finishedCount = summaryMatches.filter((match) => match.status === "finished").length;
  const scopeLabel = canShowBracket ? "淘汰赛树" : "当前列表";
  summary.textContent = `${scopeLabel}显示 ${summaryMatches.length} 场比赛，其中 ${finishedCount} 场已结束、${summaryMatches.length - finishedCount} 场未开始。`;

  syncScheduleViewButtons();
  list.classList.toggle("bracket-mode", canShowBracket);
  if (canShowBracket) {
    list.innerHTML = renderKnockoutBracket(knockoutMatches, stageFilter, statusFilter);
    return;
  }
  list.classList.remove("bracket-mode");

  if (!filtered.length) {
    list.innerHTML = `<div class="mini-empty">没有符合筛选条件的比赛。</div>`;
    return;
  }

  list.innerHTML = filtered
    .map((match) => {
      const isFinished = match.status === "finished";
      const isGroup = match.stage === "group";
      const home = escapeHtml(match.home_label || match.home_team_name || teamLabel(match.home_team));
      const away = escapeHtml(match.away_label || match.away_team_name || teamLabel(match.away_team));
      const metaLabel = isGroup
        ? `${escapeHtml(match.group || "")} 组 · ${kickoffLabel(match)} · 第 ${escapeHtml(match.match_number || "")} 场`
        : `${kickoffLabel(match)} · 第 ${escapeHtml(match.match_number || "")} 场`;
      return `
        <article class="schedule-item">
          <div class="schedule-meta">
            <span class="pill muted">${escapeHtml(match.stage_name || "小组赛")}</span>
            <span>${metaLabel}</span>
          </div>
          <div class="schedule-match">
            <strong>${home}</strong>
            <span class="schedule-score ${isFinished ? "finished" : ""}">${escapeHtml(matchScoreLabel(match))}</span>
            <strong>${away}</strong>
          </div>
          <div class="schedule-status">
            <span>${isFinished ? `${scoreSourceLabel(match)}，可参与预测` : isGroup ? scoreSourceLabel(match) : "球队待定，赛程路径已确定"}</span>
            ${isGroup && match.can_edit_score ? `<button class="ghost schedule-score-button" data-tab-target="scores">录入比分</button>` : ""}
          </div>
        </article>
      `;
    })
    .join("");

  $$(".schedule-score-button").forEach((button) => {
    button.addEventListener("click", () => activateTab(button.dataset.tabTarget));
  });
}

function groupMatchesByGroup() {
  return state.matches.filter((match) => match.stage === "group").reduce((acc, match) => {
    if (!acc[match.group]) acc[match.group] = [];
    acc[match.group].push(match);
    return acc;
  }, {});
}

function renderMatches() {
  const grid = $("#scoreGrid");
  if (!grid) return;
  if (!state.status?.allowUserScoreInput) {
    grid.innerHTML = `<div class="mini-empty">当前为网站模式，比分由服务端可信数据源维护，不支持用户手动录入。</div>`;
    return;
  }
  const grouped = groupMatchesByGroup();
  grid.innerHTML = Object.entries(grouped)
    .map(([group, matches]) => {
      const rows = matches
        .map((match) => {
          const home = match.home_score ?? "";
          const away = match.away_score ?? "";
          const readonly = !match.can_edit_score;
          const source = scoreSourceLabel(match);
          return `
            <div class="score-row ${readonly ? "readonly" : ""}" data-match-id="${match.id}">
              <span class="team-name">${match.home_team_name || teamLabel(match.home_team)}</span>
              <input class="score-input" type="number" min="0" max="30" inputmode="numeric" value="${home}" ${readonly ? "disabled" : ""} aria-label="${match.home_team_name || teamLabel(match.home_team)} 进球">
              <span class="score-separator">-</span>
              <input class="score-input" type="number" min="0" max="30" inputmode="numeric" value="${away}" ${readonly ? "disabled" : ""} aria-label="${match.away_team_name || teamLabel(match.away_team)} 进球">
              <span class="team-name away">${match.away_team_name || teamLabel(match.away_team)}</span>
              <small class="score-source">${source}</small>
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
    if (!byId[id]?.can_edit_score) return;
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
  if (!state.status?.allowUserScoreInput) return;
  const matches = collectMatchesFromForm();
  const payload = await fetchJson("/api/matches", {
    method: "POST",
    body: JSON.stringify({ matches }),
  });
  state.matches = payload.matches;
  renderMatches();
  renderSchedule();
  setText("#predictionMeta", "比分已保存。点击重新预测查看变化。");
}

async function clearScores() {
  if (!state.status?.allowUserScoreInput) return;
  state.matches = state.matches.map((match) => ({
    ...match,
    home_score: match.can_edit_score ? null : match.home_score,
    away_score: match.can_edit_score ? null : match.away_score,
    status: match.can_edit_score ? "scheduled" : match.status,
  }));
  renderMatches();
  await saveScores();
}

function formatPct(value) {
  const number = Number(value || 0);
  return number >= 0.1 ? `${(number * 100).toFixed(1)}%` : `${(number * 100).toFixed(2)}%`;
}

function topRowsForMetric(rows, metric, limit = 4) {
  return [...rows]
    .filter((row) => Number(row?.[metric] || 0) > 0)
    .sort((a, b) => Number(b?.[metric] || 0) - Number(a?.[metric] || 0))
    .slice(0, limit);
}

function probabilityGapLabel(rows, metric) {
  if (rows.length < 2) return "样本不足，等待更多模拟。";
  const gap = Math.abs(Number(rows[0]?.[metric] || 0) - Number(rows[1]?.[metric] || 0));
  if (gap < 0.03) return "前两名非常接近，随机波动较明显。";
  if (gap < 0.08) return "领先优势不大，阶段结果仍有悬念。";
  return "领先队伍相对清晰，但仍不是确定结论。";
}

function renderStageCandidateCard(card) {
  const maxValue = Math.max(...card.rows.map((row) => Number(row?.[card.valueKey] ?? 0)), 0.001);
  const uncertainty = card.uncertainty || probabilityGapLabel(card.rows, card.uncertaintyMetric);
  const rows = card.rows
    .map((row) => {
      const value = Number(row?.[card.valueKey] ?? 0);
      const width = Math.max(4, Math.round((value / maxValue) * 100));
      const groupHint = row.group ? `<span>${escapeHtml(row.group)} 组</span>` : "";
      return `
        <div class="stage-card-row">
          <div>
            <strong>${escapeHtml(row.team_name || teamLabel(row.team))}</strong>
            ${groupHint}
          </div>
          <span class="stage-card-bar"><i style="width:${width}%"></i></span>
          <b>${formatPct(value)}</b>
        </div>
      `;
    })
    .join("");
  return `
    <article class="stage-card ${card.expanded ? "expanded" : ""}">
      <div class="stage-card-head">
        <span>${escapeHtml(card.title)}</span>
        <strong>${escapeHtml(card.metricLabel)}</strong>
      </div>
      <p>${escapeHtml(card.summary)}</p>
      <div class="stage-card-rows">${rows}</div>
      <small>${escapeHtml(uncertainty)} · ${state.prediction.simulations} 次模拟</small>
    </article>
  `;
}

function renderKnockoutViews() {
  const prediction = state.prediction;
  const r32Grid = $("#knockoutR32Grid");
  const r16Grid = $("#knockoutR16Grid");
  const deepGrid = $("#knockoutDeepGrid");
  if (!r32Grid || !r16Grid || !deepGrid) return;
  if (!prediction?.rows?.length) {
    r32Grid.innerHTML = `<div class="mini-empty">生成预测后显示 32 个进入 32 强概率最高的候选。</div>`;
    r16Grid.innerHTML = `<div class="mini-empty">生成预测后显示 16 个进入 16 强概率最高的候选。</div>`;
    deepGrid.innerHTML = `<div class="mini-empty">生成预测后显示八强、四强和决赛候选。</div>`;
    return;
  }

  r32Grid.innerHTML = renderStageCandidateCard({
    title: "32 强候选",
    metricLabel: "进入 32 强",
    summary: "按晋级 32 强概率列出 32 个主要候选",
    rows: topRowsForMetric(prediction.rows, "r32", 32),
    valueKey: "r32",
    uncertaintyMetric: "r32",
    expanded: true,
  });

  r16Grid.innerHTML = renderStageCandidateCard({
    title: "16 强候选",
    metricLabel: "进入 16 强",
    summary: "按晋级 16 强概率列出 16 个主要候选",
    rows: topRowsForMetric(prediction.rows, "r16", 16),
    valueKey: "r16",
    uncertaintyMetric: "r16",
    expanded: true,
  });

  const cards = [
    { title: "八强", metricLabel: "进入八强", summary: "按晋级八强概率列出 8 个主要候选", rows: topRowsForMetric(prediction.rows, "qf", 8), valueKey: "qf", uncertaintyMetric: "qf" },
    { title: "四强", metricLabel: "进入四强", summary: "四强席位竞争格局", rows: topRowsForMetric(prediction.rows, "sf", 4), valueKey: "sf", uncertaintyMetric: "sf" },
    { title: "决赛", metricLabel: "进入决赛", summary: "决赛席位概率最高的 2 支球队", rows: topRowsForMetric(prediction.rows, "final", 2), valueKey: "final", uncertaintyMetric: "final" },
  ];
  deepGrid.innerHTML = cards
    .map((card) => {
      return renderStageCandidateCard(card);
    })
    .join("");
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
  const finalTable = $("#finalTable");
  const knockoutTable = $("#knockoutStageTable");
  if (!prediction || !ranking || !finalTable || !knockoutTable) return;

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

  finalTable.innerHTML = prediction.rows
    .slice(0, 16)
    .map(
      (row) => `
        <tr>
          <td>${row.team_name || teamLabel(row.team)}</td>
          <td>${formatPct(row.champion)}</td>
          <td>${formatPct(row.final)}</td>
        </tr>
      `
    )
    .join("");

  knockoutTable.innerHTML = prediction.rows
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
  renderKnockoutViews();
  renderQualification();
}

function renderQualification() {
  const grid = $("#qualificationGrid");
  if (!grid) return;
  const groups = state.prediction?.groupQualification || [];
  if (!groups.length) {
    if (!state.groups) {
      grid.innerHTML = `<div class="mini-empty">正在读取正式分组。</div>`;
      return;
    }
    grid.innerHTML = Object.entries(state.groups)
      .map(([group, teams]) => {
        const items = teams.map((team) => `<li>${escapeHtml(team)}</li>`).join("");
        return `
          <article class="qualification-card">
            <div class="group-title">
              <strong>${escapeHtml(group)} 组</strong>
              <span class="pill muted">正式分组</span>
            </div>
            <ul class="team-list">${items}</ul>
          </article>
        `;
      })
      .join("");
    return;
  }
  grid.innerHTML = groups
    .map((group) => {
      const rows = (group.rows || [])
        .map(
          (row) => `
            <tr>
              <td>${escapeHtml(row.team_name || teamLabel(row.team))}</td>
              <td>${formatPct(row.first)}</td>
              <td>${formatPct(row.top_two)}</td>
              <td>${formatPct(row.third)}</td>
              <td><strong>${formatPct(row.qualified)}</strong></td>
            </tr>
          `
        )
        .join("");
      return `
        <article class="qualification-card">
          <div class="group-title">
            <strong>${escapeHtml(group.group)} 组</strong>
            <span class="pill muted">出线概率</span>
          </div>
          <div class="qualification-table-wrap">
            <table class="qualification-table">
              <thead>
                <tr>
                  <th>球队</th>
                  <th>头名</th>
                  <th>前二</th>
                  <th>第三</th>
                  <th>晋级</th>
                </tr>
              </thead>
              <tbody>${rows}</tbody>
            </table>
          </div>
        </article>
      `;
    })
    .join("");
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
    renderScheduleFilters();
    renderMatches();
    renderSchedule();
    renderQualification();
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

function setScheduleView(view) {
  const stageFilter = $("#scheduleStageFilter")?.value || "all";
  if (view === "bracket" && !isKnockoutStageFilter(stageFilter)) return;
  state.scheduleView = view === "list" ? "list" : "bracket";
  syncScheduleViewButtons();
  renderSchedule();
}

function handleScheduleFilterChange() {
  const stageFilter = $("#scheduleStageFilter")?.value || "all";
  state.scheduleView = isKnockoutStageFilter(stageFilter) ? "bracket" : "list";
  syncScheduleViewButtons();
  renderSchedule();
}

function setKnockoutView(view) {
  $$("[data-knockout-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.knockoutView === view);
  });
  $$("[data-knockout-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.knockoutPanel === view);
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
  $("#scheduleStageFilter")?.addEventListener("change", handleScheduleFilterChange);
  $("#scheduleStatusFilter")?.addEventListener("change", renderSchedule);
  $$("[data-schedule-view]").forEach((button) => {
    button.addEventListener("click", () => setScheduleView(button.dataset.scheduleView));
  });
  $$("[data-knockout-view]").forEach((button) => {
    button.addEventListener("click", () => setKnockoutView(button.dataset.knockoutView));
  });
}

hydrateLlmForm();
bindEvents();
refreshApp();
