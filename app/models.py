"""
JSON 데이터 계약 (이음새 원칙 #2).
Basic에선 메모리에만 존재하지만, 이 스키마가 그대로 Pro에서 DB에 저장되고
Team에서 공유되는 단위가 된다. 여기 정의를 변경하면 프론트 계약도 함께 깨진다.
"""
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field

ColumnType = Literal["numeric", "categorical", "datetime", "boolean"]


class ColumnMeta(BaseModel):
    name: str
    dtype: ColumnType
    missing_rate: float


class Dataset(BaseModel):
    id: str
    filename: str
    row_count: int
    col_count: int
    columns: list[ColumnMeta]
    preview: list[dict]
    tags: list[str] = Field(default_factory=list)


class DatasetSummary(BaseModel):
    """저장된 데이터셋 목록(GET /api/datasets) 응답 단위."""
    id: str
    filename: str
    tags: list[str]
    row_count: int
    col_count: int
    uploaded_at: str


class TagsUpdateRequest(BaseModel):
    tags: list[str]


class TypeCorrectionRequest(BaseModel):
    column: str
    dtype: ColumnType


class NumericStats(BaseModel):
    type: Literal["numeric"] = "numeric"
    count: int
    missing_count: int
    mean: Optional[float] = None
    median: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    std: Optional[float] = None
    q1: Optional[float] = None
    q3: Optional[float] = None


class CategoryFrequency(BaseModel):
    value: str
    count: int


class CategoricalStats(BaseModel):
    type: Literal["categorical"] = "categorical"
    count: int
    missing_count: int
    unique_count: int
    mode: Optional[str] = None
    top_frequencies: list[CategoryFrequency] = Field(default_factory=list)


class DatetimeStats(BaseModel):
    type: Literal["datetime"] = "datetime"
    count: int
    missing_count: int
    min: Optional[str] = None
    max: Optional[str] = None


ColumnStats = Union[NumericStats, CategoricalStats, DatetimeStats]


class StatsResponse(BaseModel):
    dataset_id: str
    row_count: int
    col_count: int
    total_missing_rate: float
    columns: dict[str, ColumnStats]


ChartType = Literal["histogram", "bar", "line", "scatter", "heatmap"]


class ChartSpec(BaseModel):
    """
    차트 스펙 JSON 계약. Basic에선 요청 즉시 렌더링되고 버려지지만,
    이 스펙이 그대로 Pro에서 "분석결과 저장"의 단위가 된다.
    """
    chart_type: ChartType
    x: Optional[str] = None
    y: Optional[str] = None
    title: Optional[str] = None


class ChartRecommendation(BaseModel):
    label: str
    spec: ChartSpec


AggFunc = Literal["sum", "mean", "count", "min", "max"]


class AggregateSpec(BaseModel):
    """
    그룹 집계 스펙 JSON 계약. ChartSpec과 마찬가지로 Pro에서
    "분석결과 저장"의 단위가 된다.
    """
    group_by: list[str]
    value: str
    agg_func: AggFunc


class AggregateResult(BaseModel):
    group_by: list[str]
    value: str
    agg_func: AggFunc
    rows: list[dict]
    total_groups: int
    truncated: bool


class PivotSpec(BaseModel):
    rows: str
    columns: str
    value: str
    agg_func: AggFunc


class PivotResult(BaseModel):
    rows: str
    columns: str
    value: str
    agg_func: AggFunc
    row_labels: list[str]
    column_labels: list[str]
    cells: list[list[Optional[float]]]


AnalysisKind = Literal["chart", "aggregate", "pivot"]


class SaveAnalysisRequest(BaseModel):
    """
    저장할 분석 스펙 요청. spec을 dict로 받는 이유: ChartSpec/AggregateSpec/PivotSpec
    3종을 discriminated union으로 받으려면 기존 Spec 모델에 필드를 더해야 하는데,
    이음새 원칙(기존 필드 의미 변경 금지)을 지키기 위해 라우터에서 kind를 보고
    올바른 Spec 클래스로 재구성해 검증한다.
    """
    kind: AnalysisKind
    spec: dict
    title: str


class SavedAnalysis(BaseModel):
    id: str
    dataset_id: str
    kind: AnalysisKind
    title: str
    spec: dict
    created_at: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    invite_code: str


class LoginRequest(BaseModel):
    username: str
    password: str


class UserPublic(BaseModel):
    id: str
    username: str
