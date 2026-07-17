# Pro Day 0 — 인수인계 · 현황 파악 · 확장 계획

## 0. 복사본 동작 확인

로컬에 Python 3.13 venv를 만들어 의존성 설치 후 `uvicorn app.main:app`으로 기동,
curl로 Basic 전체 흐름을 End-to-End 검증했다. 모두 정상.

- 업로드/파싱: `sample_sales.xlsx`(200행 5열), `sample_sales_euckr.csv`(EUC-KR 자동 인식) 둘 다 정상 파싱, 타입 자동판별(datetime/categorical/numeric/boolean) 정확.
- 열 타입 수동 교정: PUT `/column-type`으로 `수량`을 categorical로 교정 → 응답에 반영됨.
- 기술통계: `/stats` 정상 응답(결측률 포함).
- 차트: 추천 7종 생성 확인, 히스토그램/히트맵 등 PNG 실제 생성(HTTP 200, 유효 PNG 바이너리) 확인.
- 집계/피벗: group_aggregate, pivot_table 및 각각의 차트 PNG 엔드포인트 모두 정상.
- 견고성: 잘못된 확장자 업로드(.txt) → 400 + 안내 메시지, 존재하지 않는 dataset_id → 404 + 안내 메시지. 서버 프로세스는 죽지 않음.

git 상태: `main`에 커밋 1개(`b0eef1a Pro: Basic v1.0 복사본에서 시작`)만 있고 태그(`v1.0`)는 이 로컬 저장소엔 없음(복사 시점 기준 스냅샷으로 추정). Pro 작업은 이 브랜치(`pro`)에서 진행한다.

## 1. 기존 구조 요약

### `app/core/*.py` — 순수 함수 모듈 (FastAPI 미의존)

- **`parse.py`** — `parse_file(filename, content: bytes) -> pd.DataFrame`. 확장자 검사(xlsx/xls/csv), 파일 크기 상한(10MB), 행 수 상한(50,000행), CSV 인코딩 자동 판별(chardet → utf-8/cp949/euc-kr 순 시도), 엑셀은 첫 시트만 사용, 완전 빈 행 제거. `dataframe_preview(df, n)`으로 미리보기 JSON(NaN→null, Timestamp→ISO)도 여기서 만든다.
- **`infer_types.py`** — `infer_types(df) -> list[ColumnMeta]`. 판별 순서 boolean → numeric → datetime → categorical(기본값), 각 95% 매치 임계치. `coerce_series(series, dtype)`로 지정 타입에 맞춰 강제 형변환(통계/차트/집계가 모두 이 함수를 공유). `missing_rate_for()`로 수동교정 후 결측률 재계산.
- **`stats.py`** — `compute_stats(df, columns) -> dict[str, ColumnStats]`. numeric(count/missing/mean/median/min/max/std/q1/q3), categorical/boolean(unique/mode/top5 빈도), datetime(min/max) 세 갈래. `overall_missing_rate(df)`.
- **`charts.py`** — `recommend_charts(columns)`로 열 타입 기반 자동 추천(히스토그램×수치열, 막대×범주열, 꺾은선×날짜×수치, 히트맵×수치열 2개 이상). `render_chart(df, columns, ChartSpec) -> PNG bytes`가 5종(histogram/bar/line/scatter/heatmap) 모두 처리하는 단일 진입점 — 화면표시/다운로드 모두 이 PNG 그대로 재사용. `render_aggregate_chart`, `render_pivot_chart`는 group_aggregate/pivot_table의 결과 dict를 받아 별도 PNG를 만든다.
- **`aggregate.py`** — `group_aggregate(df, columns, AggregateSpec) -> dict`(그룹수 상한 20, 초과시 truncated 플래그), `pivot_table(df, columns, PivotSpec) -> dict`(행×열 조합 400칸 상한).
- **`errors.py`** — `AppError(message, status_code=400)` 하나뿐. 라우터의 전역 exception handler가 이걸 잡아 4xx JSON으로 변환하고, 그 외 미처리 예외는 500 + 사용자 메시지로 변환(서버가 죽지 않음).

핵심 특징: 5개 모듈 전부 `import fastapi`가 없다. 입력은 `pd.DataFrame` + pydantic 모델(`ColumnMeta`, `*Spec`), 출력은 pydantic 모델 또는 JSON-safe dict/bytes. 이 순수성이 Pro에서 그대로 재사용 가능한 근거다.

### JSON 데이터 계약 (`app/models.py`, pydantic)

- **`Dataset`** — `id`(uuid), `filename`, `row_count`, `col_count`, `columns: list[ColumnMeta]`, `preview: list[dict]`. `ColumnMeta`는 `name/dtype/missing_rate`.
- **`ChartSpec`** — `chart_type`(histogram/bar/line/scatter/heatmap), `x`, `y`, `title`(모두 요청 즉시 렌더되고 버려짐 — Pro의 "저장된 분석" 후보 1호).
- **`AggregateSpec`** — `group_by: list[str]`, `value`, `agg_func`(sum/mean/count/min/max).
- **`PivotSpec`** — `rows`, `columns`, `value`, `agg_func`.
- 그 외 응답 전용 모델(`StatsResponse`, `AggregateResult`, `PivotResult`, `ChartRecommendation`)은 계산 결과이지 "재현 가능한 설정"이 아니므로 저장 대상은 아님 — 저장 대상은 위 3개 Spec + Dataset.

4종 모두 이미 pydantic → `.model_dump()`로 dict/JSON 직렬화가 즉시 가능. Pro가 이 형태를 그대로 DB 레코드로 얹으면 된다.

### `app/session_store.py` — 인메모리 저장소

- `SessionStore._entries: dict[str, SessionEntry]` 딕셔너리 하나(`threading.Lock`으로 보호), key가 `dataset_id`(uuid).
- `SessionEntry`는 `df`(pandas DataFrame 원본, 파싱 직후 형태 그대로 — 아직 coerce 안 됨), `filename`, `columns: list[ColumnMeta]`(타입 판별/교정 결과)만 담는다.
- 메서드는 `put`, `get`, `set_column_type` 세 개뿐. 전역 상태를 하나의 블롭이 아니라 dataset 단위로 분리해서 담고 있어(이음새 원칙 #3), Pro에서 dataset 단위 DB row로 옮기기 쉬운 모양.
- 주의: `df`는 pandas DataFrame이라 그대로는 JSON이 아니다 — 영속화하려면 별도 직렬화(parquet/csv 등 원본 파일 자체를 저장하거나 DataFrame을 별도 포맷으로) 경로가 필요하다. `columns`(ColumnMeta)는 이미 pydantic이라 바로 저장 가능.

### `app/main.py` — 라우팅 흐름

- `/api/upload` (POST): `parse_file` → `infer_types` → uuid 발급 → `session_store.put` → `Dataset` 응답.
- `/api/datasets/{id}/column-type` (PUT): `session_store.get` → `session_store.set_column_type` → `missing_rate_for` 재계산 → `Dataset` 재응답.
- `/api/datasets/{id}/stats` (GET): `compute_stats` 호출.
- `/api/datasets/{id}/chart-recommendations` (GET), `/chart` (POST, PNG 응답).
- `/api/datasets/{id}/aggregate`, `/aggregate/chart`, `/pivot`, `/pivot/chart`.
- 모든 라우터가 `session_store.get`으로 dataset을 찾은 뒤 core 함수를 호출하고 결과를 pydantic으로 감싸 반환할 뿐 — 로직은 전혀 없다(이음새 원칙 #1 그대로 지켜짐). `_get_entry_or_404` 헬퍼로 반복되는 404 처리만 공유.
- 전역 `AppError` 핸들러(4xx) + 미처리 예외 핸들러(500, 서버 안 죽음)가 앱 레벨에 등록되어 있어 라우터 각각은 에러 변환을 신경 안 써도 된다.

### 프론트엔드 (`templates/index.html` + `static/app.js`)

- 프레임워크 없는 vanilla JS. 전역 상태는 `state = { datasetId, dataset }` 하나뿐 — 새로고침하면 사라짐(의도된 설계).
- 업로드 → `/api/upload` 응답(Dataset)을 그대로 상태에 저장하고 요약/타입표/미리보기 렌더 → 통계·추천차트 병렬 로드.
- 차트/집계/피벗 각각 "빌더" UI가 있고, 빌드 버튼 클릭 시 서버에 Spec(JSON)을 POST → PNG blob을 받아 `<img>`로 표시 + 다운로드 링크(`URL.createObjectURL`)로 연결. 서버가 만든 PNG를 그대로 표시·다운로드에 재사용하는 게 프론트에도 그대로 반영돼 있다.
- 서버가 보내는 JSON 스펙(ChartSpec/AggregateSpec/PivotSpec)과 완전히 동일한 모양을 프론트 JS 객체로 만들어 전송 — 계약이 프론트/백엔드 양쪽에서 이미 일관되게 쓰이고 있다.

## 2. 확장 지점 확인 (이음새 3원칙 검증 결과)

**그대로 재사용:**
- `app/core/*` 5개 모듈은 FastAPI를 전혀 모른다 → Pro에서 손댈 필요 없음.
- `Dataset`/`ChartSpec`/`AggregateSpec`/`PivotSpec` 4종은 이미 pydantic이라 즉시 직렬화 가능 → 그대로 DB 저장 레코드의 페이로드가 된다.
- 각 dataset은 업로드 시점에 이미 `uuid`로 식별된다(`main.py`의 `uuid.uuid4()`) → DB 기본키로 승격 가능.

**유일하게 바꿀 지점:**
- `app/session_store.py`의 인메모리 dict(`SessionStore._entries`)를 영속 저장소(DB)로 교체하는 것 — 이게 Pro의 핵심 변경 지점이다.
- 지금은 `main.py`의 라우터에서 렌더 직후 버려지는 `ChartSpec`/`AggregateSpec`/`PivotSpec`을, 해당 `dataset_id`에 딸린 "저장된 분석" 레코드로 남기는 저장 API(신규 엔드포인트)를 추가해야 한다 — 이 저장 동작 자체는 core 로직 변경 없이 순수하게 새로운 영속화 계층 추가로 끝난다.
- `SessionEntry.df`(pandas DataFrame)는 JSON이 아니므로, 원본 업로드 파일 자체(바이트)를 어딘가에 저장해뒀다가 재호출 시 다시 `parse_file`을 태우는 경로가 필요하다 — DataFrame을 직접 영속화하기보다, "원본 파일 저장 + 재파싱"이 기존 순수 함수를 그대로 재사용할 수 있어 더 이음새에 맞는다.

## 3. Pro가 얹을 것 (계획만, 이번 Day 0에서는 구현 안 함)

- **프로젝트 단위**: 여러 dataset/분석을 프로젝트로 묶어 누적 관리.
- **엑셀 저장·재호출**: 업로드 파일을 저장했다가 다시 불러와 이어 작업(재파싱 경로로 `parse_file` 재사용).
- **분석결과 저장**: `ChartSpec`/`AggregateSpec`/`PivotSpec`을 dataset에 딸린 레코드로 저장해뒀다가 재현(같은 core 함수로 재실행).
- **저장소 도입**: `session_store`의 인메모리 dict → DB로 교체.

## 4. 건드리지 말 것 (Pro 내내 지킬 원칙)

- `app/core/*.py`는 FastAPI·DB 의존성을 들이지 않는다(순수 input→output 유지).
- 기존 JSON 계약(`Dataset`/`ChartSpec`/`AggregateSpec`/`PivotSpec`) 필드는 하위호환 유지 — 필드 추가는 가능하나 기존 필드 의미 변경 금지.
- Basic 기능은 회귀 없이 그대로 동작해야 한다 — 저장을 쓰지 않는 1회성 업로드→분석→다운로드 흐름도 Pro 위에서 계속 동작해야 한다.

## 5. Pro PRD에서 정할 결정 목록

- **DB 종류** — 개인용·실습 규모면 SQLite가 가장 단순한 후보(권장). 확정은 Pro PRD에서.
- **엑셀 파일 저장 방식** — 디스크 경로 저장 vs DB blob 저장.
- **데이터 모델** — 프로젝트 / 데이터셋 / 저장된 분석(Spec) 사이의 1:N 관계 설계.
- **다중사용자 대비** — Team 확장을 고려해 지금 스키마에 `owner`/`project` 경계 컬럼을 값은 단일사용자라도 자리만 미리 열어둘지 여부.
