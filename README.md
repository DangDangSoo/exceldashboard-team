# Excel2Dashboard — Team

엑셀/CSV를 업로드하면 자동으로 열 타입을 판별하고, 기술통계·차트·그룹집계·피벗까지 보여주는
데이터 대시보드입니다. **로그인이 필요합니다** — 팀원끼리 계정을 나눠 쓰고, 로그인한 사람은
누구나 서로의 데이터셋을 조회할 수 있지만, 수정·삭제는 업로드한 본인만 가능합니다.

3부작(Basic → Pro → Team) 중 3부(마지막). 자세한 배경은 [`PRD_Excel2Dashboard_Team_v0.1.md`](./PRD_Excel2Dashboard_Team_v0.1.md)(이 저장소), [`PRD_Excel2Dashboard_Pro_v0.1.md`](./PRD_Excel2Dashboard_Pro_v0.1.md)(2부 PRD), [`PRD_Excel2Dashboard_Basic_v0.1.md`](./PRD_Excel2Dashboard_Basic_v0.1.md)(1부 원본 PRD) 참고.

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

**회원가입에는 초대코드가 필요합니다.** 최초 기동 시 기본값은 `CHANGEME`입니다. 실제로 팀과 같이 쓰려면 서버에 접근 권한이 있는 사람이 미리 바꿔두세요(관리자 화면은 없고, 터미널에서 직접 바꿉니다):

```bash
sqlite3 data/app.db "UPDATE settings SET value='새코드' WHERE key='invite_code';"
```

## 기능

### Basic · Pro 기능 (그대로 유지)
- **업로드·파싱**: xlsx/xls/csv, 헤더 1행 전제, CSV 인코딩(UTF-8/EUC-KR) 자동 감지, 파일 10MB/5만 행 상한.
- **열 타입 판별**: 수치/범주/날짜/불리언 자동 분류 + 결측률 표시 + 드롭다운 수동 교정.
- **기술통계·시각화(5종)·그룹 집계·피벗·PNG 다운로드**: Basic 때 기능 그대로.
- **영속화**: 원본 파일·메타데이터·태그·저장된 분석이 서버 재시작에도 남아있고 다시 불러올 수 있음(Pro Day1~2).
- **삭제**: 데이터셋·저장된 분석 삭제(DB·디스크·세션 캐시까지 정리, Pro Day3).

### Team에서 추가된 기능
- **계정·로그인(Day 1)**: 아이디/비밀번호로 회원가입(초대코드 필요)·로그인·로그아웃. 로그인은 쿠키+DB `sessions` 테이블로 유지되어 서버를 재시작해도 로그인 상태가 살아있습니다. 비밀번호는 `bcrypt`로 해싱해서 저장합니다.
- **소유권·접근 제어(Day 2)**: 업로드한 사람이 데이터셋의 소유자로 기록됩니다. **조회(목록·상세·통계·차트·집계·피벗·분석재현)는 로그인한 팀원 누구나** 가능하지만, **태그·열타입 수정, 데이터셋 삭제, 분석 저장·삭제는 소유자만** 가능합니다(아니면 403). 화면에서도 본인 것이 아니면 그 버튼·입력칸 자체가 안 보입니다.
- **회원가입 UX(Day 3)**: 비밀번호 확인란, 아이디 입력 중 실시간 중복 확인(0.4초 디바운스), "MVP 데모라 아이디/비번 분실 시 복구가 안 된다"는 안내 문구.
- **견고화(Day 3)**: 세션 만료 시 정확히 401 + DB 세션 행 정리, 동시 가입 경쟁 상태(같은 아이디로 거의 동시에 두 번 가입) 방어, 정적 파일(`app.js`) 캐시 무효화를 파일 수정시각 기반으로 자동화(배포할 때마다 브라우저가 항상 최신 JS를 받음).

## 스택 · 아키텍처

- **백엔드**: Python + FastAPI + pandas. 파싱·타입판별·통계·집계·차트 생성을 담당.
- **차트**: 서버에서 matplotlib으로 PNG 생성. 화면 표시와 다운로드가 **같은 PNG 바이트**를 재사용.
- **프론트**: 바닐라 HTML/JS (프레임워크·빌드도구 없음).
- **저장**: SQLite(`data/app.db`, 표준 `sqlite3` 직접 사용, ORM 없음)에 데이터셋 메타데이터·태그·저장된 분석·**계정·세션·설정**을 보관하고, 업로드 원본 파일은 디스크(`uploads/`)에 그대로 저장.
- **인증**: 쿠키 기반 서버 세션. `app/auth.py`가 `bcrypt` 비밀번호 해싱과 세션 토큰 생성을 담당(순수 함수, FastAPI 미의존). 세션은 메모리가 아니라 DB의 `sessions` 테이블에 저장되어 서버 재시작에도 로그인이 유지됨.

## 폴더 구조

```
app/
  main.py            # FastAPI 라우터 — core 모듈 호출 + 인증/소유권 검증
  models.py          # JSON 데이터 계약 (Dataset, ChartSpec, SavedAnalysis, RegisterRequest 등)
  db.py              # SQLite 영속 계층 — datasets/dataset_tags/saved_analyses/users/sessions/settings
  auth.py            # 비밀번호 해싱·세션 토큰 생성 (순수 함수)
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

## 이음새 3원칙 (Basic → Pro → Team까지 지켜진 것)

1. **로직 ↔ UI/라우팅 분리** — `app/core/*.py`는 Team에서도 전혀 수정하지 않았다. FastAPI·DB·인증 어느 쪽도 import하지 않는 순수 함수 그대로.
2. **직렬화 가능한 JSON 데이터 계약** — `Dataset`/`ChartSpec`/`AggregateSpec`/`PivotSpec`는 Basic 때 필드를 그대로 유지(추가만 함, 예: `Dataset.owner_username`).
3. **id 부여** — Basic에서 부여한 `uuid`(dataset_id)가 그대로 DB 기본키로 승격됐고, Team의 `owner_id`도 같은 방식으로 `users.id`를 참조한다.

자세한 분석은 [`PRO_DAY0_NOTES.md`](./PRO_DAY0_NOTES.md) 참고.

## Team 범위 밖 (의도적 제외)

- **비밀번호 재설정·찾기 기능** — 이메일 등 본인 확인 수단 자체가 없어서(아이디+비밀번호만) 만들 방법이 없다. 잊어버리면 서버 파일에 직접 접근해 DB를 고치는 것 말고는 복구 수단이 없다(README 실행 방법 상단 참고).
- **관리자 페이지·역할(`is_admin`)** — 초대코드 변경 같은 관리 작업은 터미널에서 SQL로 직접 처리(§PRD 3.2). 사용자 목록·삭제 같은 UI도 없음.
- **세분화된 권한(편집자 등급 등)** — 소유자/조회자 2단계만.
- **개별 데이터셋 단위 공유 설정(비공개/특정인 공개)** — "로그인한 모두에게 공개" 하나로 통일.
- 다중 시트, SVG 내보내기, 실시간 협업(동시 편집), 예측/머신러닝 — 3부작 어디에도 계획 없음.

## API 요약

### 인증
| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/auth/register` | 회원가입(아이디·비밀번호·초대코드) → 자동 로그인 |
| GET | `/api/auth/check-username` | 아이디 중복 여부 확인(로그인 불필요) |
| POST | `/api/auth/login` | 로그인 |
| POST | `/api/auth/logout` | 로그아웃 |
| GET | `/api/auth/me` | 현재 로그인 사용자 확인 |

### 데이터셋 · 분석 (전부 로그인 필요, ⚠️ 표시는 소유자만 가능 — 아니면 403)
| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/upload` | 파일 업로드(+선택적 태그) → `Dataset` 반환(업로드한 사람이 소유자로 기록됨) |
| GET | `/api/datasets` | 데이터셋 목록 (`?tag=` 필터 가능, 전체 공개) |
| GET | `/api/datasets/{id}` | 데이터셋 재호출(전체 공개) |
| PUT | `/api/datasets/{id}/tags` | ⚠️ 태그 수정 |
| DELETE | `/api/datasets/{id}` | ⚠️ 데이터셋 삭제 |
| PUT | `/api/datasets/{id}/column-type` | ⚠️ 열 타입 수동 교정 |
| GET | `/api/datasets/{id}/stats` | 기술통계(전체 공개) |
| GET | `/api/datasets/{id}/chart-recommendations` | 자동 추천 차트 목록(전체 공개) |
| POST | `/api/datasets/{id}/chart` | 차트 PNG 생성(전체 공개) |
| POST | `/api/datasets/{id}/aggregate` | 그룹 집계 표(전체 공개) |
| POST | `/api/datasets/{id}/aggregate/chart` | 그룹 집계 막대 PNG(전체 공개) |
| POST | `/api/datasets/{id}/pivot` | 피벗 표(전체 공개) |
| POST | `/api/datasets/{id}/pivot/chart` | 피벗 히트맵 PNG(전체 공개) |
| POST | `/api/datasets/{id}/analyses` | ⚠️ 차트/집계/피벗 스펙 저장 |
| GET | `/api/datasets/{id}/analyses` | 저장된 분석 목록(전체 공개) |
| GET | `/api/datasets/{id}/analyses/{analysis_id}/chart` | 저장된 분석 재현(전체 공개) |
| DELETE | `/api/datasets/{id}/analyses/{analysis_id}` | ⚠️ 저장된 분석 삭제 |
