const DTYPE_OPTIONS = ["numeric", "categorical", "datetime", "boolean"];
const DTYPE_LABEL = { numeric: "수치", categorical: "범주", datetime: "날짜", boolean: "불리언" };

const CHART_TYPE_LABEL = { histogram: "히스토그램", bar: "막대", line: "꺾은선", scatter: "산점도", heatmap: "상관 히트맵" };
const DTYPE_ALLOWED_FOR_AXIS = {
  histogram: { x: ["numeric"], y: null },
  bar: { x: ["categorical", "boolean"], y: null },
  line: { x: ["datetime"], y: ["numeric"] },
  scatter: { x: ["numeric"], y: ["numeric"] },
  heatmap: { x: null, y: null },
};
const AGG_LABEL = { sum: "합계", mean: "평균", count: "개수", min: "최소", max: "최대" };
const CATEGORY_DTYPES = ["categorical", "boolean"];
const KIND_LABEL = { chart: "차트", aggregate: "그룹집계", pivot: "피벗" };

let state = { datasetId: null, dataset: null };

const el = (id) => document.getElementById(id);

function showError(message) {
  const banner = el("error-banner");
  banner.textContent = message;
  banner.classList.remove("hidden");
}

function clearError() {
  el("error-banner").classList.add("hidden");
}

async function requestJSON(url, options) {
  const res = await fetch(url, options);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body.detail || `요청이 실패했습니다 (HTTP ${res.status})`);
  }
  return body;
}

el("upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  clearError();
  const fileInput = el("file-input");
  if (!fileInput.files.length) return;

  const button = el("upload-button");
  button.disabled = true;
  el("upload-status").textContent = "업로드 중...";

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  formData.append("tags", el("tags-input").value);

  try {
    const dataset = await requestJSON("/api/upload", { method: "POST", body: formData });
    el("upload-status").textContent = `업로드 완료: ${dataset.filename}`;
    loadDatasetIntoView(dataset);
    await loadDatasetList();
  } catch (err) {
    el("upload-status").textContent = "";
    el("dashboard").classList.add("hidden");
    showError(err.message);
  } finally {
    button.disabled = false;
  }
});

async function loadDatasetIntoView(dataset) {
  state.datasetId = dataset.id;
  state.dataset = dataset;
  el("dashboard").classList.remove("hidden");
  renderSummary(dataset);
  renderTypesTable(dataset);
  renderPreviewTable(dataset);
  resetChartGrid();
  refreshChartBuilderOptions();
  refreshAggregateBuilderOptions();
  refreshPivotBuilderOptions();
  el("aggregate-result").innerHTML = "";
  el("pivot-result").innerHTML = "";
  el("saved-analysis-view").innerHTML = "";
  viewingAnalysisId = null;
  await Promise.all([loadStats(), loadRecommendations(), loadSavedAnalyses()]);
}

function renderSummary(dataset) {
  el("summary-content").innerHTML = `
    <div class="summary-grid">
      <div class="summary-item"><div class="label">파일명</div><div class="value">${escapeHtml(dataset.filename)}</div></div>
      <div class="summary-item"><div class="label">행 수</div><div class="value">${dataset.row_count.toLocaleString()}</div></div>
      <div class="summary-item"><div class="label">열 수</div><div class="value">${dataset.col_count.toLocaleString()}</div></div>
    </div>
  `;
}

function renderTypesTable(dataset) {
  const tbody = document.querySelector("#types-table tbody");
  tbody.innerHTML = "";
  for (const col of dataset.columns) {
    const tr = document.createElement("tr");

    const nameTd = document.createElement("td");
    nameTd.textContent = col.name;

    const typeTd = document.createElement("td");
    const select = document.createElement("select");
    for (const opt of DTYPE_OPTIONS) {
      const optionEl = document.createElement("option");
      optionEl.value = opt;
      optionEl.textContent = DTYPE_LABEL[opt];
      if (opt === col.dtype) optionEl.selected = true;
      select.appendChild(optionEl);
    }
    select.addEventListener("change", () => correctColumnType(col.name, select.value));
    typeTd.appendChild(select);

    const missingTd = document.createElement("td");
    missingTd.textContent = `${(col.missing_rate * 100).toFixed(1)}%`;

    tr.append(nameTd, typeTd, missingTd);
    tbody.appendChild(tr);
  }
}

async function correctColumnType(column, dtype) {
  clearError();
  try {
    const dataset = await requestJSON(`/api/datasets/${state.datasetId}/column-type`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ column, dtype }),
    });
    state.dataset = dataset;
    renderTypesTable(dataset);
    refreshChartBuilderOptions();
    refreshAggregateBuilderOptions();
    refreshPivotBuilderOptions();
    await Promise.all([loadStats(), loadRecommendations()]);
  } catch (err) {
    showError(err.message);
  }
}

async function loadStats() {
  try {
    const stats = await requestJSON(`/api/datasets/${state.datasetId}/stats`);
    renderStats(stats);
  } catch (err) {
    showError(err.message);
  }
}

function renderStats(stats) {
  const container = el("stats-content");
  container.innerHTML = `<p class="summary-item"><span class="label">전체 결측률</span> <span class="value">${(stats.total_missing_rate * 100).toFixed(1)}%</span></p>`;

  for (const [name, s] of Object.entries(stats.columns)) {
    const block = document.createElement("div");
    block.className = "stats-block";
    const title = document.createElement("h3");
    title.textContent = name;
    block.appendChild(title);

    const table = document.createElement("table");
    if (s.type === "numeric") {
      table.innerHTML = `
        <thead><tr><th>개수</th><th>결측</th><th>평균</th><th>중앙값</th><th>최소</th><th>최대</th><th>표준편차</th><th>Q1</th><th>Q3</th></tr></thead>
        <tbody><tr>
          <td>${s.count}</td><td>${s.missing_count}</td><td>${fmt(s.mean)}</td><td>${fmt(s.median)}</td>
          <td>${fmt(s.min)}</td><td>${fmt(s.max)}</td><td>${fmt(s.std)}</td><td>${fmt(s.q1)}</td><td>${fmt(s.q3)}</td>
        </tr></tbody>`;
    } else if (s.type === "datetime") {
      table.innerHTML = `
        <thead><tr><th>개수</th><th>결측</th><th>최소</th><th>최대</th></tr></thead>
        <tbody><tr><td>${s.count}</td><td>${s.missing_count}</td><td>${s.min ?? "-"}</td><td>${s.max ?? "-"}</td></tr></tbody>`;
    } else {
      const top = s.top_frequencies.map((f) => `${escapeHtml(f.value)} (${f.count})`).join(", ");
      table.innerHTML = `
        <thead><tr><th>개수</th><th>결측</th><th>고유값 수</th><th>최빈값</th><th>상위 빈도</th></tr></thead>
        <tbody><tr><td>${s.count}</td><td>${s.missing_count}</td><td>${s.unique_count}</td><td>${escapeHtml(s.mode ?? "-")}</td><td>${top}</td></tr></tbody>`;
    }
    const scrollWrap = document.createElement("div");
    scrollWrap.className = "table-scroll";
    scrollWrap.appendChild(table);
    block.appendChild(scrollWrap);
    container.appendChild(block);
  }
}

function renderPreviewTable(dataset) {
  const thead = document.querySelector("#preview-table thead");
  const tbody = document.querySelector("#preview-table tbody");
  thead.innerHTML = "";
  tbody.innerHTML = "";

  const columns = dataset.columns.map((c) => c.name);
  const headRow = document.createElement("tr");
  for (const col of columns) {
    const th = document.createElement("th");
    th.textContent = col;
    headRow.appendChild(th);
  }
  thead.appendChild(headRow);

  for (const row of dataset.preview) {
    const tr = document.createElement("tr");
    for (const col of columns) {
      const td = document.createElement("td");
      const value = row[col];
      td.textContent = value === null || value === undefined ? "" : value;
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
}

// --- 저장된 데이터셋 목록 · 태그 · 재호출 ---

async function loadDatasetList(tag) {
  try {
    const query = tag ? `?tag=${encodeURIComponent(tag)}` : "";
    const list = await requestJSON(`/api/datasets${query}`);
    renderDatasetList(list);
  } catch (err) {
    showError(err.message);
  }
}

function renderDatasetList(list) {
  const tbody = document.querySelector("#dataset-list-table tbody");
  tbody.innerHTML = "";

  if (list.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 5;
    td.textContent = "저장된 데이터셋이 없습니다.";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  for (const item of list) {
    const tr = document.createElement("tr");

    const nameTd = document.createElement("td");
    nameTd.textContent = item.filename;

    const tagsTd = document.createElement("td");
    const tagsInput = document.createElement("input");
    tagsInput.type = "text";
    tagsInput.value = item.tags.join(", ");
    tagsInput.placeholder = "태그(콤마로 구분)";
    const tagsSaveButton = document.createElement("button");
    tagsSaveButton.type = "button";
    tagsSaveButton.textContent = "태그 저장";
    tagsSaveButton.addEventListener("click", () => saveDatasetTags(item.id, tagsInput.value));
    tagsTd.append(tagsInput, tagsSaveButton);

    const uploadedTd = document.createElement("td");
    uploadedTd.textContent = new Date(item.uploaded_at).toLocaleString();

    const sizeTd = document.createElement("td");
    sizeTd.textContent = `${item.row_count.toLocaleString()} / ${item.col_count.toLocaleString()}`;

    const openTd = document.createElement("td");
    const openButton = document.createElement("button");
    openButton.type = "button";
    openButton.textContent = "열기";
    openButton.addEventListener("click", () => openDataset(item.id));
    openTd.appendChild(openButton);

    const deleteTd = document.createElement("td");
    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.textContent = "삭제";
    deleteButton.addEventListener("click", () => deleteDataset(item.id));
    deleteTd.appendChild(deleteButton);

    tr.append(nameTd, tagsTd, uploadedTd, sizeTd, openTd, deleteTd);
    tbody.appendChild(tr);
  }
}

async function deleteDataset(datasetId) {
  if (!confirm("정말 삭제하시겠습니까? 되돌릴 수 없습니다.")) return;
  clearError();
  try {
    await requestJSON(`/api/datasets/${datasetId}`, { method: "DELETE" });
    if (state.datasetId === datasetId) {
      state.datasetId = null;
      state.dataset = null;
      el("dashboard").classList.add("hidden");
      el("upload-status").textContent = "";
    }
    await loadDatasetList(el("dataset-tag-filter").value.trim());
  } catch (err) {
    showError(err.message);
  }
}

async function openDataset(datasetId) {
  clearError();
  try {
    const dataset = await requestJSON(`/api/datasets/${datasetId}`);
    el("upload-status").textContent = `불러옴: ${dataset.filename}`;
    await loadDatasetIntoView(dataset);
  } catch (err) {
    showError(err.message);
  }
}

async function saveDatasetTags(datasetId, rawTags) {
  clearError();
  try {
    await requestJSON(`/api/datasets/${datasetId}/tags`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tags: rawTags.split(",") }),
    });
    await loadDatasetList(el("dataset-tag-filter").value.trim());
  } catch (err) {
    showError(err.message);
  }
}

el("dataset-filter-button").addEventListener("click", () => {
  loadDatasetList(el("dataset-tag-filter").value.trim());
});

el("dataset-filter-clear-button").addEventListener("click", () => {
  el("dataset-tag-filter").value = "";
  loadDatasetList();
});

// --- 인증 ---

async function checkAuth() {
  try {
    const user = await requestJSON("/api/auth/me");
    showLoggedIn(user);
  } catch (err) {
    showLoggedOut();
  }
}

function showLoggedIn(user) {
  el("auth-section").classList.add("hidden");
  el("app-content").classList.remove("hidden");
  el("user-info").classList.remove("hidden");
  el("user-info-name").textContent = `${user.username}님`;
  loadDatasetList();
}

function showLoggedOut() {
  el("auth-section").classList.remove("hidden");
  el("app-content").classList.add("hidden");
  el("user-info").classList.add("hidden");
}

function showAuthFormError(bannerId, message) {
  const banner = el(bannerId);
  banner.textContent = message;
  banner.classList.remove("hidden");
}

el("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  el("login-error").classList.add("hidden");
  try {
    const user = await requestJSON("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: el("login-username").value,
        password: el("login-password").value,
      }),
    });
    el("login-form").reset();
    showLoggedIn(user);
  } catch (err) {
    showAuthFormError("login-error", err.message);
  }
});

el("register-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  el("register-error").classList.add("hidden");
  try {
    const user = await requestJSON("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: el("register-username").value,
        password: el("register-password").value,
        invite_code: el("register-invite-code").value,
      }),
    });
    el("register-form").reset();
    showLoggedIn(user);
  } catch (err) {
    showAuthFormError("register-error", err.message);
  }
});

el("logout-button").addEventListener("click", async () => {
  try {
    await requestJSON("/api/auth/logout", { method: "POST" });
  } catch (err) {
    // 로그아웃 요청이 실패해도 화면은 로그인 화면으로 되돌린다.
  }
  showLoggedOut();
});

checkAuth();

function fmt(value) {
  return value === null || value === undefined ? "-" : value;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

// --- 차트 ---

async function loadRecommendations() {
  try {
    const recs = await requestJSON(`/api/datasets/${state.datasetId}/chart-recommendations`);
    renderRecommendations(recs);
  } catch (err) {
    showError(err.message);
  }
}

function renderRecommendations(recs) {
  const container = el("recommendation-list");
  container.innerHTML = "";
  if (recs.length === 0) {
    container.textContent = "추천할 차트가 없습니다.";
    return;
  }
  for (const rec of recs) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chip-button";
    button.textContent = rec.label;
    button.addEventListener("click", () => generateChart(rec.spec, rec.label));
    container.appendChild(button);
  }
}

function refreshChartBuilderOptions() {
  const chartType = el("chart-type-select").value;
  const rule = DTYPE_ALLOWED_FOR_AXIS[chartType];
  const columns = state.dataset ? state.dataset.columns : [];
  populateAxisSelect("chart-x-wrap", "chart-x-select", columns, rule.x);
  populateAxisSelect("chart-y-wrap", "chart-y-select", columns, rule.y);
}

function populateAxisSelect(wrapId, selectId, columns, allowedTypes) {
  const wrap = el(wrapId);
  const select = el(selectId);
  select.innerHTML = "";
  if (!allowedTypes) {
    wrap.classList.add("hidden");
    return;
  }
  wrap.classList.remove("hidden");
  for (const col of columns) {
    if (!allowedTypes.includes(col.dtype)) continue;
    const opt = document.createElement("option");
    opt.value = col.name;
    opt.textContent = col.name;
    select.appendChild(opt);
  }
}

el("chart-type-select").addEventListener("change", refreshChartBuilderOptions);

el("chart-build-button").addEventListener("click", () => {
  const chartType = el("chart-type-select").value;
  const rule = DTYPE_ALLOWED_FOR_AXIS[chartType];
  const spec = { chart_type: chartType };
  if (rule.x) spec.x = el("chart-x-select").value || null;
  if (rule.y) spec.y = el("chart-y-select").value || null;
  generateChart(spec, manualChartLabel(spec));
});

function manualChartLabel(spec) {
  const typeLabel = CHART_TYPE_LABEL[spec.chart_type];
  if (spec.chart_type === "heatmap") return typeLabel;
  return spec.y ? `${typeLabel} · ${spec.x} → ${spec.y}` : `${typeLabel} · ${spec.x}`;
}

async function generateChart(spec, label) {
  clearChartBuilderError();
  try {
    const res = await fetch(`/api/datasets/${state.datasetId}/chart`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(spec),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `차트를 생성하지 못했습니다 (HTTP ${res.status})`);
    }
    const blob = await res.blob();
    addChartCard(blob, spec, label);
  } catch (err) {
    showChartBuilderError(err.message);
  }
}

function addChartCard(blob, spec, label) {
  const url = URL.createObjectURL(blob);

  const card = document.createElement("div");
  card.className = "chart-card";

  const title = document.createElement("div");
  title.className = "chart-card-title";
  title.textContent = label;

  const img = document.createElement("img");
  img.src = url;
  img.alt = label;

  const downloadLink = document.createElement("a");
  downloadLink.href = url;
  downloadLink.download = filenameFor(spec);
  downloadLink.className = "download-button";
  downloadLink.textContent = "PNG 다운로드";

  const saveButton = createSaveAnalysisButton("chart", spec, label);

  card.append(title, img, downloadLink, saveButton);
  el("chart-grid").prepend(card);
}

function sanitizeFilenamePart(value) {
  return (value || "").replace(/[\\/:*?"<>|]/g, "_");
}

function filenameFor(spec) {
  if (spec.chart_type === "heatmap") return "heatmap_상관행렬.png";
  const parts = [spec.chart_type, sanitizeFilenamePart(spec.x)];
  if (spec.y) parts.push(sanitizeFilenamePart(spec.y));
  return `${parts.join("_")}.png`;
}

function resetChartGrid() {
  const grid = el("chart-grid");
  grid.querySelectorAll("img").forEach((img) => URL.revokeObjectURL(img.src));
  grid.innerHTML = "";
}

function showChartBuilderError(message) {
  const banner = el("chart-builder-error");
  banner.textContent = message;
  banner.classList.remove("hidden");
}

function clearChartBuilderError() {
  el("chart-builder-error").classList.add("hidden");
}

// --- 그룹 집계 ---

function refreshAggregateBuilderOptions() {
  const columns = state.dataset ? state.dataset.columns : [];
  const categoryCols = columns.filter((c) => CATEGORY_DTYPES.includes(c.dtype));
  const numericCols = columns.filter((c) => c.dtype === "numeric");

  fillSelectOptions("agg-group1-select", categoryCols);
  fillSelectOptions("agg-group2-select", categoryCols, { includeEmpty: true });
  fillSelectOptions("agg-value-select", numericCols);
}

function fillSelectOptions(selectId, columns, { includeEmpty = false } = {}) {
  const select = el(selectId);
  select.innerHTML = "";
  if (includeEmpty) {
    const emptyOpt = document.createElement("option");
    emptyOpt.value = "";
    emptyOpt.textContent = "없음";
    select.appendChild(emptyOpt);
  }
  for (const col of columns) {
    const opt = document.createElement("option");
    opt.value = col.name;
    opt.textContent = col.name;
    select.appendChild(opt);
  }
}

el("agg-build-button").addEventListener("click", runAggregate);

async function runAggregate() {
  clearAggregateError();
  const group1 = el("agg-group1-select").value;
  const group2 = el("agg-group2-select").value;
  const value = el("agg-value-select").value;
  const aggFunc = el("agg-func-select").value;
  const spec = { group_by: group2 ? [group1, group2] : [group1], value, agg_func: aggFunc };

  try {
    const result = await requestJSON(`/api/datasets/${state.datasetId}/aggregate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(spec),
    });
    renderAggregateResult(result, spec);
  } catch (err) {
    showAggregateError(err.message);
  }
}

function renderAggregateResult(result, spec) {
  const container = el("aggregate-result");
  container.innerHTML = "";

  if (result.truncated) {
    const notice = document.createElement("p");
    notice.className = "notice";
    notice.textContent = `그룹이 많아 값이 큰 상위 ${result.rows.length}개만 표시합니다 (전체 ${result.total_groups}개 그룹).`;
    container.appendChild(notice);
  }

  const table = document.createElement("table");
  const headRow = document.createElement("tr");
  for (const g of result.group_by) {
    const th = document.createElement("th");
    th.textContent = g;
    headRow.appendChild(th);
  }
  const valueTh = document.createElement("th");
  valueTh.textContent = `${result.value} (${AGG_LABEL[result.agg_func]})`;
  headRow.appendChild(valueTh);
  const thead = document.createElement("thead");
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const row of result.rows) {
    const tr = document.createElement("tr");
    for (const g of result.group_by) {
      const td = document.createElement("td");
      td.textContent = row[g];
      tr.appendChild(td);
    }
    const valueTd = document.createElement("td");
    valueTd.textContent = row[result.value];
    tr.appendChild(valueTd);
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);

  const scrollWrap = document.createElement("div");
  scrollWrap.className = "table-scroll";
  scrollWrap.appendChild(table);
  container.appendChild(scrollWrap);

  generateAggregateChart(spec, container);
}

async function generateAggregateChart(spec, container) {
  try {
    const res = await fetch(`/api/datasets/${state.datasetId}/aggregate/chart`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(spec),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `집계 차트를 생성하지 못했습니다 (HTTP ${res.status})`);
    }
    const blob = await res.blob();
    const filename = `bar_${spec.group_by.map(sanitizeFilenamePart).join("_")}_${sanitizeFilenamePart(spec.value)}.png`;
    appendChartImage(container, blob, filename, { kind: "aggregate", spec, label: aggregateLabel(spec) });
  } catch (err) {
    showAggregateError(err.message);
  }
}

function showAggregateError(message) {
  const banner = el("aggregate-error");
  banner.textContent = message;
  banner.classList.remove("hidden");
}

function clearAggregateError() {
  el("aggregate-error").classList.add("hidden");
}

// --- 피벗 ---

function refreshPivotBuilderOptions() {
  const columns = state.dataset ? state.dataset.columns : [];
  const categoryCols = columns.filter((c) => CATEGORY_DTYPES.includes(c.dtype));
  const numericCols = columns.filter((c) => c.dtype === "numeric");

  fillSelectOptions("pivot-rows-select", categoryCols);
  fillSelectOptions("pivot-columns-select", categoryCols);
  fillSelectOptions("pivot-value-select", numericCols);
}

el("pivot-build-button").addEventListener("click", runPivot);

async function runPivot() {
  clearPivotError();
  const spec = {
    rows: el("pivot-rows-select").value,
    columns: el("pivot-columns-select").value,
    value: el("pivot-value-select").value,
    agg_func: el("pivot-func-select").value,
  };

  try {
    const result = await requestJSON(`/api/datasets/${state.datasetId}/pivot`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(spec),
    });
    renderPivotResult(result, spec);
  } catch (err) {
    showPivotError(err.message);
  }
}

function renderPivotResult(result, spec) {
  const container = el("pivot-result");
  container.innerHTML = "";

  const table = document.createElement("table");
  const headRow = document.createElement("tr");
  const cornerTh = document.createElement("th");
  cornerTh.textContent = `${result.rows} \\ ${result.columns}`;
  headRow.appendChild(cornerTh);
  for (const label of result.column_labels) {
    const th = document.createElement("th");
    th.textContent = label;
    headRow.appendChild(th);
  }
  const thead = document.createElement("thead");
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  result.row_labels.forEach((rowLabel, i) => {
    const tr = document.createElement("tr");
    const rowTh = document.createElement("th");
    rowTh.textContent = rowLabel;
    tr.appendChild(rowTh);
    result.column_labels.forEach((_, j) => {
      const td = document.createElement("td");
      const value = result.cells[i][j];
      td.textContent = value === null || value === undefined ? "-" : value;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);

  const scrollWrap = document.createElement("div");
  scrollWrap.className = "table-scroll";
  scrollWrap.appendChild(table);
  container.appendChild(scrollWrap);

  generatePivotChart(spec, container);
}

async function generatePivotChart(spec, container) {
  try {
    const res = await fetch(`/api/datasets/${state.datasetId}/pivot/chart`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(spec),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `피벗 차트를 생성하지 못했습니다 (HTTP ${res.status})`);
    }
    const blob = await res.blob();
    const filename = `pivot_${sanitizeFilenamePart(spec.rows)}_${sanitizeFilenamePart(spec.columns)}_${sanitizeFilenamePart(spec.value)}.png`;
    appendChartImage(container, blob, filename, { kind: "pivot", spec, label: pivotLabel(spec) });
  } catch (err) {
    showPivotError(err.message);
  }
}

function appendChartImage(container, blob, filename, saveInfo) {
  const url = URL.createObjectURL(blob);
  const wrap = document.createElement("div");
  wrap.className = "chart-card";

  const img = document.createElement("img");
  img.src = url;

  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.className = "download-button";
  link.textContent = "PNG 다운로드";

  wrap.append(img, link);
  if (saveInfo) {
    wrap.appendChild(createSaveAnalysisButton(saveInfo.kind, saveInfo.spec, saveInfo.label));
  }
  container.appendChild(wrap);
}

function createSaveAnalysisButton(kind, spec, label) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "분석 저장";
  button.addEventListener("click", () => saveAnalysis(kind, spec, label, button));
  return button;
}

async function saveAnalysis(kind, spec, label, buttonEl) {
  clearError();
  buttonEl.disabled = true;
  buttonEl.textContent = "저장 중...";
  try {
    await requestJSON(`/api/datasets/${state.datasetId}/analyses`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, spec, title: label }),
    });
    buttonEl.textContent = "저장됨";
    await loadSavedAnalyses();
  } catch (err) {
    buttonEl.disabled = false;
    buttonEl.textContent = "분석 저장";
    showError(err.message);
  }
}

function aggregateLabel(spec) {
  return `그룹집계 · ${spec.group_by.join("+")} (${AGG_LABEL[spec.agg_func]} ${spec.value})`;
}

function pivotLabel(spec) {
  return `피벗 · ${spec.rows}×${spec.columns} (${AGG_LABEL[spec.agg_func]} ${spec.value})`;
}

async function loadSavedAnalyses() {
  try {
    const list = await requestJSON(`/api/datasets/${state.datasetId}/analyses`);
    renderSavedAnalysesList(list);
  } catch (err) {
    showError(err.message);
  }
}

function renderSavedAnalysesList(list) {
  const tbody = document.querySelector("#saved-analyses-table tbody");
  tbody.innerHTML = "";

  if (list.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 5;
    td.textContent = "저장된 분석이 없습니다.";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  for (const item of list) {
    const tr = document.createElement("tr");

    const titleTd = document.createElement("td");
    titleTd.textContent = item.title;

    const kindTd = document.createElement("td");
    kindTd.textContent = KIND_LABEL[item.kind] || item.kind;

    const createdTd = document.createElement("td");
    createdTd.textContent = new Date(item.created_at).toLocaleString();

    const viewTd = document.createElement("td");
    const viewButton = document.createElement("button");
    viewButton.type = "button";
    viewButton.textContent = "보기";
    viewButton.addEventListener("click", () => viewSavedAnalysis(item.id, item.title));
    viewTd.appendChild(viewButton);

    const deleteTd = document.createElement("td");
    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.textContent = "삭제";
    deleteButton.addEventListener("click", () => deleteAnalysis(item.id));
    deleteTd.appendChild(deleteButton);

    tr.append(titleTd, kindTd, createdTd, viewTd, deleteTd);
    tbody.appendChild(tr);
  }
}

let viewingAnalysisId = null;

async function deleteAnalysis(analysisId) {
  if (!confirm("정말 삭제하시겠습니까? 되돌릴 수 없습니다.")) return;
  clearError();
  try {
    await requestJSON(`/api/datasets/${state.datasetId}/analyses/${analysisId}`, { method: "DELETE" });
    if (viewingAnalysisId === analysisId) {
      el("saved-analysis-view").innerHTML = "";
      viewingAnalysisId = null;
    }
    await loadSavedAnalyses();
  } catch (err) {
    showError(err.message);
  }
}

async function viewSavedAnalysis(analysisId, title) {
  clearError();
  const view = el("saved-analysis-view");
  view.innerHTML = "";
  try {
    const res = await fetch(`/api/datasets/${state.datasetId}/analyses/${analysisId}/chart`);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `분석을 불러오지 못했습니다 (HTTP ${res.status})`);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    viewingAnalysisId = analysisId;

    const card = document.createElement("div");
    card.className = "chart-card";

    const titleEl = document.createElement("div");
    titleEl.className = "chart-card-title";
    titleEl.textContent = title;

    const img = document.createElement("img");
    img.src = url;
    img.alt = title;

    const downloadLink = document.createElement("a");
    downloadLink.href = url;
    downloadLink.download = `${sanitizeFilenamePart(title)}.png`;
    downloadLink.className = "download-button";
    downloadLink.textContent = "PNG 다운로드";

    card.append(titleEl, img, downloadLink);
    view.appendChild(card);
  } catch (err) {
    showError(err.message);
  }
}

function showPivotError(message) {
  const banner = el("pivot-error");
  banner.textContent = message;
  banner.classList.remove("hidden");
}

function clearPivotError() {
  el("pivot-error").classList.add("hidden");
}
