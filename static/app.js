const state = {
  tasks: [],
  pnrs: [],
  proxyConfigs: [],
  selectedTaskId: "",
  sources: [],
  health: null,
  activeView: "tasks",
  expandedTaskIds: new Set(),
  collapsedTaskIds: new Set(),
};

const els = {
  tabs: document.querySelectorAll(".tabs button[data-view]"),
  viewPages: document.querySelectorAll(".view-page[data-view]"),
  health: document.getElementById("health"),
  refreshBtn: document.getElementById("refreshBtn"),
  source: document.getElementById("source"),
  taskForm: document.getElementById("taskForm"),
  taskRows: document.getElementById("taskRows"),
  taskCount: document.getElementById("taskCount"),
  selectedTask: document.getElementById("selectedTask"),
  detailEmpty: document.getElementById("detailEmpty"),
  detailContent: document.getElementById("detailContent"),
  attemptRows: document.getElementById("attemptRows"),
  lastResult: document.getElementById("lastResult"),
  successCount: document.getElementById("successCount"),
  failureCount: document.getElementById("failureCount"),
  intervalInfo: document.getElementById("intervalInfo"),
  dbInfo: document.getElementById("dbInfo"),
  syncJsonBtn: document.getElementById("syncJsonBtn"),
  taskJson: document.getElementById("taskJson"),
  importJson: document.getElementById("importJson"),
  importBtn: document.getElementById("importBtn"),
  toast: document.getElementById("toast"),
  clearLogBtn: document.getElementById("clearLogBtn"),
  configDbPath: document.getElementById("configDbPath"),
  configRunner: document.getElementById("configRunner"),
  configPoll: document.getElementById("configPoll"),
  configTaskCount: document.getElementById("configTaskCount"),
  configSources: document.getElementById("configSources"),
  sourceProxyRows: document.getElementById("sourceProxyRows"),
  proxyRefreshBtn: document.getElementById("proxyRefreshBtn"),
  pnrRows: document.getElementById("pnrRows"),
  pnrCount: document.getElementById("pnrCount"),
  pnrRefreshBtn: document.getElementById("pnrRefreshBtn"),
};

const formIds = [
  "taskId",
  "taskIdAdvanced",
  "intervalSeconds",
  "maxRuns",
  "maxRunsAdvanced",
  "depAirport",
  "arrAirport",
  "depDate",
  "flightNumber",
  "cabin",
  "currencyCode",
  "currencyCodeAdvanced",
  "bookRate",
  "passengerRange",
  "pnrValidMinutes",
  "callData",
  "callUrl",
  "callUrlAdvanced",
];

const $ = (id) => document.getElementById(id);

function value(id) {
  const element = $(id);
  return element ? element.value.trim() : "";
}

function valueOrDefault(id) {
  const element = $(id);
  if (!element) return "";
  return element.value.trim() || element.dataset.default || "";
}

function numberOrNull(id) {
  const raw = value(id);
  return raw ? Number(raw) : null;
}

function numberOrDefault(id) {
  const raw = valueOrDefault(id);
  return raw ? Number(raw) : null;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json();
}

function normalizeDate(raw) {
  return raw.replaceAll("-", "").replaceAll("/", "").trim();
}

function buildPayloadFromForm() {
  const currency = value("currencyCodeAdvanced") || value("currencyCode") || "MYR";
  const callUrl = value("callUrlAdvanced") || value("callUrl");
  const pnrValidMinutes = numberOrNull("pnrValidMinutes");
  const taskData = {
    depAirport: valueOrDefault("depAirport").toUpperCase(),
    arrAirport: valueOrDefault("arrAirport").toUpperCase(),
    depDate: normalizeDate(valueOrDefault("depDate")),
    flightNumber: valueOrDefault("flightNumber").toUpperCase(),
    cabin: valueOrDefault("cabin").toUpperCase(),
    bookingConfig: {
      bookRate: numberOrDefault("bookRate"),
      currencyCode: currency.toUpperCase(),
    },
    ext: {
      usePassport: $("usePassport").checked,
      ...(pnrValidMinutes ? { pnrValidMinutes } : {}),
    },
    callbackData: {
      callData: value("callData"),
      callUrl,
    },
  };

  return {
    taskId: value("taskIdAdvanced") || value("taskId") || undefined,
    source: value("source"),
    taskType: "shamBooking",
    taskData,
    passengerRange: valueOrDefault("passengerRange"),
    intervalSeconds: numberOrDefault("intervalSeconds") || undefined,
    maxRuns: numberOrNull("maxRunsAdvanced") || numberOrNull("maxRuns") || undefined,
  };
}

function syncJsonFromForm() {
  els.taskJson.value = JSON.stringify(buildPayloadFromForm(), null, 2);
}

function payloadFromEditor() {
  const raw = els.taskJson.value.trim();
  return raw ? JSON.parse(raw) : buildPayloadFromForm();
}

async function loadSources() {
  const data = await api("/api/sources");
  state.sources = data.sources || [];
  els.source.innerHTML = state.sources.map((source) => `<option value="${source}">${source}</option>`).join("");
  if (state.sources.includes("5JWEB")) {
    els.source.value = "5JWEB";
  }
  await loadProxyConfigs();
  renderConfig();
}

async function loadHealth() {
  state.health = await api("/api/health");
  els.health.textContent = `运行中 ${state.health.runner.running}/${runnerLimitText(state.health.runner)}`;
  els.dbInfo.textContent = state.health.dbPath.split("/").pop();
  renderConfig();
}

async function loadTasks() {
  state.tasks = await api("/api/tasks");
  rememberExpandableTasks();
  renderTasks();
  if (state.selectedTaskId && state.tasks.some((task) => task.task_id === state.selectedTaskId)) {
    await selectTask(state.selectedTaskId, false);
  } else if (state.selectedTaskId) {
    clearSelectedTask();
  }
  renderConfig();
}

async function loadProxyConfigs() {
  state.proxyConfigs = await api("/api/source-proxies");
  renderProxyConfigs();
}

function switchView(view) {
  state.activeView = view;
  els.tabs.forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  els.viewPages.forEach((page) => page.classList.toggle("hidden", page.dataset.view !== view));
  if (view === "pnr") {
    loadPnrs().catch(showError);
  }
  if (view === "config") {
    renderConfig();
    if (!state.proxyConfigs.length) {
      loadProxyConfigs().catch(showError);
    }
  }
}

function renderConfig() {
  if (!els.configDbPath) return;
  const runner = state.health?.runner;
  els.configDbPath.textContent = state.health?.dbPath || "-";
  els.configRunner.textContent = runner ? `${runner.running}/${runnerLimitText(runner)}` : "-";
  els.configPoll.textContent = runner ? `${runner.pollInterval} 秒` : "-";
  els.configTaskCount.textContent = `${state.tasks.length} 个任务`;
  els.configSources.innerHTML = state.sources.length
    ? state.sources.map((source) => `<span class="source-pill">${escapeHtml(source)}</span>`).join("")
    : "-";
}

function renderProxyConfigs() {
  if (!els.sourceProxyRows) return;
  const configs = state.proxyConfigs.length
    ? state.proxyConfigs
    : state.sources.map((source) => ({ source, enabled: false }));
  els.sourceProxyRows.innerHTML = configs.map(renderProxyConfigRow).join("");
}

function renderProxyConfigRow(config) {
  return `
    <tr data-source="${escapeHtml(config.source)}">
      <td>${escapeHtml(config.source)}</td>
      <td><input data-proxy-field="enabled" type="checkbox" ${config.enabled ? "checked" : ""} /></td>
      <td><input data-proxy-field="host" placeholder="127.0.0.1 或 host:port" value="${escapeAttr(config.host || "")}" /></td>
      <td><input data-proxy-field="port" type="number" min="1" max="65535" placeholder="9000" value="${escapeAttr(config.port || "")}" /></td>
      <td><input data-proxy-field="username" placeholder="可空" value="${escapeAttr(config.username || "")}" /></td>
      <td><input data-proxy-field="password" type="password" placeholder="可空" value="${escapeAttr(config.password || "")}" /></td>
      <td><input data-proxy-field="region" placeholder="hk/de/us" value="${escapeAttr(config.region || "")}" /></td>
      <td><input data-proxy-field="sessionTime" type="number" min="1" placeholder="10" value="${escapeAttr(config.sessionTime || "")}" /></td>
      <td><input data-proxy-field="format" placeholder="留空自动" value="${escapeAttr(config.format || "")}" /></td>
      <td>
        <div class="row-actions proxy-actions">
          <button data-proxy-action="save" type="button">保存</button>
          <button data-proxy-action="reset" class="danger" type="button">清空</button>
        </div>
      </td>
    </tr>`;
}

function collectProxyRowPayload(row) {
  const field = (name) => row.querySelector(`[data-proxy-field="${name}"]`);
  return {
    enabled: field("enabled").checked,
    host: field("host").value.trim(),
    port: numberFromElement(field("port")),
    username: field("username").value.trim(),
    password: field("password").value.trim(),
    region: field("region").value.trim(),
    sessionTime: numberFromElement(field("sessionTime")),
    format: field("format").value.trim(),
  };
}

function numberFromElement(element) {
  const raw = element.value.trim();
  return raw ? Number(raw) : null;
}

async function handleProxyAction(action, source, row) {
  if (action === "reset") {
    if (!confirm(`清空 ${source} 的代理配置？`)) return;
    await api(`/api/source-proxies/${encodeURIComponent(source)}`, { method: "DELETE" });
    toast(`${source} 代理已清空`);
  } else {
    const payload = collectProxyRowPayload(row);
    await api(`/api/source-proxies/${encodeURIComponent(source)}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    toast(`${source} 代理已保存`);
  }
  await loadProxyConfigs();
}

function renderTasks() {
  const childCount = state.tasks.filter((task) => task.parent_task_id).length;
  const rootCount = state.tasks.length - childCount;
  els.taskCount.textContent = childCount ? `${rootCount} 个主任务 / ${childCount} 个子任务` : `${rootCount} 个任务`;
  if (!state.tasks.length) {
    els.taskRows.innerHTML = `<tr><td colspan="14" class="empty-row">暂无任务，填写上方信息后点击添加任务。</td></tr>`;
    return;
  }
  els.taskRows.innerHTML = renderTaskTreeRows().join("");
}

function rememberExpandableTasks() {
  const parentIds = new Set(state.tasks.filter((task) => task.is_parent).map((task) => task.task_id));
  state.expandedTaskIds.forEach((taskId) => {
    if (!parentIds.has(taskId)) state.expandedTaskIds.delete(taskId);
  });
  state.collapsedTaskIds.forEach((taskId) => {
    if (!parentIds.has(taskId)) state.collapsedTaskIds.delete(taskId);
  });
}

function renderTaskTreeRows() {
  const childrenByParent = new Map();
  const rootRows = [];
  const taskIds = new Set(state.tasks.map((task) => task.task_id));

  state.tasks.forEach((task) => {
    if (task.parent_task_id && taskIds.has(task.parent_task_id)) {
      if (!childrenByParent.has(task.parent_task_id)) childrenByParent.set(task.parent_task_id, []);
      childrenByParent.get(task.parent_task_id).push(task);
    } else {
      rootRows.push(task);
    }
  });

  const rows = [];
  rootRows.forEach((task) => {
    const children = childrenByParent.get(task.task_id) || [];
    rows.push(renderTaskRow(task, { childCount: children.length }));
    if (task.is_parent && state.expandedTaskIds.has(task.task_id)) {
      children.forEach((child, index) => {
        rows.push(renderTaskRow(child, {
          childPosition: index === 0 ? "first" : index === children.length - 1 ? "last" : "middle",
        }));
      });
    }
  });
  return rows;
}

function runnerLimitText(runner) {
  return runner?.unlimited ? "不限" : runner?.concurrency;
}

function renderTaskRow(task, options = {}) {
  const taskData = task.task_data || {};
  const bookingConfig = taskData.bookingConfig || {};
  const selected = task.task_id === state.selectedTaskId ? " selected" : "";
  const isChild = Boolean(task.parent_task_id);
  const isParent = Boolean(task.is_parent);
  const childClass = isChild && options.childPosition ? ` child-${options.childPosition}` : "";
  const passport = inferPassport(taskData) ? "是" : "否";
  const passengerText = isParent ? task.passenger_range || "-" : task.passenger_count || taskData.ext?.passengerCount || "-";
  return `
    <tr class="${selected} ${isParent ? "parent-row" : ""} ${isChild ? "child-row" : ""}${childClass}" data-task-id="${escapeHtml(task.task_id)}">
      <td>
        <div class="task-name">
          ${treeControl(task, options.childCount || 0)}
          <span>${isChild ? `子任务 ${task.child_index || ""}` : "主任务"}</span>
        </div>
      </td>
      <td class="task-id-cell">${renderTaskIdCell(task.task_id)}</td>
      <td>${escapeHtml(taskData.depAirport || "-")}</td>
      <td>${escapeHtml(taskData.arrAirport || "-")}</td>
      <td>${escapeHtml(formatDepDate(taskData.depDate))}</td>
      <td>${escapeHtml(taskData.flightNumber || "-")}</td>
      <td>${escapeHtml(taskData.cabin || "-")}</td>
      <td>${escapeHtml(task.interval_seconds || "-")}</td>
      <td>${escapeHtml(bookingConfig.bookRate || "-")}</td>
      <td>${escapeHtml(passengerText)}</td>
      <td>${escapeHtml(task.run_count || "-")}</td>
      <td>${renderStatusBadge(task)}</td>
      <td>${passport}</td>
      <td>
        ${renderTaskActions(task)}
      </td>
    </tr>`;
}

function renderTaskActions(task) {
  if (task.parent_task_id) {
    return `<span class="no-actions">-</span>`;
  }
  const toggleAction = task.status === "ACTIVE" ? "pause" : "resume";
  const toggleLabel = task.status === "ACTIVE" ? "暂停" : "开始";
  const toggleIcon = task.status === "ACTIVE" ? "pause" : "play";
  return `
    <div class="row-actions">
      <button class="action-button" data-action="${toggleAction}" data-task-id="${escapeHtml(task.task_id)}">
        ${renderIcon(toggleIcon)}<span>${toggleLabel}</span>
      </button>
      <button class="action-button" data-action="copy" data-task-id="${escapeHtml(task.task_id)}">
        ${renderIcon("copy")}<span>复制</span>
      </button>
      <button class="action-button danger" data-action="delete" data-task-id="${escapeHtml(task.task_id)}">
        ${renderIcon("trash")}<span>删除</span>
      </button>
    </div>`;
}

function treeControl(task, childCount) {
  if (task.is_parent && childCount > 0) {
    const expanded = state.expandedTaskIds.has(task.task_id);
    return `
      <button
        class="tree-toggle"
        type="button"
        data-expand-task-id="${escapeAttr(task.task_id)}"
        title="${expanded ? "收起子任务" : "展开子任务"}"
        aria-label="${expanded ? "收起子任务" : "展开子任务"}"
      >${expanded ? "▾" : "▸"}</button>
      <span class="child-count">${childCount}</span>`;
  }
  return task.parent_task_id ? `<span class="tree-branch" aria-hidden="true"></span>` : `<span class="tree-marker"></span>`;
}

function statusText(status, task) {
  if (task.in_flight) return "执行中";
  if (status === "ACTIVE") return "静默";
  if (status === "PAUSED") return "已停止";
  if (status === "STOPPED") return "已结束";
  return status || "-";
}

function statusMeta(task) {
  if (task.in_flight) return { label: "执行中", variant: "running" };
  if (task.status === "PAUSED") return { label: "已暂停", variant: "paused" };
  if (task.status === "STOPPED") return { label: "已结束", variant: "stopped" };
  if (task.last_status_code !== null && task.last_status_code !== undefined && Number(task.last_status_code) !== 200) {
    return { label: "失败", variant: "failed" };
  }
  if (task.status === "ACTIVE") return { label: "静默", variant: "idle" };
  return { label: task.status || "-", variant: "neutral" };
}

function renderStatusBadge(task) {
  const meta = statusMeta(task);
  return `
    <span class="status-badge ${meta.variant}">
      <span class="status-dot" aria-hidden="true"></span>
      ${escapeHtml(meta.label)}
    </span>`;
}

function renderTaskIdCell(taskId) {
  return `
    <div class="task-id-wrap" title="${escapeAttr(taskId)}">
      <code>${escapeHtml(abbreviateTaskId(taskId))}</code>
      <button class="icon-button copy-id-button" data-copy-task-id="${escapeAttr(taskId)}" type="button" aria-label="复制任务 ID">
        ${renderIcon("copy")}
      </button>
    </div>`;
}

function abbreviateTaskId(taskId) {
  const value = String(taskId || "");
  if (value.length <= 24) return value || "-";
  return `${value.slice(0, 9)}...${value.slice(-7)}`;
}

function inferPassport(taskData) {
  const ext = taskData.ext || {};
  if (typeof ext.usePassport === "boolean") return ext.usePassport;
  return $("usePassport").checked;
}

function extractPassengerCount(result) {
  const passengers = extractPassengers(result);
  return Array.isArray(passengers) ? passengers.length : null;
}

function extractPassengers(result) {
  const passengers = result?.data?.passengers || result?.passengers;
  return Array.isArray(passengers) ? passengers : [];
}

async function loadPnrs(announce = false) {
  const sourceTasks = state.tasks.length ? state.tasks : await api("/api/tasks");
  const candidates = sourceTasks.filter((task) => !task.is_parent && (task.success_count > 0 || extractPnr(task.last_result)));
  const details = await Promise.all(
    candidates.map(async (task) => {
      try {
        return await api(`/api/tasks/${encodeURIComponent(task.task_id)}`);
      } catch {
        return task;
      }
    }),
  );
  const seen = new Set();
  const rows = [];
  details.forEach((task) => {
    (task.attempts || []).forEach((attempt) => {
      collectPnrRow(rows, seen, task, attempt.raw_result, attempt);
    });
    collectPnrRow(rows, seen, task, task.last_result, null);
  });
  state.pnrs = rows.sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0));
  renderPnrs();
  if (announce) toast("PNR 已刷新");
}

function collectPnrRow(rows, seen, task, result, attempt) {
  if (!result || Number(result.status || 0) !== 200) return;
  const data = result.data || {};
  const pnr = extractPnr(result);
  if (!pnr) return;
  const key = `${task.task_id}:${pnr}:${attempt?.attempt_no || "last"}`;
  if (seen.has(key)) return;
  seen.add(key);
  const taskData = task.task_data || {};
  const pnrCreatedAt = attempt?.finished_at || task.updated_at || 0;
  const pnrValidMinutes = pnrValidMinutesForTask(task);
  const expiresAt = pnrCreatedAt && pnrValidMinutes ? pnrCreatedAt + pnrValidMinutes * 60 : 0;
  rows.push({
    taskId: task.task_id,
    pnr,
    source: task.source,
    flightNumber: taskData.flightNumber || "-",
    depAirport: taskData.depAirport || "-",
    arrAirport: taskData.arrAirport || "-",
    depDate: taskData.depDate || "-",
    passengerCount: extractPassengerCount(result) ?? "-",
    passengers: extractPassengerNames(result),
    orderState: data.orderState || result.message || "-",
    createdAt: pnrCreatedAt,
    expiresAt,
  });
}

function extractPnr(result) {
  const data = result?.data || {};
  return data.pnr || result?.pnr || "";
}

function pnrValidMinutesForTask(task) {
  const ext = task.task_data?.ext || {};
  const raw = ext.pnrValidMinutes || ext.pnrValidityMinutes || ext.pnrValidMinute;
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 ? value : null;
}

function extractPassengerNames(result) {
  const names = extractPassengers(result)
    .map((passenger) => {
      const lastName = passenger.lastName || passenger.last_name || "";
      const firstName = passenger.firstName || passenger.first_name || "";
      const joined = [lastName, firstName].filter(Boolean).join("/");
      return joined || passenger.name || passenger.passengerName || "";
    })
    .filter(Boolean);
  return names.length ? names.join(", ") : "-";
}

function renderPnrs() {
  els.pnrCount.textContent = `${state.pnrs.length} 条`;
  if (!state.pnrs.length) {
    els.pnrRows.innerHTML = `<tr><td colspan="12" class="empty-row">暂无成功 PNR 记录。</td></tr>`;
    return;
  }
  els.pnrRows.innerHTML = state.pnrs
    .map(
      (row) => `
        <tr data-task-id="${escapeHtml(row.taskId)}">
          <td title="${escapeHtml(row.pnr)}">${escapeHtml(row.pnr)}</td>
          <td title="${escapeAttr(row.taskId)}">${renderTaskIdCell(row.taskId)}</td>
          <td>${escapeHtml(row.source)}</td>
          <td>${escapeHtml(row.flightNumber)}</td>
          <td>${escapeHtml(row.depAirport)}</td>
          <td>${escapeHtml(row.arrAirport)}</td>
          <td>${escapeHtml(formatDepDate(row.depDate))}</td>
          <td>${escapeHtml(row.passengerCount)}</td>
          <td title="${escapeAttr(row.passengers)}">${escapeHtml(row.passengers)}</td>
          <td>${escapeHtml(row.orderState)}</td>
          <td>${row.createdAt ? escapeHtml(formatTime(row.createdAt)) : "-"}</td>
          <td>${row.expiresAt ? escapeHtml(formatTime(row.expiresAt)) : "-"}</td>
        </tr>`,
    )
    .join("");
}

function clearSelectedTask() {
  state.selectedTaskId = "";
  els.selectedTask.textContent = "未选择";
  els.detailEmpty.classList.remove("hidden");
  els.detailContent.classList.add("hidden");
  els.lastResult.innerHTML = "";
  els.attemptRows.innerHTML = "";
}

async function selectTask(taskId, announce = true) {
  const task = await api(`/api/tasks/${encodeURIComponent(taskId)}`);
  state.selectedTaskId = taskId;
  els.selectedTask.textContent = taskId;
  els.detailEmpty.classList.add("hidden");
  els.detailContent.classList.remove("hidden");
  if (task.is_parent) {
    renderParentTaskDetail(task);
  } else {
    renderChildTaskDetail(task);
  }
  renderTasks();
  if (announce) toast("已加载任务详情");
}

function renderChildTaskDetail(task) {
  els.successCount.textContent = task.success_count || 0;
  els.failureCount.textContent = task.failure_count || 0;
  els.intervalInfo.textContent = `${task.interval_seconds || "-"} 秒`;
  setResultJson(task.last_result || {});
  renderAttempts(task.attempts || []);
}

function renderParentTaskDetail(task) {
  const children = childTasksFor(task.task_id);
  els.successCount.textContent = sumBy(children, "success_count");
  els.failureCount.textContent = sumBy(children, "failure_count");
  els.intervalInfo.textContent = "主任务不执行";
  setResultJson(
    {
      taskId: task.task_id,
      type: "parent",
      message: "主任务只负责拆分子任务；真实执行和 Log 都在子任务维度。",
      passengerRange: task.passenger_range || "-",
      childCount: children.length,
    }
  );
  renderChildSummaries(children);
}

function childTasksFor(parentTaskId) {
  return state.tasks
    .filter((task) => task.parent_task_id === parentTaskId)
    .sort((a, b) => (a.child_index || 0) - (b.child_index || 0));
}

function sumBy(items, key) {
  return items.reduce((total, item) => total + Number(item[key] || 0), 0);
}

function renderChildSummaries(children) {
  if (!children.length) {
    els.attemptRows.innerHTML = `<tr><td colspan="5">暂无子任务</td></tr>`;
    return;
  }
  els.attemptRows.innerHTML = children
    .map((child) => {
      const passengerCount = child.passenger_count || child.task_data?.ext?.passengerCount || "-";
      const message = `子任务ID: ${child.task_id} / 人数: ${passengerCount} / 执行: ${child.run_count || 0}`;
      return `
        <tr data-task-id="${escapeHtml(child.task_id)}" class="child-summary-row">
          <td>${escapeHtml(child.child_index || "-")}</td>
          <td>${renderStatusBadge(child)}</td>
          <td title="${escapeAttr(message)}">${escapeHtml(message)}</td>
          <td>-</td>
          <td>${child.updated_at ? escapeHtml(formatTime(child.updated_at)) : "-"}</td>
        </tr>`;
    })
    .join("");
}

function renderAttempts(attempts) {
  if (!attempts.length) {
    els.attemptRows.innerHTML = `<tr><td colspan="5">暂无执行记录</td></tr>`;
    return;
  }
  els.attemptRows.innerHTML = attempts
    .map((attempt) => {
      const prefix = `[${formatLogTime(attempt.finished_at || attempt.started_at)}]`;
      const severity = attemptSeverity(attempt);
      return `
        <tr class="attempt-row ${severity}">
          <td>${attempt.attempt_no}</td>
          <td>${escapeHtml(attempt.status)}</td>
          <td><span class="log-message ${severity}">${escapeHtml(`${prefix} ${attempt.message || "-"}`)}</span></td>
          <td>${attempt.duration_seconds ? attempt.duration_seconds.toFixed(2) + "s" : "-"}</td>
          <td>${attempt.finished_at ? escapeHtml(formatTime(attempt.finished_at)) : "-"}</td>
        </tr>`;
    })
    .join("");
}

async function handleTaskAction(action, taskId) {
  if (action === "copy") {
    const task = state.tasks.find((item) => item.task_id === taskId);
    if (task) copyTaskToForm(task);
    return;
  }
  if (action === "delete" && !confirm(`删除任务 ${taskId}？`)) return;
  const method = action === "delete" ? "DELETE" : "POST";
  const suffix = action === "delete" ? "" : `/${action}`;
  await api(`/api/tasks/${encodeURIComponent(taskId)}${suffix}`, { method });
  toast("操作已提交");
  await loadTasks();
}

function copyTaskToForm(task) {
  const data = task.task_data || {};
  const booking = data.bookingConfig || {};
  $("taskIdAdvanced").value = "";
  $("maxRunsAdvanced").value = task.max_runs || "";
  $("source").value = task.source;
  $("depAirport").value = data.depAirport || "";
  $("arrAirport").value = data.arrAirport || "";
  $("depDate").value = formatDepDate(data.depDate);
  $("flightNumber").value = data.flightNumber || "";
  $("cabin").value = data.cabin || "";
  $("intervalSeconds").value = task.interval_seconds || "";
  $("bookRate").value = booking.bookRate || "";
  $("passengerRange").value = task.passenger_range || (task.passenger_count ? `${task.passenger_count}-${task.passenger_count}` : "");
  $("pnrValidMinutes").value = data.ext?.pnrValidMinutes || "";
  $("currencyCodeAdvanced").value = booking.currencyCode || "";
  $("callUrlAdvanced").value = data.callbackData?.callUrl || "";
  $("callData").value = data.callbackData?.callData || "";
  $("usePassport").checked = inferPassport(data);
  syncJsonFromForm();
  toast("已复制到上方表单");
}

async function submitTask(event) {
  event.preventDefault();
  syncAdvancedFields();
  const payload = payloadFromEditor();
  await api("/api/tasks", { method: "POST", body: JSON.stringify(payload) });
  toast("任务已添加");
  resetFormDefaults();
  await loadTasks();
}

async function importTasks() {
  const raw = els.importJson.value.trim();
  if (!raw) {
    toast("请先粘贴任务 JSON");
    return;
  }
  const parsed = JSON.parse(raw);
  const result = await api("/api/tasks/import", {
    method: "POST",
    body: JSON.stringify({ tasks: parsed, replaceExisting: true }),
  });
  toast(`已导入 ${result.count} 个任务`);
  els.importJson.value = "";
  await loadTasks();
}

function syncAdvancedFields() {
  $("taskId").value = value("taskIdAdvanced");
  $("maxRuns").value = value("maxRunsAdvanced");
  $("currencyCode").value = value("currencyCodeAdvanced") || value("currencyCode") || "MYR";
  $("callUrl").value = value("callUrlAdvanced") || value("callUrl");
}

function resetFormDefaults() {
  $("taskForm").reset();
  if (state.sources.includes("5JWEB")) $("source").value = "5JWEB";
  $("currencyCode").value = "MYR";
  $("currencyCodeAdvanced").value = "MYR";
  $("usePassport").checked = true;
  syncJsonFromForm();
}

function formatDepDate(value) {
  const raw = String(value || "");
  if (/^\d{8}$/.test(raw)) return `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}`;
  return raw || "-";
}

function formatTime(seconds) {
  return new Date(seconds * 1000).toLocaleString("zh-CN", { hour12: false });
}

function formatLogTime(seconds) {
  if (!seconds) return "--:--:--";
  return new Date(seconds * 1000).toLocaleTimeString("zh-CN", { hour12: false });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value);
}

function setResultJson(value) {
  const text = JSON.stringify(value || {}, null, 2);
  els.lastResult.innerHTML = syntaxHighlightJson(text);
}

function syntaxHighlightJson(text) {
  return escapeHtml(text).replace(
    /("(?:\\u[\da-fA-F]{4}|\\[^u]|[^\\"])*"(?:\s*:)?|\btrue\b|\bfalse\b|\bnull\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g,
    (match) => {
      let cls = "json-number";
      if (match.startsWith('"')) cls = match.endsWith(":") ? "json-key" : "json-string";
      else if (match === "true" || match === "false") cls = "json-boolean";
      else if (match === "null") cls = "json-null";
      return `<span class="${cls}">${match}</span>`;
    },
  );
}

function attemptSeverity(attempt) {
  const status = String(attempt.status || "").toUpperCase();
  const message = String(attempt.message || "");
  if (status.includes("FAIL") || /失败|异常|错误|无可用|售完|不足|不可用/.test(message)) return "error";
  if (/警告|等待|重试/.test(message)) return "warning";
  if (status.includes("SUCCESS")) return "success";
  return "neutral";
}

async function copyText(text, label = "内容") {
  try {
    await navigator.clipboard.writeText(text);
    toast(`${label}已复制`);
  } catch {
    toast("复制失败，请手动复制");
  }
}

function renderIcon(name) {
  const icons = {
    play: '<path d="M8 5v14l11-7z"></path>',
    pause: '<path d="M8 5h4v14H8z"></path><path d="M16 5h4v14h-4z"></path>',
    copy: '<path d="M8 8h10v10H8z"></path><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>',
    trash: '<path d="M3 6h18"></path><path d="M8 6V4h8v2"></path><path d="M6 6l1 16h10l1-16"></path><path d="M10 11v6"></path><path d="M14 11v6"></path>',
  };
  return `<svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true">${icons[name] || ""}</svg>`;
}

function toast(message) {
  els.toast.textContent = message;
  els.toast.classList.remove("hidden");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => els.toast.classList.add("hidden"), 2400);
}

function bindEvents() {
  els.tabs.forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.view));
  });
  els.refreshBtn.addEventListener("click", () => refreshAll().catch(showError));
  els.proxyRefreshBtn.addEventListener("click", () => loadProxyConfigs().catch(showError));
  els.pnrRefreshBtn.addEventListener("click", () => loadPnrs(true).catch(showError));
  els.syncJsonBtn.addEventListener("click", () => {
    syncAdvancedFields();
    syncJsonFromForm();
  });
  els.taskForm.addEventListener("submit", (event) => submitTask(event).catch(showError));
  els.importBtn.addEventListener("click", () => importTasks().catch(showError));
  els.clearLogBtn.addEventListener("click", () => {
    clearSelectedTask();
  });
  formIds.forEach((id) => {
    const element = $(id);
    if (element) element.addEventListener("input", syncJsonFromForm);
  });
  $("usePassport").addEventListener("change", syncJsonFromForm);
  els.source.addEventListener("change", syncJsonFromForm);
  els.taskRows.addEventListener("click", (event) => {
    const copyButton = event.target.closest("button[data-copy-task-id]");
    if (copyButton) {
      copyText(copyButton.dataset.copyTaskId, "任务 ID").catch(showError);
      return;
    }
    const expandButton = event.target.closest("button[data-expand-task-id]");
    if (expandButton) {
      toggleTaskExpand(expandButton.dataset.expandTaskId);
      return;
    }
    const actionButton = event.target.closest("button[data-action]");
    if (actionButton) {
      handleTaskAction(actionButton.dataset.action, actionButton.dataset.taskId).catch(showError);
      return;
    }
    const row = event.target.closest("tr[data-task-id]");
    if (row) selectTask(row.dataset.taskId).catch(showError);
  });
  els.attemptRows.addEventListener("click", (event) => {
    const row = event.target.closest("tr[data-task-id]");
    if (row) selectTask(row.dataset.taskId).catch(showError);
  });
  els.pnrRows.addEventListener("click", (event) => {
    const copyButton = event.target.closest("button[data-copy-task-id]");
    if (copyButton) {
      copyText(copyButton.dataset.copyTaskId, "任务 ID").catch(showError);
      return;
    }
    const row = event.target.closest("tr[data-task-id]");
    if (!row) return;
    switchView("tasks");
    selectTask(row.dataset.taskId).catch(showError);
  });
  els.sourceProxyRows.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-proxy-action]");
    if (!button) return;
    const row = button.closest("tr[data-source]");
    handleProxyAction(button.dataset.proxyAction, row.dataset.source, row).catch(showError);
  });
}

function toggleTaskExpand(taskId) {
  if (state.expandedTaskIds.has(taskId)) {
    state.expandedTaskIds.delete(taskId);
    state.collapsedTaskIds.add(taskId);
  } else {
    state.expandedTaskIds.add(taskId);
    state.collapsedTaskIds.delete(taskId);
  }
  renderTasks();
}

async function refreshAll() {
  await loadHealth();
  await loadTasks();
  if (state.activeView === "pnr") {
    await loadPnrs();
  }
}

function showError(error) {
  console.error(error);
  toast(error.message || String(error));
}

async function init() {
  bindEvents();
  await loadSources();
  resetFormDefaults();
  await refreshAll();
  setInterval(() => refreshAll().catch(showError), 5000);
}

init().catch(showError);
