"""순수 함수 모듈: DataFrame + 열 타입 -> 기술통계."""
import pandas as pd

from app.core.infer_types import coerce_series
from app.models import CategoricalStats, CategoryFrequency, ColumnMeta, ColumnStats, DatetimeStats, NumericStats

_TOP_N_CATEGORIES = 5


def compute_stats(df: pd.DataFrame, columns: list[ColumnMeta]) -> dict[str, ColumnStats]:
    result: dict[str, ColumnStats] = {}
    for col_meta in columns:
        series = coerce_series(df[col_meta.name], col_meta.dtype)
        if col_meta.dtype == "numeric":
            result[col_meta.name] = _numeric_stats(series)
        elif col_meta.dtype == "datetime":
            result[col_meta.name] = _datetime_stats(series)
        else:  # categorical, boolean
            result[col_meta.name] = _categorical_stats(series)
    return result


def overall_missing_rate(df: pd.DataFrame) -> float:
    total_cells = df.shape[0] * df.shape[1]
    if total_cells == 0:
        return 0.0
    return round(float(df.isna().sum().sum()) / total_cells, 4)


def _numeric_stats(s: pd.Series) -> NumericStats:
    non_null = s.dropna()
    count = int(s.shape[0])
    missing = int(s.isna().sum())
    if non_null.empty:
        return NumericStats(count=count, missing_count=missing)
    return NumericStats(
        count=count,
        missing_count=missing,
        mean=round(float(non_null.mean()), 4),
        median=round(float(non_null.median()), 4),
        min=round(float(non_null.min()), 4),
        max=round(float(non_null.max()), 4),
        std=round(float(non_null.std()), 4) if len(non_null) > 1 else 0.0,
        q1=round(float(non_null.quantile(0.25)), 4),
        q3=round(float(non_null.quantile(0.75)), 4),
    )


def _categorical_stats(s: pd.Series) -> CategoricalStats:
    non_null = s.dropna()
    count = int(s.shape[0])
    missing = int(s.isna().sum())
    if non_null.empty:
        return CategoricalStats(count=count, missing_count=missing, unique_count=0)
    value_counts = non_null.astype(str).value_counts()
    top = [
        CategoryFrequency(value=value, count=int(freq))
        for value, freq in value_counts.head(_TOP_N_CATEGORIES).items()
    ]
    return CategoricalStats(
        count=count,
        missing_count=missing,
        unique_count=int(non_null.nunique()),
        mode=str(value_counts.index[0]),
        top_frequencies=top,
    )


def _datetime_stats(s: pd.Series) -> DatetimeStats:
    non_null = s.dropna()
    count = int(s.shape[0])
    missing = int(s.isna().sum())
    if non_null.empty:
        return DatetimeStats(count=count, missing_count=missing)
    return DatetimeStats(
        count=count,
        missing_count=missing,
        min=non_null.min().isoformat(),
        max=non_null.max().isoformat(),
    )
