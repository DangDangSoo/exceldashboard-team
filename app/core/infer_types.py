"""
순수 함수 모듈: DataFrame -> 열 타입 판별(+수동 교정 시 강제 형변환).
판별 순서: boolean -> numeric -> datetime -> categorical(기본값).
"""
import pandas as pd

from app.models import ColumnMeta, ColumnType

_BOOLEAN_TOKENS = {"true", "false", "yes", "no", "y", "n", "참", "거짓", "예", "아니오"}
_NUMERIC_MATCH_RATIO = 0.95
_DATETIME_MATCH_RATIO = 0.95


def infer_types(df: pd.DataFrame) -> list[ColumnMeta]:
    columns = []
    for col in df.columns:
        series = df[col]
        dtype = infer_column_type(series)
        missing_rate = round(float(series.isna().mean()), 4) if len(series) else 0.0
        columns.append(ColumnMeta(name=str(col), dtype=dtype, missing_rate=missing_rate))
    return columns


def infer_column_type(series: pd.Series) -> ColumnType:
    non_null = series.dropna()
    if non_null.empty:
        return "categorical"  # 전부 결측이면 판단 불가 -> 기본값

    if _looks_boolean(non_null):
        return "boolean"
    if _looks_numeric(non_null):
        return "numeric"
    if _looks_datetime(non_null):
        return "datetime"
    return "categorical"


def _looks_boolean(s: pd.Series) -> bool:
    if pd.api.types.is_bool_dtype(s):
        return True
    normalized = s.astype(str).str.strip().str.lower()
    unique_vals = set(normalized.unique())
    return len(unique_vals) <= 2 and unique_vals.issubset(_BOOLEAN_TOKENS)


def _looks_numeric(s: pd.Series) -> bool:
    if pd.api.types.is_bool_dtype(s):
        return False
    if pd.api.types.is_numeric_dtype(s):
        return True
    converted = pd.to_numeric(s.astype(str).str.strip(), errors="coerce")
    return converted.notna().mean() >= _NUMERIC_MATCH_RATIO


def _looks_datetime(s: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(s):
        return True
    # 날짜가 텍스트로 들어온 경우도 인식 시도 (PRD 4절)
    converted = pd.to_datetime(s.astype(str).str.strip(), errors="coerce", format="mixed")
    return converted.notna().mean() >= _DATETIME_MATCH_RATIO


def coerce_series(series: pd.Series, dtype: ColumnType) -> pd.Series:
    """사용자가 수동 교정한 타입에 맞춰 통계 계산용으로 강제 형변환한다."""
    if dtype == "numeric":
        return pd.to_numeric(series.astype(str).str.strip(), errors="coerce")
    if dtype == "datetime":
        return pd.to_datetime(series.astype(str).str.strip(), errors="coerce", format="mixed")
    if dtype == "boolean":
        normalized = series.astype(str).str.strip().str.lower()
        true_tokens = {"true", "yes", "y", "참", "예"}
        false_tokens = {"false", "no", "n", "거짓", "아니오"}
        return normalized.map(
            lambda v: True if v in true_tokens else (False if v in false_tokens else None)
        )
    return series.where(series.notna(), None).astype("object")


def missing_rate_for(series: pd.Series, dtype: ColumnType) -> float:
    """수동 교정 후 재계산: coercion 과정에서 새로 드러나는 결측(예: 텍스트인데 숫자로 지정)도 반영."""
    coerced = coerce_series(series, dtype)
    if len(coerced) == 0:
        return 0.0
    return round(float(coerced.isna().mean()), 4)
