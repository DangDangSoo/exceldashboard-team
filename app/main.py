"""
FastAPI 라우터. 이음새 원칙 #1: 여기는 core 모듈 호출만 하고,
파싱/타입판별/통계 로직 자체는 절대 여기 두지 않는다.
"""
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Form, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app import db, storage
from app.core.aggregate import group_aggregate, pivot_table
from app.core.charts import recommend_charts, render_aggregate_chart, render_chart, render_pivot_chart
from app.core.errors import AppError
from app.core.infer_types import infer_types, missing_rate_for
from app.core.parse import dataframe_preview, parse_file
from app.core.stats import compute_stats, overall_missing_rate
from app.models import (
    AggregateResult,
    AggregateSpec,
    ChartRecommendation,
    ChartSpec,
    Dataset,
    DatasetSummary,
    PivotResult,
    PivotSpec,
    SaveAnalysisRequest,
    SavedAnalysis,
    StatsResponse,
    TagsUpdateRequest,
    TypeCorrectionRequest,
)
from app.session_store import SessionEntry, session_store

PREVIEW_ROWS = 20
SPEC_MODEL_BY_KIND = {"chart": ChartSpec, "aggregate": AggregateSpec, "pivot": PivotSpec}

app = FastAPI(title="Excel2Dashboard (Basic) — v1.0")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    # 견고성: 예상 못한 서버 예외도 프로세스를 죽이지 않고 사용자에게 보이는 메시지로 응답한다.
    return JSONResponse(
        status_code=500,
        content={"detail": f"예상치 못한 서버 오류가 발생했습니다: {exc}"},
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


def _split_tags(raw: str | None) -> list[str]:
    return raw.split(",") if raw else []


@app.post("/api/upload", response_model=Dataset)
async def upload(file: UploadFile, tags: str | None = Form(None)):
    content = await file.read()
    df = parse_file(file.filename or "", content)
    columns = infer_types(df)

    dataset_id = str(uuid.uuid4())
    session_store.put(dataset_id, SessionEntry(df=df, filename=file.filename or "", columns=columns))

    file_path = storage.save_upload(dataset_id, file.filename or "", content)
    tag_list = _split_tags(tags)
    uploaded_at = datetime.now(timezone.utc).isoformat()
    db.insert_dataset(
        dataset_id,
        file.filename or "",
        str(file_path),
        df.shape[0],
        df.shape[1],
        columns,
        uploaded_at,
        tag_list,
    )

    return Dataset(
        id=dataset_id,
        filename=file.filename or "",
        row_count=df.shape[0],
        col_count=df.shape[1],
        columns=columns,
        preview=dataframe_preview(df, PREVIEW_ROWS),
        tags=db.get_tags(dataset_id),
    )


@app.put("/api/datasets/{dataset_id}/column-type", response_model=Dataset)
async def correct_column_type(dataset_id: str, body: TypeCorrectionRequest):
    entry = session_store.get(dataset_id)
    if entry is None:
        raise AppError("세션에서 데이터셋을 찾을 수 없습니다. 새로고침 후 다시 업로드해주세요.", status_code=404)

    updated_columns = session_store.set_column_type(dataset_id, body.column, body.dtype)
    if updated_columns is None:
        raise AppError(f"열을 찾을 수 없습니다: {body.column}", status_code=404)

    # 수동 교정 시 결측률도 새 타입 기준으로 다시 계산한다 (PRD 3.3: 교정 시 통계 재계산).
    for col_meta in updated_columns:
        if col_meta.name == body.column:
            col_meta.missing_rate = missing_rate_for(entry.df[body.column], body.dtype)

    # 교정 이력을 DB에도 반영 — 재호출 후에도 유지되도록 (Pro PRD 완료기준 #2).
    db.update_columns(dataset_id, updated_columns)

    return Dataset(
        id=dataset_id,
        filename=entry.filename,
        row_count=entry.df.shape[0],
        col_count=entry.df.shape[1],
        columns=updated_columns,
        preview=dataframe_preview(entry.df, PREVIEW_ROWS),
        tags=db.get_tags(dataset_id),
    )


@app.get("/api/datasets", response_model=list[DatasetSummary])
async def list_datasets(tag: str | None = None):
    rows = db.list_datasets(tag=tag)
    return [DatasetSummary(**row) for row in rows]


def _load_or_reload_entry(dataset_id: str) -> SessionEntry:
    """세션 캐시에 있으면 그대로, 없으면 DB+디스크에서 복원(Day1 재호출 로직)."""
    entry = session_store.get(dataset_id)
    if entry is not None:
        return entry

    row = db.get_dataset(dataset_id)
    if row is None:
        raise AppError("데이터셋을 찾을 수 없습니다.", status_code=404)

    file_path = Path(row["file_path"])
    if not file_path.exists():
        raise AppError("원본 파일을 찾을 수 없습니다. 다시 업로드해주세요.", status_code=404)

    content = storage.read_upload(file_path)
    df = parse_file(row["filename"], content)
    entry = SessionEntry(df=df, filename=row["filename"], columns=row["columns"])
    session_store.put(dataset_id, entry)
    return entry


@app.get("/api/datasets/{dataset_id}", response_model=Dataset)
async def get_dataset(dataset_id: str):
    entry = _load_or_reload_entry(dataset_id)
    return Dataset(
        id=dataset_id,
        filename=entry.filename,
        row_count=entry.df.shape[0],
        col_count=entry.df.shape[1],
        columns=entry.columns,
        preview=dataframe_preview(entry.df, PREVIEW_ROWS),
        tags=db.get_tags(dataset_id),
    )


@app.put("/api/datasets/{dataset_id}/tags", response_model=DatasetSummary)
async def update_tags(dataset_id: str, body: TagsUpdateRequest):
    row = db.get_dataset(dataset_id)
    if row is None:
        raise AppError("데이터셋을 찾을 수 없습니다.", status_code=404)

    db.set_tags(dataset_id, body.tags)

    return DatasetSummary(
        id=dataset_id,
        filename=row["filename"],
        tags=db.get_tags(dataset_id),
        row_count=row["row_count"],
        col_count=row["col_count"],
        uploaded_at=row["uploaded_at"],
    )


@app.get("/api/datasets/{dataset_id}/stats", response_model=StatsResponse)
async def get_stats(dataset_id: str):
    entry = session_store.get(dataset_id)
    if entry is None:
        raise AppError("세션에서 데이터셋을 찾을 수 없습니다. 새로고침 후 다시 업로드해주세요.", status_code=404)

    columns_stats = compute_stats(entry.df, entry.columns)
    return StatsResponse(
        dataset_id=dataset_id,
        row_count=entry.df.shape[0],
        col_count=entry.df.shape[1],
        total_missing_rate=overall_missing_rate(entry.df),
        columns=columns_stats,
    )


def _get_entry_or_404(dataset_id: str) -> SessionEntry:
    entry = session_store.get(dataset_id)
    if entry is None:
        raise AppError("세션에서 데이터셋을 찾을 수 없습니다. 새로고침 후 다시 업로드해주세요.", status_code=404)
    return entry


@app.get("/api/datasets/{dataset_id}/chart-recommendations", response_model=list[ChartRecommendation])
async def chart_recommendations(dataset_id: str):
    entry = _get_entry_or_404(dataset_id)
    return recommend_charts(entry.columns)


@app.post("/api/datasets/{dataset_id}/chart")
async def create_chart(dataset_id: str, spec: ChartSpec):
    entry = _get_entry_or_404(dataset_id)
    png_bytes = render_chart(entry.df, entry.columns, spec)
    return Response(content=png_bytes, media_type="image/png")


@app.post("/api/datasets/{dataset_id}/aggregate", response_model=AggregateResult)
async def aggregate(dataset_id: str, spec: AggregateSpec):
    entry = _get_entry_or_404(dataset_id)
    result = group_aggregate(entry.df, entry.columns, spec)
    return AggregateResult(**result)


@app.post("/api/datasets/{dataset_id}/aggregate/chart")
async def aggregate_chart(dataset_id: str, spec: AggregateSpec):
    entry = _get_entry_or_404(dataset_id)
    result = group_aggregate(entry.df, entry.columns, spec)
    png_bytes = render_aggregate_chart(result)
    return Response(content=png_bytes, media_type="image/png")


@app.post("/api/datasets/{dataset_id}/pivot", response_model=PivotResult)
async def pivot(dataset_id: str, spec: PivotSpec):
    entry = _get_entry_or_404(dataset_id)
    result = pivot_table(entry.df, entry.columns, spec)
    return PivotResult(**result)


@app.post("/api/datasets/{dataset_id}/pivot/chart")
async def pivot_chart(dataset_id: str, spec: PivotSpec):
    entry = _get_entry_or_404(dataset_id)
    result = pivot_table(entry.df, entry.columns, spec)
    png_bytes = render_pivot_chart(result)
    return Response(content=png_bytes, media_type="image/png")


@app.post("/api/datasets/{dataset_id}/analyses", response_model=SavedAnalysis)
async def save_analysis(dataset_id: str, body: SaveAnalysisRequest):
    if db.get_dataset(dataset_id) is None:
        raise AppError("데이터셋을 찾을 수 없습니다.", status_code=404)

    spec_cls = SPEC_MODEL_BY_KIND[body.kind]
    try:
        spec_obj = spec_cls(**body.spec)
    except ValidationError as e:
        raise AppError(f"저장할 분석 스펙이 올바르지 않습니다: {e}")

    analysis_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    spec_dict = spec_obj.model_dump()
    db.insert_saved_analysis(analysis_id, dataset_id, body.kind, body.title, spec_dict, created_at)

    return SavedAnalysis(
        id=analysis_id,
        dataset_id=dataset_id,
        kind=body.kind,
        title=body.title,
        spec=spec_dict,
        created_at=created_at,
    )


@app.get("/api/datasets/{dataset_id}/analyses", response_model=list[SavedAnalysis])
async def list_analyses(dataset_id: str):
    return [SavedAnalysis(**row) for row in db.list_saved_analyses(dataset_id)]


@app.get("/api/datasets/{dataset_id}/analyses/{analysis_id}/chart")
async def reproduce_analysis(dataset_id: str, analysis_id: str):
    entry = _load_or_reload_entry(dataset_id)

    record = db.get_saved_analysis(analysis_id)
    if record is None or record["dataset_id"] != dataset_id:
        raise AppError("저장된 분석을 찾을 수 없습니다.", status_code=404)

    if record["kind"] == "chart":
        spec = ChartSpec(**record["spec"])
        png_bytes = render_chart(entry.df, entry.columns, spec)
    elif record["kind"] == "aggregate":
        agg_spec = AggregateSpec(**record["spec"])
        result = group_aggregate(entry.df, entry.columns, agg_spec)
        png_bytes = render_aggregate_chart(result)
    else:
        pivot_spec = PivotSpec(**record["spec"])
        result = pivot_table(entry.df, entry.columns, pivot_spec)
        png_bytes = render_pivot_chart(result)

    return Response(content=png_bytes, media_type="image/png")


@app.delete("/api/datasets/{dataset_id}", status_code=204)
async def delete_dataset(dataset_id: str):
    if db.get_dataset(dataset_id) is None:
        raise AppError("데이터셋을 찾을 수 없습니다.", status_code=404)

    db.delete_dataset(dataset_id)
    storage.delete_upload(dataset_id)
    session_store.remove(dataset_id)
    return Response(status_code=204)


@app.delete("/api/datasets/{dataset_id}/analyses/{analysis_id}", status_code=204)
async def delete_analysis(dataset_id: str, analysis_id: str):
    record = db.get_saved_analysis(analysis_id)
    if record is None or record["dataset_id"] != dataset_id:
        raise AppError("저장된 분석을 찾을 수 없습니다.", status_code=404)

    db.delete_saved_analysis(analysis_id)
    return Response(status_code=204)
