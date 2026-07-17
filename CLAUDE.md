# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository status

This repository currently contains only a PRD (`PRD_Excel2Dashboard_Basic_v0.1.md`) — no code has been written yet, and there is no git repo initialized. There are no build/lint/test commands to run yet. Once implementation starts (Python + FastAPI backend, vanilla HTML/JS frontend per the stack below), update this file with the actual commands (e.g. `uvicorn` run command, `pytest` invocation, dependency install).

## Product context

Excel2Dashboard is planned as a 3-part series: **Basic** (this repo) → **Pro** (adds persistence) → **Team** (adds multi-user collaboration). Each stage adds a layer without rewriting the previous one — this constrains how Basic must be built (see "Seams for future extension" below).

**Basic in one line:** upload an Excel/CSV file, get an auto-generated dashboard, download chosen analysis charts as PNG.

**Basic explicitly excludes:** saving, projects, re-opening past uploads, multiple users. Everything is session-only, in-memory — a refresh discards all data. Do not add localStorage, a database, or any persistence layer; that's Pro's job.

## Intended architecture

- **Backend:** Python + FastAPI + pandas. This is the analysis server responsible for parsing, type inference, stats, aggregation, and chart generation.
- **Chart rendering:** matplotlib generates PNGs **server-side**. The same image is used for on-screen display and for download — this is a deliberate simplicity choice since PNG is the only export format. Do not introduce client-side charting (e.g. Chart.js/D3) or SVG export.
- **Frontend:** lightweight HTML/JS, no framework or build tooling. Responsible only for file upload, rendering the dashboard, and per-chart PNG download buttons.
- **Storage:** none. Uploaded files live only in server-side session memory / temp paths and are discarded on session end or refresh.

### Seams required for future extension (Pro/Team)

These three rules exist so that Pro can be "add a storage layer" and Team can be "add accounts/sharing" without rewriting Basic. Any implementation work in this repo must preserve them:

1. **Logic/UI separation.** `parse`, `infer_types`, `stats`, `aggregate`, and `make_chart` must be pure input→output function modules, independent of FastAPI. Routers only call into these modules — no business logic in route handlers.
2. **JSON-serializable data contract.** The "dataset" and "analysis config" concepts must be expressed as JSON from the start, even though Basic only holds them in memory. This JSON shape is what Pro will persist to a DB and Team will share.
3. **IDs everywhere.** Datasets and analysis results get a `uuid` from the start. Avoid a single global-state blob holding everything.

## Feature scope (from PRD)

- **Upload/parse:** `.xlsx`, `.xls`, `.csv`. One file = one sheet/tab. Row 1 = single header, data from row 2. Auto-detect CSV encoding (UTF-8 / EUC-KR). Show a preview of the top N rows plus total row/column counts.
- **Column type inference:** classify each column as numeric / categorical / date / boolean, show missing-value rate, and allow manual correction via dropdown (inference will be wrong sometimes).
- **Descriptive stats:** numeric columns → count, missing count, mean, median, min/max, std dev, Q1/Q3. Categorical columns → unique count, mode, top category frequencies.
- **Visualization:** histogram (numeric distribution), bar (categorical frequency), line (date × numeric trend), scatter (numeric × numeric), correlation heatmap (all numeric columns). Chart type is auto-recommended based on column types, but users can manually pick axes/columns.
- **Group aggregation / pivot (extended scope):** group-by on categorical columns with agg functions (sum/mean/count/min/max) → table + bar chart. Simple pivot: row=category, column=category, value=numeric with an aggregation function.
- **PNG export:** each chart downloadable as PNG, filename reflecting chart type and column name (e.g. `histogram_매출액.png`).

## Non-functional constraints

- Enforce a file size/row-count cap and give a clear message when exceeded (specific limits not yet decided — see open decisions below).
- Never let messy data (blank rows, mixed types, dates stored as text) crash the server — warn instead of failing silently or dying.
- Parsing failures and bad input must surface a visible error to the user, never fail silently.
- Stack is fixed: Python + FastAPI + pandas + matplotlib. Frontend stays vanilla; no localStorage (out of scope for Basic).

## Out of scope for Basic

- Saving, project-level organization, re-opening past uploads, saved analysis results → deferred to **Pro**.
- Multi-user, accounts, login, sharing, permissions → deferred to **Team**.
- Multi-sheet files, SVG export, real-time collaboration, prediction/ML — not planned for any of the three stages described here.

## Implementation phases (per PRD §6)

- **Day 1 — skeleton/interpretation:** upload → parse → column type inference (+ manual correction) → table preview → descriptive stats. Do not build charts or aggregation yet.
- **Day 2 — visualization/export:** auto-recommended + manually-selected charts (histogram/bar/line/scatter/correlation heatmap) + PNG download. Do not build group aggregation/pivot yet.
- **Day 3 — aggregation/polish:** group aggregation + simple pivot + robustness (errors, large files, messy data) + README + self-evaluation.

## Completion criteria (check in this order)

1. Upload/parse: xlsx/xls/csv upload from the browser works; preview and row/column counts are accurate.
2. Types/stats: column types auto-inferred and manually correctable; descriptive stats match pandas' own computation.
3. Visualization: recommended and manual charts render correctly; each downloads as an accurate PNG.
4. Aggregation/pivot: group aggregation and pivot results are correct in both table and chart form.
5. Robustness: messy data, large files, and bad input don't crash the server and produce clear guidance.
6. Documentation: `README.md` (how to run, features, structure) and a self-evaluation report exist.

## Open decisions (not yet settled — ask before assuming)

- Concrete file size / row count upper limit.
- Number of rows (N) shown in the preview table.
- Dashboard layout order (summary cards → stats table → chart grid, etc.).
- Cap on number of numeric columns included in the correlation heatmap when there are many.
