"""순수 함수 모듈: group-by 집계, 피벗. FastAPI·세션 개념은 들어오지 않는다."""
import json

import pandas as pd

from app.core.errors import AppError
from app.core.infer_types import coerce_series
from app.models import AggregateSpec, ColumnMeta, PivotSpec

AGG_FUNCS = ("sum", "mean", "count", "min", "max")
CATEGORY_DTYPES = ("categorical", "boolean")

MAX_GROUP_ROWS = 20  # group-by 결과 표시 상한(카테고리 폭발 방어)
MAX_PIVOT_CELLS = 400  # 행 카테고리 수 × 열 카테고리 수 상한


def _by_name(columns: list[ColumnMeta]) -> dict:
    return {c.name: c for c in columns}


def _require_categorical(by_name: dict, name: str | None, label: str) -> ColumnMeta:
    if not name:
        raise AppError(f"{label} 열을 선택해주세요.")
    if name not in by_name:
        raise AppError(f"존재하지 않는 열입니다: {name}")
    col = by_name[name]
    if col.dtype not in CATEGORY_DTYPES:
        raise AppError(f"'{name}' 열은 {col.dtype} 타입입니다. {label}에는 범주/불리언 타입 열이 필요합니다.")
    return col


def _require_numeric(by_name: dict, name: str | None, label: str) -> ColumnMeta:
    if not name:
        raise AppError(f"{label} 열을 선택해주세요.")
    if name not in by_name:
        raise AppError(f"존재하지 않는 열입니다: {name}")
    col = by_name[name]
    if col.dtype != "numeric":
        raise AppError(f"'{name}' 열은 {col.dtype} 타입입니다. {label}에는 수치 타입 열이 필요합니다.")
    return col


def _check_agg_func(agg_func: str) -> None:
    if agg_func not in AGG_FUNCS:
        raise AppError(f"지원하지 않는 집계함수입니다: {agg_func}")


def _category_labels(series: pd.Series, dtype: str) -> pd.Series:
    """그룹/피벗 기준 열을 문자열 라벨로 만든다. 결측은 'None' 문자열 대신 사람이 읽을 라벨로."""
    coerced = coerce_series(series, dtype)
    return coerced.apply(lambda v: "(결측)" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v))


def group_aggregate(df: pd.DataFrame, columns: list[ColumnMeta], spec: AggregateSpec) -> dict:
    by_name = _by_name(columns)
    _check_agg_func(spec.agg_func)
    if not spec.group_by:
        raise AppError("그룹 기준 열을 1개 이상 선택해주세요.")

    group_cols = [_require_categorical(by_name, name, "그룹 기준").name for name in spec.group_by]
    value_col = _require_numeric(by_name, spec.value, "집계 대상(값)")

    work = pd.DataFrame({name: _category_labels(df[name], by_name[name].dtype) for name in group_cols})
    work[value_col.name] = coerce_series(df[value_col.name], "numeric")
    work = work.dropna(subset=[value_col.name])

    if work.empty:
        raise AppError(f"'{value_col.name}' 열에 유효한 수치 데이터가 없어 집계할 수 없습니다.")

    grouped = work.groupby(group_cols, dropna=False)[value_col.name].agg(spec.agg_func).reset_index()
    grouped = grouped.sort_values(value_col.name, ascending=False)

    total_groups = len(grouped)
    truncated = total_groups > MAX_GROUP_ROWS
    if truncated:
        grouped = grouped.head(MAX_GROUP_ROWS)

    return {
        "group_by": group_cols,
        "value": value_col.name,
        "agg_func": spec.agg_func,
        "rows": json.loads(grouped.to_json(orient="records", force_ascii=False)),
        "total_groups": total_groups,
        "truncated": truncated,
    }


def pivot_table(df: pd.DataFrame, columns: list[ColumnMeta], spec: PivotSpec) -> dict:
    by_name = _by_name(columns)
    _check_agg_func(spec.agg_func)

    row_col = _require_categorical(by_name, spec.rows, "피벗 행")
    col_col = _require_categorical(by_name, spec.columns, "피벗 열")
    if row_col.name == col_col.name:
        raise AppError("피벗의 행과 열은 서로 다른 열이어야 합니다.")
    value_col = _require_numeric(by_name, spec.value, "피벗 값")

    work = pd.DataFrame(
        {
            row_col.name: _category_labels(df[row_col.name], row_col.dtype),
            col_col.name: _category_labels(df[col_col.name], col_col.dtype),
            value_col.name: coerce_series(df[value_col.name], "numeric"),
        }
    ).dropna(subset=[value_col.name])

    if work.empty:
        raise AppError(f"'{value_col.name}' 열에 유효한 수치 데이터가 없어 피벗할 수 없습니다.")

    n_rows = work[row_col.name].nunique()
    n_cols = work[col_col.name].nunique()
    if n_rows * n_cols > MAX_PIVOT_CELLS:
        raise AppError(
            f"피벗 조합이 너무 많습니다({n_rows}행 × {n_cols}열 = {n_rows * n_cols:,}칸, "
            f"상한 {MAX_PIVOT_CELLS:,}칸). 카테고리 수가 적은 열을 선택해주세요."
        )

    pivot = pd.pivot_table(
        work,
        index=row_col.name,
        columns=col_col.name,
        values=value_col.name,
        aggfunc=spec.agg_func,
        dropna=False,
    )

    return {
        "rows": row_col.name,
        "columns": col_col.name,
        "value": value_col.name,
        "agg_func": spec.agg_func,
        "row_labels": [str(v) for v in pivot.index.tolist()],
        "column_labels": [str(v) for v in pivot.columns.tolist()],
        "cells": json.loads(pivot.to_json(orient="values")),
    }
