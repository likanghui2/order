const state = {
  tasks: [],
  pnrs: [],
  pnrTotal: 0,
  pnrPage: 1,
  pnrHasMore: false,
  pnrLoading: false,
  pnrReloadQueued: false,
  pnrQueuedReset: false,
  pnrQueuedPage: null,
  pnrFilterTimer: null,
  proxyConfigs: [],
  selectedTaskId: "",
  sources: [],
  health: null,
  activeView: "tasks",
  expandedTaskIds: new Set(),
  collapsedTaskIds: new Set(),
  pnrDatePickerMonth: null,
  confirmResolver: null,
  confirmPreviousFocus: null,
  tableImportItems: [],
};

const els = {
  tabs: document.querySelectorAll(".tabs button[data-view]"),
  viewPages: document.querySelectorAll(".view-page[data-view]"),
  health: document.getElementById("health"),
  refreshBtn: document.getElementById("refreshBtn"),
  source: document.getElementById("source"),
  taskForm: document.getElementById("taskForm"),
  tasksWorkspace: document.getElementById("tasksWorkspace"),
  taskRows: document.getElementById("taskRows"),
  taskCount: document.getElementById("taskCount"),
  logSection: document.getElementById("logSection"),
  selectedTask: document.getElementById("selectedTask"),
  detailEmpty: document.getElementById("detailEmpty"),
  detailContent: document.getElementById("detailContent"),
  attemptRows: document.getElementById("attemptRows"),
  lastResult: document.getElementById("lastResult"),
  successCount: document.getElementById("successCount"),
  failureCount: document.getElementById("failureCount"),
  intervalInfo: document.getElementById("intervalInfo"),
  dbInfo: document.getElementById("dbInfo"),
  tableImportPanel: document.getElementById("tableImportPanel"),
  tableImportFile: document.getElementById("tableImportFile"),
  tableImportFileName: document.getElementById("tableImportFileName"),
  tableImportRows: document.getElementById("tableImportRows"),
  tableImportCount: document.getElementById("tableImportCount"),
  tableImportTemplateBtn: document.getElementById("tableImportTemplateBtn"),
  tableImportParseBtn: document.getElementById("tableImportParseBtn"),
  tableImportSubmitBtn: document.getElementById("tableImportSubmitBtn"),
  tableImportClearBtn: document.getElementById("tableImportClearBtn"),
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
  pnrTaskIdFilter: document.getElementById("pnrTaskIdFilter"),
  pnrPnrFilter: document.getElementById("pnrPnrFilter"),
  pnrSourceFilter: document.getElementById("pnrSourceFilter"),
  pnrFlightFilter: document.getElementById("pnrFlightFilter"),
  pnrCabinFilter: document.getElementById("pnrCabinFilter"),
  pnrDepFilter: document.getElementById("pnrDepFilter"),
  pnrArrFilter: document.getElementById("pnrArrFilter"),
  pnrDateFilter: document.getElementById("pnrDateFilter"),
  pnrDatePickerPanel: document.getElementById("pnrDatePickerPanel"),
  pnrPeopleFilter: document.getElementById("pnrPeopleFilter"),
  pnrPassengerFilter: document.getElementById("pnrPassengerFilter"),
  pnrExpiredFilter: document.getElementById("pnrExpiredFilter"),
  pnrResetFiltersBtn: document.getElementById("pnrResetFiltersBtn"),
  pnrPageInfo: document.getElementById("pnrPageInfo"),
  pnrPrevPageBtn: document.getElementById("pnrPrevPageBtn"),
  pnrNextPageBtn: document.getElementById("pnrNextPageBtn"),
  confirmOverlay: document.getElementById("confirmOverlay"),
  confirmTitle: document.getElementById("confirmTitle"),
  confirmMessage: document.getElementById("confirmMessage"),
  confirmOkBtn: document.getElementById("confirmOkBtn"),
  confirmCancelBtn: document.getElementById("confirmCancelBtn"),
};

const PNR_PAGE_SIZE = 100;

const TABLE_IMPORT_COLUMNS = [
  { key: "source", label: "Source", aliases: ["source", "数据源", "站点"] },
  { key: "depAirport", label: "出发地", aliases: ["出发地", "出发", "dep", "depairport"] },
  { key: "arrAirport", label: "目的地", aliases: ["目的地", "到达地", "到达", "arr", "arrairport"] },
  { key: "depDate", label: "日期", aliases: ["日期", "出发日期", "depdate", "date"] },
  { key: "flightNumber", label: "航班号", aliases: ["航班号", "航班", "flight", "flightnumber"] },
  { key: "cabin", label: "舱位", aliases: ["舱位", "仓位", "cabin"] },
  { key: "intervalSeconds", label: "查询延迟", aliases: ["查询延迟", "查询间隔", "interval", "intervalseconds"] },
  { key: "bookRate", label: "预计延迟", aliases: ["预计延迟", "预计延迟秒", "bookrate"] },
  { key: "passengerRange", label: "人数", aliases: ["人数", "乘客数", "passengerrange", "passengers"] },
  { key: "pnrValidMinutes", label: "PNR有效期", aliases: ["pnr有效期", "有效期", "pnrvalidminutes"] },
  { key: "usePassport", label: "护照", aliases: ["护照", "使用护照", "usepassport", "passport"] },
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
  const isFormData = options.body instanceof FormData;
  const headers = isFormData ? {} : { "Content-Type": "application/json" };
  const response = await fetch(path, {
    ...options,
    headers: {
      ...headers,
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json();
}

function normalizeDate(raw) {
  return String(raw || "").replaceAll("-", "").replaceAll("/", "").trim();
}

function buildPayloadFromForm() {
  const currency = value("currencyCode") || "MYR";
  const callUrl = value("callUrl");
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
    taskId: value("taskId") || undefined,
    source: value("source"),
    taskType: "shamBooking",
    taskData,
    passengerRange: valueOrDefault("passengerRange"),
    intervalSeconds: numberOrDefault("intervalSeconds") || undefined,
    maxRuns: numberOrNull("maxRuns") || undefined,
  };
}

async function loadSources() {
  const data = await api("/api/sources");
  state.sources = data.sources || [];
  els.source.innerHTML = state.sources.map((source) => `<option value="${source}">${source}</option>`).join("");
  if (state.sources.includes("5JWEB")) {
    els.source.value = "5JWEB";
  }
  renderPnrFilterOptions();
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
  if (view === "tasks") {
    loadTasks().catch(showError);
  }
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
    const confirmed = await showConfirmDialog({
      title: "清空代理配置",
      message: `确认清空 ${source} 的代理配置？清空后该数据源会恢复为不使用代理。`,
      confirmText: "清空",
    });
    if (!confirmed) return;
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

async function parseTableImport(announce = true) {
  const file = els.tableImportFile?.files?.[0];
  if (!file) {
    state.tableImportItems = [];
    renderTableImportPreview();
    if (announce) toast("请先选择表格文件");
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  const result = await api("/api/table-import/preview", {
    method: "POST",
    body: formData,
  });
  loadTableImportRows(result.rows || [], announce);
}

function loadTableImportRows(tableRows, announce = true) {
  const rows = tableRows
    .map((cells) => (cells || []).map((cell) => String(cell || "").trim()))
    .filter((cells) => cells.some((cell) => cell));
  if (!rows.length) {
    state.tableImportItems = [];
    renderTableImportPreview();
    if (announce) toast("表格文件没有可解析的数据");
    return;
  }
  const header = tableImportHeader(rows[0]);
  const dataRows = header.hasHeader ? rows.slice(1) : rows;
  state.tableImportItems = dataRows
    .filter((cells) => cells.some((cell) => String(cell || "").trim()))
    .map((cells, index) => buildTableImportItem(cells, header.indexByKey, index + 1));
  renderTableImportPreview();
  if (announce) {
    const validCount = state.tableImportItems.filter((item) => !item.errors.length).length;
    toast(`已解析 ${state.tableImportItems.length} 行，${validCount} 行有效`);
  }
}

async function downloadTableImportTemplate() {
  const response = await fetch("/api/table-import/template");
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "模板下载失败");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "sham-booking-table-template.xlsx";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function tableImportHeader(cells) {
  const indexByKey = {};
  cells.forEach((cell, index) => {
    const key = tableImportKeyForHeader(cell);
    if (key && indexByKey[key] === undefined) indexByKey[key] = index;
  });
  const hasHeader = Object.keys(indexByKey).length >= 2;
  if (hasHeader) return { hasHeader, indexByKey };
  return {
    hasHeader,
    indexByKey: Object.fromEntries(TABLE_IMPORT_COLUMNS.map((column, index) => [column.key, index])),
  };
}

function tableImportKeyForHeader(value) {
  const normalized = normalizeImportHeader(value);
  const column = TABLE_IMPORT_COLUMNS.find((item) => item.aliases.some((alias) => normalizeImportHeader(alias) === normalized));
  return column?.key || "";
}

function normalizeImportHeader(value) {
  return String(value || "").toLowerCase().replace(/[\s:_：\-\/（）()]/g, "");
}

function buildTableImportItem(cells, indexByKey, rowNumber) {
  const raw = Object.fromEntries(TABLE_IMPORT_COLUMNS.map((column) => [column.key, tableCell(cells, indexByKey[column.key])]));
  const payload = buildPayloadFromTableImport(raw);
  return {
    rowNumber,
    raw,
    payload,
    errors: validateTableImportPayload(payload, raw),
  };
}

function tableCell(cells, index) {
  return index === undefined ? "" : String(cells[index] || "").trim();
}

function buildPayloadFromTableImport(raw) {
  const pnrValidMinutes = positiveNumber(raw.pnrValidMinutes || value("pnrValidMinutes"));
  const taskData = {
    depAirport: (raw.depAirport || valueOrDefault("depAirport")).toUpperCase(),
    arrAirport: (raw.arrAirport || valueOrDefault("arrAirport")).toUpperCase(),
    depDate: normalizeDate(raw.depDate || valueOrDefault("depDate")),
    flightNumber: (raw.flightNumber || valueOrDefault("flightNumber")).toUpperCase(),
    cabin: (raw.cabin || value("cabin")).toUpperCase(),
    bookingConfig: {
      bookRate: positiveNumber(raw.bookRate) || numberOrDefault("bookRate"),
      currencyCode: (value("currencyCode") || "MYR").toUpperCase(),
    },
    ext: {
      usePassport: parseBoolean(raw.usePassport, $("usePassport").checked),
      ...(pnrValidMinutes ? { pnrValidMinutes } : {}),
    },
    callbackData: {
      callData: "",
      callUrl: value("callUrl"),
    },
  };
  return {
    source: (raw.source || value("source")).toUpperCase(),
    taskType: "shamBooking",
    taskData,
    passengerRange: raw.passengerRange || valueOrDefault("passengerRange"),
    intervalSeconds: positiveNumber(raw.intervalSeconds) || numberOrDefault("intervalSeconds") || undefined,
    maxRuns: numberOrNull("maxRuns") || undefined,
  };
}

function positiveNumber(value) {
  const number = Number(String(value || "").trim());
  return Number.isFinite(number) && number > 0 ? number : null;
}

function parseBoolean(value, fallback) {
  const text = String(value || "").trim().toLowerCase();
  if (!text) return fallback;
  if (["1", "true", "yes", "y", "是", "启用", "使用"].includes(text)) return true;
  if (["0", "false", "no", "n", "否", "不", "不用"].includes(text)) return false;
  return fallback;
}

function validateTableImportPayload(payload, raw) {
  const errors = [];
  const taskData = payload.taskData || {};
  if (!payload.source) errors.push("缺少 Source");
  if (state.sources.length && payload.source && !state.sources.includes(payload.source)) errors.push("Source 不支持");
  if (!taskData.depAirport) errors.push("缺少出发地");
  if (!taskData.arrAirport) errors.push("缺少目的地");
  if (!/^\d{8}$/.test(taskData.depDate || "")) errors.push("日期格式错误");
  if (!taskData.flightNumber) errors.push("缺少航班号");
  if (!payload.intervalSeconds || payload.intervalSeconds <= 0) errors.push("查询延迟无效");
  if (!taskData.bookingConfig?.bookRate || taskData.bookingConfig.bookRate <= 0) errors.push("预计延迟无效");
  if (!payload.passengerRange) errors.push("缺少人数");
  if (raw.pnrValidMinutes && !positiveNumber(raw.pnrValidMinutes)) errors.push("PNR有效期无效");
  return errors;
}

function renderTableImportPreview() {
  const items = state.tableImportItems;
  const validCount = items.filter((item) => !item.errors.length).length;
  els.tableImportCount.textContent = items.length ? `${validCount} 行有效 / ${items.length} 行` : "选择表格文件后解析预览";
  els.tableImportSubmitBtn.disabled = validCount === 0;
  if (!items.length) {
    els.tableImportRows.innerHTML = `<tr><td colspan="13" class="empty-row">暂无预览。</td></tr>`;
    return;
  }
  els.tableImportRows.innerHTML = items.map(renderTableImportRow).join("");
}

function resetTableImport() {
  if (els.tableImportFile) els.tableImportFile.value = "";
  if (els.tableImportFileName) els.tableImportFileName.textContent = "未选择文件";
  state.tableImportItems = [];
  renderTableImportPreview();
  els.tableImportPanel.classList.add("hidden");
}

function renderTableImportRow(item) {
  const data = item.payload.taskData;
  const status = item.errors.length ? item.errors.join("，") : "有效";
  return `
    <tr class="${item.errors.length ? "invalid" : "valid"}">
      <td>${item.rowNumber}</td>
      <td>${escapeHtml(item.payload.source || "-")}</td>
      <td>${escapeHtml(data.depAirport || "-")}</td>
      <td>${escapeHtml(data.arrAirport || "-")}</td>
      <td>${escapeHtml(formatDepDate(data.depDate))}</td>
      <td>${escapeHtml(data.flightNumber || "-")}</td>
      <td>${escapeHtml(data.cabin || "-")}</td>
      <td>${escapeHtml(item.payload.intervalSeconds || "-")}</td>
      <td>${escapeHtml(data.bookingConfig?.bookRate || "-")}</td>
      <td>${escapeHtml(item.payload.passengerRange || "-")}</td>
      <td>${escapeHtml(data.ext?.pnrValidMinutes || "-")}</td>
      <td>${data.ext?.usePassport ? "是" : "否"}</td>
      <td><span class="import-status ${item.errors.length ? "invalid" : "valid"}">${escapeHtml(status)}</span></td>
    </tr>`;
}

async function submitTableImport() {
  if (!state.tableImportItems.length) await parseTableImport(false);
  const validItems = state.tableImportItems.filter((item) => !item.errors.length);
  if (!validItems.length) {
    toast("没有有效的导入行");
    return;
  }
  let successCount = 0;
  const failures = [];
  for (const item of validItems) {
    try {
      await api("/api/tasks", { method: "POST", body: JSON.stringify(item.payload) });
      successCount += 1;
    } catch (error) {
      failures.push(`第 ${item.rowNumber} 行：${error.message || error}`);
    }
  }
  toast(failures.length ? `导入 ${successCount} 行，失败 ${failures.length} 行` : `已导入 ${successCount} 行任务`);
  if (failures.length) {
    console.warn("表格导入失败", failures);
  } else {
    resetTableImport();
  }
  await loadTasks();
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
  if (isChild) {
    return `
      <tr class="${selected} child-row${childClass}" data-task-id="${escapeHtml(task.task_id)}">
        <td>
          <div class="task-name">
            ${treeControl(task, 0)}
            <span>子任务 ${escapeHtml(task.child_index || "")}</span>
          </div>
        </td>
        <td class="task-id-cell">${renderTaskIdCell(task.task_id)}</td>
        <td class="child-result-cell" colspan="7">${renderChildResult(task)}</td>
        <td>${escapeHtml(passengerText)}</td>
        <td>${escapeHtml(task.run_count || "-")}</td>
        <td>${renderStatusBadge(task)}</td>
        <td>${passport}</td>
        <td>${renderTaskActions(task)}</td>
      </tr>`;
  }
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

function renderChildResult(task) {
  const summary = childResultSummary(task);
  return `
    <div class="child-result-summary" title="${escapeAttr(summary)}">
      <span class="child-result-label">最后结果</span>
      <span class="child-result-text">${escapeHtml(summary)}</span>
    </div>`;
}

function childResultSummary(task) {
  const result = task.last_result || {};
  const data = objectValue(result.data) || objectValue(result.result) || {};
  const pnr = firstText(data.pnr, result.pnr);
  const orderState = firstText(data.orderState, data.order_state, result.orderState, result.order_state, data.status, result.status);
  const cabin = firstText(data.cabin, result.cabin);
  const message = firstText(task.last_message, result.message, data.message, result.error, data.error, result.msg, data.msg);
  const parts = [];
  if (pnr) parts.push(`PNR ${pnr}`);
  if (orderState) parts.push(`状态 ${orderState}`);
  if (cabin) parts.push(`舱位 ${cabin}`);
  if (message && !parts.some((part) => part.includes(message))) parts.push(message);
  if (!parts.length && task.last_status_code) parts.push(`HTTP ${task.last_status_code}`);
  if (!parts.length) {
    const compact = compactResultText(result);
    if (compact) parts.push(compact);
  }
  return parts.join(" · ") || "暂无运行结果";
}

function objectValue(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : null;
}

function firstText(...values) {
  for (const value of values) {
    if (value && typeof value === "object") continue;
    const text = String(value ?? "").trim();
    if (text) return text;
  }
  return "";
}

function compactResultText(value) {
  if (!value || typeof value !== "object" || !Object.keys(value).length) return "";
  return JSON.stringify(value).replace(/\s+/g, " ").slice(0, 160);
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

async function loadPnrs(announce = false, options = {}) {
  if (state.pnrLoading) {
    state.pnrReloadQueued = true;
    state.pnrQueuedReset = state.pnrQueuedReset || Boolean(options.reset);
    if (options.page) state.pnrQueuedPage = Number(options.page);
    return;
  }
  const page = Math.max(1, Number(options.reset ? 1 : options.page || state.pnrPage || 1));
  const offset = (page - 1) * PNR_PAGE_SIZE;
  const params = buildPnrQueryParams(offset, PNR_PAGE_SIZE);
  state.pnrLoading = true;
  state.pnrPage = page;
  renderPnrPagination();
  try {
    const data = await api(`/api/pnrs?${params.toString()}`);
    const rows = data.rows || [];
    state.pnrs = rows;
    state.pnrTotal = Number(data.total || 0);
    state.pnrHasMore = Boolean(data.hasMore);
    renderPnrs();
    if (announce) toast("PNR 已刷新");
  } finally {
    state.pnrLoading = false;
    renderPnrPagination();
    if (state.pnrReloadQueued) {
      const reset = state.pnrQueuedReset;
      const queuedPage = state.pnrQueuedPage;
      state.pnrReloadQueued = false;
      state.pnrQueuedReset = false;
      state.pnrQueuedPage = null;
      loadPnrs(false, { reset, page: reset ? 1 : queuedPage || state.pnrPage }).catch(showError);
    }
  }
}

function buildPnrQueryParams(offset = 0, limit = PNR_PAGE_SIZE) {
  const params = new URLSearchParams();
  Object.entries(currentPnrFilters()).forEach(([key, rawValue]) => {
    const filterValue = String(rawValue || "").trim();
    if (filterValue) params.set(key, filterValue);
  });
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  return params;
}

function schedulePnrReload() {
  if (state.activeView !== "pnr") return;
  window.clearTimeout(state.pnrFilterTimer);
  state.pnrFilterTimer = window.setTimeout(() => {
    loadPnrs(false, { reset: true }).catch(showError);
  }, 180);
}

function renderPnrs() {
  renderPnrFilterOptions();
  const rows = state.pnrs;
  const total = state.pnrTotal || rows.length;
  const pageCount = pnrPageCount();
  const start = total && rows.length ? (state.pnrPage - 1) * PNR_PAGE_SIZE + 1 : 0;
  const end = total && rows.length ? start + rows.length - 1 : 0;
  els.pnrCount.textContent = total ? `${start}-${end} / ${total} 条` : "0 条";
  if (!rows.length) {
    const emptyText = hasActivePnrFilters() ? "没有符合筛选条件的 PNR。" : "暂无成功 PNR 记录。";
    els.pnrRows.innerHTML = `<tr><td colspan="14" class="empty-row">${emptyText}</td></tr>`;
    renderPnrPagination();
    return;
  }
  els.pnrRows.innerHTML = rows
    .map(
      (row) => `
        <tr data-task-id="${escapeHtml(row.taskId)}">
          <td title="${escapeAttr(row.taskId)}">${renderTaskIdCell(row.taskId)}</td>
          <td title="${escapeHtml(row.pnr)}">${escapeHtml(row.pnr)}</td>
          <td>${escapeHtml(row.source)}</td>
          <td>${escapeHtml(row.flightNumber)}</td>
          <td>${escapeHtml(row.cabin)}</td>
          <td>${escapeHtml(row.depAirport)}</td>
          <td>${escapeHtml(row.arrAirport)}</td>
          <td>${escapeHtml(formatDepDate(row.depDate))}</td>
          <td>${escapeHtml(row.passengerCount)}</td>
          <td title="${escapeAttr(row.passengers)}">${escapeHtml(row.passengers)}</td>
          <td>${escapeHtml(row.orderState)}</td>
          <td>${row.createdAt ? escapeHtml(formatTime(row.createdAt)) : "-"}</td>
          <td>${row.expiresAt ? escapeHtml(formatTime(row.expiresAt)) : "-"}</td>
          <td>${renderPnrExpiredBadge(row.expiresAt)}</td>
        </tr>`,
    )
    .join("");
  renderPnrPagination();
}

function renderPnrPagination() {
  if (!els.pnrPageInfo) return;
  const total = state.pnrTotal || 0;
  const pageCount = pnrPageCount();
  const page = total ? Math.min(state.pnrPage, pageCount) : 0;
  const start = total && state.pnrs.length ? (state.pnrPage - 1) * PNR_PAGE_SIZE + 1 : 0;
  const end = total && state.pnrs.length ? start + state.pnrs.length - 1 : 0;
  els.pnrPageInfo.textContent = total
    ? `第 ${page} / ${pageCount} 页 · ${start}-${end} / ${total} 条 · 每页 ${PNR_PAGE_SIZE} 条`
    : state.pnrLoading ? "加载中..." : "0 条";
  els.pnrPrevPageBtn.disabled = state.pnrLoading || page <= 1;
  els.pnrNextPageBtn.disabled = state.pnrLoading || !total || page >= pageCount;
}

function pnrPageCount() {
  return Math.max(1, Math.ceil((state.pnrTotal || 0) / PNR_PAGE_SIZE));
}

function filteredPnrRows() {
  const filters = currentPnrFilters();
  return state.pnrs.filter((row) => {
    if (filters.taskId && !includesText(row.taskId, filters.taskId)) return false;
    if (filters.pnr && !includesText(row.pnr, filters.pnr)) return false;
    if (filters.source && row.source !== filters.source) return false;
    if (filters.flightNumber && !includesText(row.flightNumber, filters.flightNumber)) return false;
    if (filters.cabin && !includesText(row.cabin, filters.cabin)) return false;
    if (filters.depAirport && !includesText(row.depAirport, filters.depAirport)) return false;
    if (filters.arrAirport && !includesText(row.arrAirport, filters.arrAirport)) return false;
    if (filters.depDate && !includesText(`${row.depDate} ${formatDepDate(row.depDate)}`, filters.depDate)) return false;
    if (filters.passengerCount && !includesText(row.passengerCount, filters.passengerCount)) return false;
    if (filters.passengers && !includesText(row.passengers, filters.passengers)) return false;
    if (filters.expired && pnrExpiryState(row.expiresAt) !== filters.expired) return false;
    return true;
  });
}

function currentPnrFilters() {
  return {
    taskId: value("pnrTaskIdFilter"),
    pnr: value("pnrPnrFilter"),
    source: value("pnrSourceFilter"),
    flightNumber: value("pnrFlightFilter"),
    cabin: value("pnrCabinFilter"),
    depAirport: value("pnrDepFilter"),
    arrAirport: value("pnrArrFilter"),
    depDate: value("pnrDateFilter"),
    passengerCount: value("pnrPeopleFilter"),
    passengers: value("pnrPassengerFilter"),
    expired: value("pnrExpiredFilter"),
  };
}

function includesText(value, query) {
  return String(value ?? "").toLowerCase().includes(String(query ?? "").toLowerCase());
}

function hasActivePnrFilters() {
  const filters = currentPnrFilters();
  return Object.values(filters).some(Boolean);
}

function renderPnrFilterOptions() {
  setSelectOptions(els.pnrSourceFilter, "全部", uniqueValues([...state.sources, ...state.pnrs.map((row) => row.source)]));
}

function setSelectOptions(select, emptyLabel, options) {
  if (!select) return;
  const current = select.value;
  const values = current && !options.includes(current) ? [current, ...options] : options;
  select.innerHTML = [`<option value="">${emptyLabel}</option>`, ...values.map((item) => `<option value="${escapeAttr(item)}">${escapeHtml(item)}</option>`)].join("");
  select.value = values.includes(current) ? current : "";
}

function uniqueValues(values) {
  return Array.from(new Set(values.map((item) => String(item || "").trim()).filter(Boolean))).sort();
}

function renderPnrExpiredBadge(expiresAt) {
  const expiryState = pnrExpiryState(expiresAt);
  if (expiryState === "unknown") return `<span class="expiry-badge unknown">-</span>`;
  const expired = expiryState === "expired";
  return `<span class="expiry-badge ${expired ? "expired" : "valid"}">${expired ? "是" : "否"}</span>`;
}

function pnrExpiryState(expiresAt) {
  if (!expiresAt) return "unknown";
  return Date.now() / 1000 >= Number(expiresAt) ? "expired" : "valid";
}

function openPnrDatePicker() {
  if (!els.pnrDatePickerPanel) return;
  state.pnrDatePickerMonth = monthStartFor(parseLocalDate(value("pnrDateFilter")) || firstPnrDate() || new Date());
  renderPnrDatePicker();
  els.pnrDatePickerPanel.classList.remove("hidden");
  els.pnrDatePickerPanel.closest(".date-filter-control")?.classList.add("active");
}

function closePnrDatePicker() {
  if (!els.pnrDatePickerPanel) return;
  els.pnrDatePickerPanel.classList.add("hidden");
  els.pnrDatePickerPanel.closest(".date-filter-control")?.classList.remove("active");
}

function renderPnrDatePicker() {
  if (!els.pnrDatePickerPanel) return;
  const month = state.pnrDatePickerMonth || monthStartFor(new Date());
  const selectedDate = parseLocalDate(value("pnrDateFilter"));
  const selectedValue = selectedDate ? formatLocalDate(selectedDate) : "";
  const todayValue = formatLocalDate(new Date());
  const firstDay = new Date(month.getFullYear(), month.getMonth(), 1);
  const gridStart = new Date(month.getFullYear(), month.getMonth(), 1 - firstDay.getDay());
  const weekDays = ["日", "一", "二", "三", "四", "五", "六"];
  const days = Array.from({ length: 42 }, (_, index) => {
    const date = new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + index);
    const dateValue = formatLocalDate(date);
    const classes = [
      "date-picker-day",
      date.getMonth() === month.getMonth() ? "" : "outside",
      dateValue === todayValue ? "today" : "",
      dateValue === selectedValue ? "selected" : "",
    ]
      .filter(Boolean)
      .join(" ");
    return `<button class="${classes}" data-date-value="${dateValue}" type="button">${date.getDate()}</button>`;
  }).join("");

  els.pnrDatePickerPanel.innerHTML = `
    <div class="date-picker-head">
      <button class="date-picker-nav" data-date-picker-action="prev" type="button" aria-label="上个月">${renderIcon("chevron-left")}</button>
      <strong>${month.getFullYear()}年${month.getMonth() + 1}月</strong>
      <button class="date-picker-nav" data-date-picker-action="next" type="button" aria-label="下个月">${renderIcon("chevron-right")}</button>
    </div>
    <div class="date-picker-weekdays">
      ${weekDays.map((day) => `<span>${day}</span>`).join("")}
    </div>
    <div class="date-picker-days">
      ${days}
    </div>
    <div class="date-picker-foot">
      <button class="date-picker-foot-button" data-date-picker-action="clear" type="button">清空</button>
      <button class="date-picker-foot-button primary" data-date-picker-action="today" type="button">今天</button>
    </div>`;
}

function handlePnrDatePickerClick(event) {
  const dateButton = event.target.closest("button[data-date-value]");
  if (dateButton) {
    els.pnrDateFilter.value = dateButton.dataset.dateValue;
    closePnrDatePicker();
    loadPnrs(false, { reset: true }).catch(showError);
    return;
  }
  const actionButton = event.target.closest("button[data-date-picker-action]");
  if (!actionButton) return;
  const action = actionButton.dataset.datePickerAction;
  if (action === "prev" || action === "next") {
    shiftPnrDatePickerMonth(action === "prev" ? -1 : 1);
    return;
  }
  if (action === "clear") {
    els.pnrDateFilter.value = "";
    closePnrDatePicker();
    loadPnrs(false, { reset: true }).catch(showError);
    return;
  }
  if (action === "today") {
    els.pnrDateFilter.value = formatLocalDate(new Date());
    closePnrDatePicker();
    loadPnrs(false, { reset: true }).catch(showError);
  }
}

function shiftPnrDatePickerMonth(delta) {
  const month = state.pnrDatePickerMonth || monthStartFor(new Date());
  state.pnrDatePickerMonth = new Date(month.getFullYear(), month.getMonth() + delta, 1);
  renderPnrDatePicker();
}

function firstPnrDate() {
  const first = state.pnrs.find((row) => parseLocalDate(formatDepDate(row.depDate)));
  return first ? parseLocalDate(formatDepDate(first.depDate)) : null;
}

function monthStartFor(date) {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function parseLocalDate(raw) {
  const value = String(raw || "").trim();
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(year, month - 1, day);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) return null;
  return date;
}

function formatLocalDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function clearSelectedTask() {
  state.selectedTaskId = "";
  els.tasksWorkspace.classList.remove("log-open");
  els.logSection.classList.add("hidden");
  els.selectedTask.textContent = "未选择";
  els.detailEmpty.classList.remove("hidden");
  els.detailContent.classList.add("hidden");
  els.lastResult.innerHTML = "";
  els.attemptRows.innerHTML = "";
  if (state.tasks.length) renderTasks();
}

async function selectTask(taskId, announce = true) {
  const task = await api(`/api/tasks/${encodeURIComponent(taskId)}`);
  state.selectedTaskId = taskId;
  els.tasksWorkspace.classList.add("log-open");
  els.logSection.classList.remove("hidden");
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
    els.attemptRows.innerHTML = `<div class="attempt-empty">暂无子任务</div>`;
    return;
  }
  els.attemptRows.innerHTML = children
    .map((child) => {
      const passengerCount = child.passenger_count || child.task_data?.ext?.passengerCount || "-";
      const updatedAt = child.updated_at ? formatTime(child.updated_at) : "-";
      return `
        <div data-task-id="${escapeHtml(child.task_id)}" class="attempt-item child-summary-row">
          <div class="attempt-item-head">
            <span class="attempt-index">#${escapeHtml(child.child_index || "-")}</span>
            ${renderStatusBadge(child)}
          </div>
          <div class="attempt-message" title="${escapeAttr(child.task_id)}">${escapeHtml(abbreviateTaskId(child.task_id))}</div>
          <div class="attempt-meta">
            <span>人数 ${escapeHtml(passengerCount)}</span>
            <span>执行 ${escapeHtml(child.run_count || 0)}</span>
            <span>${escapeHtml(updatedAt)}</span>
          </div>
        </div>`;
    })
    .join("");
}

function renderAttempts(attempts) {
  if (!attempts.length) {
    els.attemptRows.innerHTML = `<div class="attempt-empty">暂无执行记录</div>`;
    return;
  }
  els.attemptRows.innerHTML = attempts
    .map((attempt) => {
      const prefix = `[${formatLogTime(attempt.finished_at || attempt.started_at)}]`;
      const severity = attemptSeverity(attempt);
      const duration = attempt.duration_seconds ? `${attempt.duration_seconds.toFixed(2)}s` : "-";
      const finishedAt = attempt.finished_at ? formatTime(attempt.finished_at) : "-";
      return `
        <div class="attempt-item ${severity}">
          <div class="attempt-item-head">
            <span class="attempt-index">#${escapeHtml(attempt.attempt_no)}</span>
            <span class="attempt-state">${escapeHtml(attempt.status)}</span>
          </div>
          <div class="attempt-message log-message ${severity}">${escapeHtml(`${prefix} ${attempt.message || "-"}`)}</div>
          <div class="attempt-meta">
            <span>耗时 ${escapeHtml(duration)}</span>
            <span>${escapeHtml(finishedAt)}</span>
          </div>
        </div>`;
    })
    .join("");
}

async function handleTaskAction(action, taskId) {
  if (action === "copy") {
    const task = state.tasks.find((item) => item.task_id === taskId);
    if (task) copyTaskToForm(task);
    return;
  }
  if (action === "delete") {
    const confirmed = await showConfirmDialog({
      title: "删除任务",
      message: `确认删除任务 ${taskId}？删除后任务和相关执行记录将从本地列表移除。`,
      confirmText: "删除",
    });
    if (!confirmed) return;
  }
  const method = action === "delete" ? "DELETE" : "POST";
  const suffix = action === "delete" ? "" : `/${action}`;
  await api(`/api/tasks/${encodeURIComponent(taskId)}${suffix}`, { method });
  toast("操作已提交");
  await loadTasks();
}

function copyTaskToForm(task) {
  const data = task.task_data || {};
  const booking = data.bookingConfig || {};
  $("taskId").value = "";
  $("maxRuns").value = task.max_runs || "";
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
  $("currencyCode").value = booking.currencyCode || "MYR";
  $("callUrl").value = data.callbackData?.callUrl || "";
  $("callData").value = data.callbackData?.callData || "";
  $("usePassport").checked = inferPassport(data);
  toast("已复制到上方表单");
}

async function submitTask(event) {
  event.preventDefault();
  const payload = buildPayloadFromForm();
  await api("/api/tasks", { method: "POST", body: JSON.stringify(payload) });
  toast("任务已添加");
  resetFormDefaults();
  await loadTasks();
}

function resetFormDefaults() {
  $("taskForm").reset();
  if (state.sources.includes("5JWEB")) $("source").value = "5JWEB";
  $("currencyCode").value = "MYR";
  $("usePassport").checked = true;
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
    "chevron-left": '<path d="m15 18-6-6 6-6"></path>',
    "chevron-right": '<path d="m9 18 6-6-6-6"></path>',
  };
  return `<svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true">${icons[name] || ""}</svg>`;
}

function toast(message) {
  els.toast.textContent = message;
  els.toast.classList.remove("hidden");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => els.toast.classList.add("hidden"), 2400);
}

function showConfirmDialog({ title, message, confirmText = "确认", cancelText = "取消" }) {
  if (!els.confirmOverlay) return Promise.resolve(false);
  if (state.confirmResolver) closeConfirmDialog(false);
  els.confirmTitle.textContent = title || "确认操作";
  els.confirmMessage.textContent = message || "请确认是否继续。";
  els.confirmOkBtn.textContent = confirmText;
  els.confirmCancelBtn.textContent = cancelText;
  els.confirmOverlay.classList.remove("hidden");
  state.confirmPreviousFocus = document.activeElement;
  requestAnimationFrame(() => els.confirmCancelBtn.focus());
  return new Promise((resolve) => {
    state.confirmResolver = resolve;
  });
}

function closeConfirmDialog(result) {
  if (!state.confirmResolver) return;
  const resolver = state.confirmResolver;
  const previousFocus = state.confirmPreviousFocus;
  state.confirmResolver = null;
  state.confirmPreviousFocus = null;
  els.confirmOverlay.classList.add("hidden");
  resolver(result);
  if (previousFocus && typeof previousFocus.focus === "function") previousFocus.focus();
}

function bindEvents() {
  els.tabs.forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.view));
  });
  els.refreshBtn.addEventListener("click", () => refreshAll().catch(showError));
  els.proxyRefreshBtn.addEventListener("click", () => loadProxyConfigs().catch(showError));
  els.pnrRefreshBtn.addEventListener("click", () => loadPnrs(true, { page: state.pnrPage }).catch(showError));
  els.pnrPrevPageBtn.addEventListener("click", () => loadPnrs(false, { page: Math.max(1, state.pnrPage - 1) }).catch(showError));
  els.pnrNextPageBtn.addEventListener("click", () => loadPnrs(false, { page: state.pnrPage + 1 }).catch(showError));
  els.confirmCancelBtn.addEventListener("click", () => closeConfirmDialog(false));
  els.confirmOkBtn.addEventListener("click", () => closeConfirmDialog(true));
  els.confirmOverlay.addEventListener("click", (event) => {
    if (event.target === els.confirmOverlay) closeConfirmDialog(false);
  });
  [
    els.pnrTaskIdFilter,
    els.pnrPnrFilter,
    els.pnrFlightFilter,
    els.pnrCabinFilter,
    els.pnrDepFilter,
    els.pnrArrFilter,
    els.pnrDateFilter,
    els.pnrPeopleFilter,
    els.pnrPassengerFilter,
  ].forEach((input) => {
    if (input) {
      input.addEventListener("input", () => {
        if (input === els.pnrDateFilter && !els.pnrDatePickerPanel.classList.contains("hidden")) renderPnrDatePicker();
        schedulePnrReload();
      });
    }
  });
  els.pnrDateFilter.addEventListener("focus", openPnrDatePicker);
  els.pnrDatePickerPanel.addEventListener("click", (event) => {
    event.stopPropagation();
    handlePnrDatePickerClick(event);
  });
  [els.pnrSourceFilter, els.pnrExpiredFilter].forEach((select) => {
    if (select) select.addEventListener("change", () => loadPnrs(false, { reset: true }).catch(showError));
  });
  els.pnrResetFiltersBtn.addEventListener("click", () => {
    [
      "pnrTaskIdFilter",
      "pnrPnrFilter",
      "pnrSourceFilter",
      "pnrFlightFilter",
      "pnrCabinFilter",
      "pnrDepFilter",
      "pnrArrFilter",
      "pnrDateFilter",
      "pnrPeopleFilter",
      "pnrPassengerFilter",
      "pnrExpiredFilter",
    ].forEach((id) => {
      const element = $(id);
      if (element) element.value = "";
    });
    closePnrDatePicker();
    loadPnrs(false, { reset: true }).catch(showError);
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".date-filter-control")) closePnrDatePicker();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    closePnrDatePicker();
    closeConfirmDialog(false);
    if (!els.logSection.classList.contains("hidden")) clearSelectedTask();
  });
  els.taskForm.addEventListener("submit", (event) => submitTask(event).catch(showError));
  els.tableImportTemplateBtn.addEventListener("click", () => downloadTableImportTemplate().catch(showError));
  els.tableImportParseBtn.addEventListener("click", () => parseTableImport(true).catch(showError));
  els.tableImportSubmitBtn.addEventListener("click", () => submitTableImport().catch(showError));
  els.tableImportClearBtn.addEventListener("click", resetTableImport);
  els.tableImportFile.addEventListener("change", () => {
    const file = els.tableImportFile.files?.[0];
    if (!file) {
      resetTableImport();
      return;
    }
    els.tableImportPanel.classList.remove("hidden");
    els.tableImportFileName.textContent = file.name;
    state.tableImportItems = [];
    renderTableImportPreview();
    parseTableImport(false).catch(showError);
  });
  els.clearLogBtn.addEventListener("click", () => {
    clearSelectedTask();
  });
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
    const row = event.target.closest("[data-task-id]");
    if (row) selectTask(row.dataset.taskId).catch(showError);
  });
  els.pnrRows.addEventListener("click", (event) => {
    const copyButton = event.target.closest("button[data-copy-task-id]");
    if (copyButton) {
      copyText(copyButton.dataset.copyTaskId, "任务 ID").catch(showError);
    }
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
  if (state.activeView === "pnr") {
    renderPnrPagination();
  } else {
    await loadTasks();
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
