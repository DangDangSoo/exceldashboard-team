"""
순수 함수 모듈: (DataFrame, 열 메타, ChartSpec) -> PNG 바이트.
FastAPI·세션 개념은 이 모듈에 들어오지 않는다. 화면 표시와 다운로드가
같은 PNG 바이트를 쓰도록, 렌더링은 항상 여기 한 곳에서만 일어난다.
"""
import io

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.font_manager as fm  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from app.core.errors import AppError
from app.core.infer_types import coerce_series
from app.models import ChartRecommendation, ChartSpec, ColumnMeta

BAR_TOP_N = 10
HEATMAP_MAX_COLUMNS = 15
FIGSIZE = (7, 4.5)
DPI = 150
_ACCENT = "#3a6df0"

_DTYPE_LABEL = {"numeric": "수치", "categorical": "범주", "datetime": "날짜", "boolean": "불리언"}
_AGG_LABEL = {"sum": "합계", "mean": "평균", "count": "개수", "min": "최소", "max": "최대"}

_KOREAN_FONT_CANDIDATES = ("Apple SD Gothic Neo", "AppleGothic", "Nanum Gothic", "Malgun Gothic")


def _configure_korean_font() -> None:
    available = {f.name for f in fm.fontManager.ttflist}
    for name in _KOREAN_FONT_CANDIDATES:
        if name in available:
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False


_configure_korean_font()


def recommend_charts(columns: list[ColumnMeta]) -> list[ChartRecommendation]:
    """열 타입만 근거로 한 자동 추천 세트 (PRD 3.4)."""
    numeric_cols = [c.name for c in columns if c.dtype == "numeric"]
    categorical_cols = [c.name for c in columns if c.dtype in ("categorical", "boolean")]
    datetime_cols = [c.name for c in columns if c.dtype == "datetime"]

    recs: list[ChartRecommendation] = []
    for name in numeric_cols:
        recs.append(ChartRecommendation(label=f"히스토그램 · {name}", spec=ChartSpec(chart_type="histogram", x=name)))
    for name in categorical_cols:
        recs.append(ChartRecommendation(label=f"막대 · {name}", spec=ChartSpec(chart_type="bar", x=name)))
    if datetime_cols and numeric_cols:
        date_col = datetime_cols[0]
        for name in numeric_cols:
            recs.append(
                ChartRecommendation(
                    label=f"꺾은선 · {date_col} → {name}",
                    spec=ChartSpec(chart_type="line", x=date_col, y=name),
                )
            )
    if len(numeric_cols) >= 2:
        recs.append(ChartRecommendation(label="상관 히트맵 · 전체 수치열", spec=ChartSpec(chart_type="heatmap")))
    return recs


def render_chart(df: pd.DataFrame, columns: list[ColumnMeta], spec: ChartSpec) -> bytes:
    by_name = {c.name: c for c in columns}

    if spec.chart_type == "histogram":
        col = _require_column(by_name, spec.x, ("numeric",), "히스토그램")
        series = coerce_series(df[col.name], "numeric").dropna()
        fig = _draw_histogram(series, col.name, spec.title)
    elif spec.chart_type == "bar":
        col = _require_column(by_name, spec.x, ("categorical", "boolean"), "막대")
        series = coerce_series(df[col.name], col.dtype).dropna()
        fig = _draw_bar(series, col.name, spec.title)
    elif spec.chart_type == "line":
        xcol = _require_column(by_name, spec.x, ("datetime",), "꺾은선(X축)")
        ycol = _require_column(by_name, spec.y, ("numeric",), "꺾은선(Y축)")
        x = coerce_series(df[xcol.name], "datetime")
        y = coerce_series(df[ycol.name], "numeric")
        fig = _draw_line(x, y, xcol.name, ycol.name, spec.title)
    elif spec.chart_type == "scatter":
        xcol = _require_column(by_name, spec.x, ("numeric",), "산점도(X축)")
        ycol = _require_column(by_name, spec.y, ("numeric",), "산점도(Y축)")
        x = coerce_series(df[xcol.name], "numeric")
        y = coerce_series(df[ycol.name], "numeric")
        fig = _draw_scatter(x, y, xcol.name, ycol.name, spec.title)
    elif spec.chart_type == "heatmap":
        numeric_cols = [c for c in columns if c.dtype == "numeric"]
        if len(numeric_cols) < 2:
            raise AppError("상관 히트맵을 그리려면 수치열이 2개 이상 필요합니다.")
        fig = _draw_heatmap(df, numeric_cols, spec.title)
    else:
        raise AppError(f"지원하지 않는 차트 종류입니다: {spec.chart_type}")

    return _fig_to_png(fig)


def _require_column(by_name: dict, col_name: str | None, allowed: tuple[str, ...], chart_label: str) -> ColumnMeta:
    if not col_name:
        raise AppError(f"{chart_label}에 사용할 열을 선택해주세요.")
    if col_name not in by_name:
        raise AppError(f"존재하지 않는 열입니다: {col_name}")
    col = by_name[col_name]
    if col.dtype not in allowed:
        allowed_label = "/".join(_DTYPE_LABEL[a] for a in allowed)
        raise AppError(
            f"'{col_name}' 열은 {_DTYPE_LABEL[col.dtype]} 타입입니다. "
            f"{chart_label}에는 {allowed_label} 타입 열이 필요합니다."
        )
    return col


def _set_ylabel(ax, text: str) -> None:
    # matplotlib이 90도 회전된 한글 y축 라벨을 글리프끼리 겹쳐 그리는 문제가 있어(폰트 무관),
    # 가로로 눕혀서 표시한다.
    ax.set_ylabel(text, rotation=0, ha="right", va="center", labelpad=10)


def _draw_histogram(series: pd.Series, col_name: str, title: str | None):
    if series.empty:
        raise AppError(f"'{col_name}' 열에 유효한 수치 데이터가 없습니다.")
    fig, ax = plt.subplots(figsize=FIGSIZE)
    bins = min(30, max(5, int(len(series) ** 0.5)))
    ax.hist(series, bins=bins, color=_ACCENT, edgecolor="white")
    ax.set_xlabel(col_name)
    _set_ylabel(ax, "빈도")
    ax.set_title(title or f"{col_name} 분포")
    fig.tight_layout()
    return fig


def _draw_bar(series: pd.Series, col_name: str, title: str | None, top_n: int = BAR_TOP_N):
    if series.empty:
        raise AppError(f"'{col_name}' 열에 유효한 데이터가 없습니다.")
    counts = series.astype(str).value_counts()
    if len(counts) > top_n:
        top = counts.iloc[:top_n]
        others_sum = counts.iloc[top_n:].sum()
        counts = pd.concat([top, pd.Series({"기타": others_sum})])

    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.bar(counts.index.astype(str), counts.values, color=_ACCENT)
    ax.set_xlabel(col_name)
    _set_ylabel(ax, "빈도")
    ax.set_title(title or f"{col_name} 빈도")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    return fig


def _draw_line(x: pd.Series, y: pd.Series, x_name: str, y_name: str, title: str | None):
    valid = pd.DataFrame({"x": x, "y": y}).dropna().sort_values("x")
    if valid.empty:
        raise AppError(f"'{x_name}'/'{y_name}' 열에 유효한 데이터 쌍이 없습니다.")
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.plot(valid["x"], valid["y"], color=_ACCENT, marker="o", markersize=3, linewidth=1.2)
    ax.set_xlabel(x_name)
    _set_ylabel(ax, y_name)
    ax.set_title(title or f"{x_name}에 따른 {y_name} 추세")
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def _draw_scatter(x: pd.Series, y: pd.Series, x_name: str, y_name: str, title: str | None):
    valid = pd.DataFrame({"x": x, "y": y}).dropna()
    if valid.empty:
        raise AppError(f"'{x_name}'/'{y_name}' 열에 유효한 데이터 쌍이 없습니다.")
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.scatter(valid["x"], valid["y"], color=_ACCENT, alpha=0.7, s=18)
    ax.set_xlabel(x_name)
    _set_ylabel(ax, y_name)
    ax.set_title(title or f"{x_name} × {y_name}")
    fig.tight_layout()
    return fig


def _draw_heatmap(df: pd.DataFrame, numeric_cols: list[ColumnMeta], title: str | None):
    numeric_df = pd.DataFrame({c.name: coerce_series(df[c.name], "numeric") for c in numeric_cols})

    if numeric_df.shape[1] > HEATMAP_MAX_COLUMNS:
        top_variance_cols = numeric_df.var().sort_values(ascending=False).head(HEATMAP_MAX_COLUMNS).index
        numeric_df = numeric_df[top_variance_cols]

    corr = numeric_df.corr()
    if corr.isna().all().all():
        raise AppError("상관계수를 계산할 유효한 데이터가 없습니다.")

    n = len(corr.columns)
    fig, ax = plt.subplots(figsize=(max(6, n * 0.6), max(5, n * 0.6)))
    im = ax.imshow(corr.values, cmap="coolwarm", vmin=-1, vmax=1)
    ax.set_xticks(range(n))
    ax.set_xticklabels(corr.columns, rotation=45, ha="right")
    ax.set_yticks(range(n))
    ax.set_yticklabels(corr.columns)
    for i in range(n):
        for j in range(n):
            value = corr.values[i, j]
            if not pd.isna(value):
                ax.text(j, i, f"{value:.2f}", ha="center", va="center", fontsize=8)
    fig.colorbar(im, ax=ax, shrink=0.8)
    ax.set_title(title or "상관 히트맵")
    fig.tight_layout()
    return fig


def _fig_to_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def render_aggregate_chart(agg_result: dict) -> bytes:
    """group_aggregate()의 반환 dict를 받아 막대 차트 PNG로 그린다."""
    group_cols = agg_result["group_by"]
    value_col = agg_result["value"]
    agg_label = _AGG_LABEL[agg_result["agg_func"]]

    rows = agg_result["rows"]
    if not rows:
        raise AppError("집계 결과가 없어 차트를 그릴 수 없습니다.")

    labels = [" · ".join(str(row[col]) for col in group_cols) for row in rows]
    values = [row[value_col] for row in rows]

    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.bar(labels, values, color=_ACCENT)
    ax.set_xlabel(" × ".join(group_cols))
    _set_ylabel(ax, f"{value_col} ({agg_label})")
    ax.set_title(f"{' × '.join(group_cols)}별 {value_col} {agg_label}")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    return _fig_to_png(fig)


def render_pivot_chart(pivot_result: dict) -> bytes:
    """pivot_table()의 반환 dict를 받아 히트맵 스타일 PNG로 그린다."""
    row_labels = pivot_result["row_labels"]
    col_labels = pivot_result["column_labels"]
    if not row_labels or not col_labels:
        raise AppError("피벗 결과가 없어 차트를 그릴 수 없습니다.")

    matrix = pd.DataFrame(pivot_result["cells"], index=row_labels, columns=col_labels).astype(float)
    n_rows, n_cols = matrix.shape

    fig, ax = plt.subplots(figsize=(max(6, n_cols * 0.8), max(5, n_rows * 0.6)))
    im = ax.imshow(matrix.values, cmap="Blues")
    ax.set_xticks(range(n_cols))
    ax.set_xticklabels(col_labels, rotation=45, ha="right")
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels(row_labels)
    for i in range(n_rows):
        for j in range(n_cols):
            value = matrix.values[i, j]
            if not pd.isna(value):
                ax.text(j, i, f"{value:,.1f}", ha="center", va="center", fontsize=8)
    fig.colorbar(im, ax=ax, shrink=0.8)
    ax.set_xlabel(pivot_result["columns"])
    _set_ylabel(ax, pivot_result["rows"])
    ax.set_title(f"{pivot_result['value']} {_AGG_LABEL[pivot_result['agg_func']]} 피벗")
    fig.tight_layout()
    return _fig_to_png(fig)
