# Excel2Dashboard — Pro

엑셀/CSV를 업로드하면 자동으로 열 타입을 판별하고, 기술통계·차트·그룹집계·피벗까지 보여주는
데이터 대시보드입니다. **Basic과 달리 저장이 됩니다** — 업로드한 원본 파일과 태그, 저장한
차트/집계/피벗 분석이 서버에 계속 남아 있어 새로고침하거나 서버를 재시작해도 다시 불러올 수
있습니다.

3부작(Basic → Pro → Team) 중 2부. 자세한 배경은 [`PRD_Excel2Dashboard_Pro_v0.1.md`](./PRD_Excel2Dashboard_Pro_v0.1.md)(이 저장소), [`PRD_Excel2Dashboard_Basic_v0.1.md`](./PRD_Excel2Dashboard_Basic_v0.1.md)(1부 원본 PRD), [`PRO_DAY0_NOTES.md`](./PRO_DAY0_NOTES.md)(Basic → Pro 인수인계 노트) 참고.

## 실행 방법

**Python 3.10 이상이 필요합니다** (`str | None` 같은 최신 타입 문법을 코드 전반에서 사용). 3.9 이하에서는 `import` 시점에 바로 에러가 납니다.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload
```

브라우저에서 `http://127.0.0.1:8000` 접속. `sample_data/`에 테스트용 엑셀/CSV 샘플이 있습니다.

처음 실행하면 `data/app.db`(SQLite)와 `uploads/`(원본 파일 저장 폴더)가 자동으로 생성됩니다. 둘 다 `.gitignore`에 등록되어 있어 git에는 올라가지 않습니다 — 저장소를 새로 내려받으면 빈 상태로 시작합니다.

## 기능

### Basic 기능 (그대로 유지)
- **업로드·파싱**: xlsx/xls/csv, 헤더 1행 전제, CSV 인코딩(UTF-8/EUC-KR) 자동 감지, 파일 10MB/5만 행 상한.
- **열 타입 판별**: 수치/범주/날짜/불리언 자동 분류 + 결측률 표시 + 드롭다운 수동 교정(교정 시 결측률 재계산).
- **기술통계**: 수치열(개수·결측·평균·중앙값·최소/최대·표준편차·Q1/Q3), 범주열(고유값 수·최빈값·상위 빈도).
- **시각화(5종)**: 히스토그램·막대·꺾은선·산점도·상관 히트맵. 열 타입 기반 자동 추천 + 축/열을 고르는 수동 생성.
- **그룹 집계**: 범주열 1~2개 기준 group-by + 집계함수(합/평균/개수/최소/최대) → 표 + 막대 차트.
- **피벗**: 행×열(범주) × 값(수치, 집계함수) 피벗 표 + 히트맵 스타일 차트.
- **PNG 다운로드**: 모든 차트(추천/수동/집계/피벗)를 화면에 표시된 것과 동일한 PNG로 다운로드.

### Pro에서 추가된 기능
- **파일·메타데이터 영속화(Day 1)**: 업로드한 원본 파일을 `uploads/{dataset_id}/`에, 메타데이터·열 타입을 SQLite에 저장. 서버를 재시작해도 "저장된 데이터셋" 목록에 남아있고 다시 불러올 수 있습니다.
- **태그 기반 모아보기(Day 1)**: 업로드 시(또는 이후 언제든) 데이터셋에 자유 텍스트 태그를 붙이고, 태그로 필터링해서 모아볼 수 있습니다. 태그는 trim + 영문 소문자 통일로 정규화됩니다.
- **분석결과 저장·재현(Day 2)**: 만든 차트/집계/피벗 각각에 "분석 저장" 버튼이 있습니다. PNG 자체가 아니라 스펙(JSON)만 저장해두고, "보기"를 누르면 그 스펙으로 최신 데이터를 다시 계산해 PNG를 새로 만듭니다.
- **삭제(Day 3)**: 데이터셋과 저장된 분석을 각각 삭제할 수 있습니다. 데이터셋을 지우면 DB 행·원본 파일·딸린 저장 분석·메모리 캐시가 모두 함께 정리됩니다.

## 스택 · 아키텍처

- **백엔드**: Python + FastAPI + pandas. 파싱·타입판별·통계·집계·차트 생성을 담당.
- **차트**: 서버에서 matplotlib으로 PNG 생성. 화면 표시와 다운로드가 **같은 PNG 바이트**를 재사용.
- **프론트**: 바닐라 HTML/JS (프레임워크·빌드도구 없음).
- **저장**: **SQLite**(`data/app.db`, 표준 `sqlite3` 직접 사용, ORM 없음)에 데이터셋 메타데이터·태그·저장된 분석 스펙을 보관하고, 업로드 원본 파일은 디스크(`uploads/`)에 그대로 저장. `session_store.py`는 "지금 이 프로세스가 들고 있는 DataFrame 캐시" 역할만 하며, 진짜 저장소는 DB+디스크입니다.

## 폴더 구조

```
app/
  main.py            # FastAPI 라우터 — core 모듈 호출만, 로직 없음
  models.py          # JSON 데이터 계약 (Dataset, ChartSpec, AggregateSpec, PivotSpec, SavedAnalysis 등)
  db.py              # SQLite 영속 계층 — datasets/dataset_tags/saved_analyses 테이블
  storage.py         # 업로드 원본 파일 디스크 저장/조회/삭제 (순수 함수)
  session_store.py   # uuid -> (DataFrame, 열 메타) 세션 메모리 캐시
  core/
    parse.py         # 파일 바이트 -> DataFrame (순수 함수)
    infer_types.py   # DataFrame -> 열 타입 판별 + 강제 형변환 (순수 함수)
    stats.py         # DataFrame + 타입 -> 기술통계 (순수 함수)
    charts.py        # (DataFrame, 열 메타, ChartSpec) -> PNG 바이트 (순수 함수)
    aggregate.py      # group-by 집계 · 피벗 (순수 함수)
    errors.py         # AppError — 4xx 변환용 공통 예외
templates/index.html
static/app.js, static/style.css
sample_data/          # 테스트용 샘플 엑셀·CSV
data/                  # SQLite DB (gitignore, 실행 시 자동 생성)
uploads/               # 업로드 원본 파일 (gitignore, 실행 시 자동 생성)
requirements.txt
```

## 이음새 3원칙 (Basic에서 Pro로 넘어오며 지켜진 것)

1. **로직 ↔ UI/라우팅 분리** — `app/core/*.py`는 Pro에서도 전혀 수정하지 않았다. FastAPI·DB 어느 쪽도 import하지 않는 순수 함수 그대로.
2. **직렬화 가능한 JSON 데이터 계약** — `Dataset`/`ChartSpec`/`AggregateSpec`/`PivotSpec`는 Basic 때 필드를 그대로 유지(추가만 함, 예: `Dataset.tags`). 이 계약이 그대로 `saved_analyses.spec_json`, `datasets.columns_json`으로 DB에 저장된다.
3. **id 부여** — Basic에서 부여한 `uuid`(dataset_id)가 그대로 DB 기본키로 승격됐다.

자세한 분석은 [`PRO_DAY0_NOTES.md`](./PRO_DAY0_NOTES.md) 참고.

## Pro 범위 밖 (의도적 제외)

- **로그인·계정·다중 사용자·공유·권한** → Team의 역할. Pro는 여전히 단일 사용자 전제.
- **프로젝트 단위 그룹핑** → 태그로 대체(§ PRD 결정). 계층형 "프로젝트" 개념은 만들지 않았다.
- 다중 시트, SVG 내보내기, 실시간 협업, 예측/머신러닝, 디스크 용량 자동 정리 — 3부작 어디에도 계획 없음(디스크 정리는 삭제 API로 수동 대응).

## API 요약

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/upload` | 파일 업로드(+선택적 태그) → 파싱·타입판별·영속 저장 → `Dataset` 반환 |
| GET | `/api/datasets` | 저장된 데이터셋 목록 (`?tag=` 필터 가능) |
| GET | `/api/datasets/{id}` | 데이터셋 재호출(세션에 없으면 DB+디스크에서 복원) |
| PUT | `/api/datasets/{id}/tags` | 태그 수정 |
| DELETE | `/api/datasets/{id}` | 데이터셋 삭제(DB·디스크·세션·딸린 저장분석까지 정리) |
| PUT | `/api/datasets/{id}/column-type` | 열 타입 수동 교정(DB에도 반영) |
| GET | `/api/datasets/{id}/stats` | 기술통계 |
| GET | `/api/datasets/{id}/chart-recommendations` | 자동 추천 차트 목록 |
| POST | `/api/datasets/{id}/chart` | 차트 PNG 생성 |
| POST | `/api/datasets/{id}/aggregate` | 그룹 집계 표 |
| POST | `/api/datasets/{id}/aggregate/chart` | 그룹 집계 막대 PNG |
| POST | `/api/datasets/{id}/pivot` | 피벗 표 |
| POST | `/api/datasets/{id}/pivot/chart` | 피벗 히트맵 PNG |
| POST | `/api/datasets/{id}/analyses` | 차트/집계/피벗 스펙 저장 |
| GET | `/api/datasets/{id}/analyses` | 저장된 분석 목록 |
| GET | `/api/datasets/{id}/analyses/{analysis_id}/chart` | 저장된 분석을 최신 데이터로 재계산해 PNG 반환 |
| DELETE | `/api/datasets/{id}/analyses/{analysis_id}` | 저장된 분석 삭제 |
