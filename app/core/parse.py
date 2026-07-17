"""
순수 함수 모듈: 업로드된 파일 바이트 -> pandas DataFrame.
FastAPI, 세션 저장 등 어떤 프레임워크 개념도 이 모듈에 들어오지 않는다.
"""
import io
import json

import chardet
import pandas as pd

from app.core.errors import AppError

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
MAX_ROWS = 50_000
ALLOWED_EXTENSIONS = {"xlsx", "xls", "csv"}

_ENCODING_CANDIDATES = ("utf-8", "utf-8-sig", "cp949", "euc-kr")


def parse_file(filename: str, content: bytes) -> pd.DataFrame:
    """한 파일 = 한 탭, 1행 헤더 · 2행부터 데이터 전제로 파싱한다."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise AppError(
            f"지원하지 않는 파일 형식입니다(.{ext or '확장자 없음'}). "
            "xlsx, xls, csv 파일만 업로드할 수 있습니다."
        )

    if len(content) == 0:
        raise AppError("빈 파일입니다. 내용이 있는 파일을 올려주세요.")

    if len(content) > MAX_FILE_SIZE_BYTES:
        mb = MAX_FILE_SIZE_BYTES // (1024 * 1024)
        raise AppError(f"파일 크기가 {mb}MB 상한을 초과했습니다.", status_code=413)

    if ext == "csv":
        df = _parse_csv(content)
    else:
        df = _parse_excel(content, ext)

    if df.shape[1] == 0:
        raise AppError("열을 찾을 수 없습니다. 1행에 헤더가 있는 파일인지 확인하세요.")

    # 완전 빈 행 방어: 지저분한 데이터에서 흔함
    df = df.dropna(how="all").reset_index(drop=True)

    if df.shape[0] == 0:
        raise AppError("헤더만 있고 실제 데이터 행이 없는 파일입니다.")

    if df.shape[0] > MAX_ROWS:
        raise AppError(
            f"행 수가 {MAX_ROWS:,}행 상한을 초과했습니다(현재 {df.shape[0]:,}행).",
            status_code=413,
        )

    return df


def _detect_encoding(content: bytes) -> str:
    result = chardet.detect(content[:200_000])
    encoding = (result.get("encoding") or "utf-8").lower()
    if encoding in ("euc-kr", "ms949", "cp949", "euc_kr"):
        return "cp949"
    return encoding


def _parse_csv(content: bytes) -> pd.DataFrame:
    detected = _detect_encoding(content)
    tried = []
    for encoding in [detected, *[e for e in _ENCODING_CANDIDATES if e != detected]]:
        if encoding in tried:
            continue
        tried.append(encoding)
        try:
            return pd.read_csv(io.BytesIO(content), encoding=encoding, header=0)
        except UnicodeDecodeError:
            continue
        except pd.errors.EmptyDataError:
            raise AppError("빈 CSV 파일입니다.")
        except pd.errors.ParserError as e:
            raise AppError(f"CSV 형식을 해석할 수 없습니다: {e}")

    raise AppError("CSV 인코딩을 인식하지 못했습니다(UTF-8/EUC-KR 시도 실패).")


def _parse_excel(content: bytes, ext: str) -> pd.DataFrame:
    engine = "openpyxl" if ext == "xlsx" else "xlrd"
    try:
        excel_file = pd.ExcelFile(io.BytesIO(content), engine=engine)
    except Exception as e:
        raise AppError(f"손상되었거나 읽을 수 없는 엑셀 파일입니다: {e}")

    sheet_name = excel_file.sheet_names[0]  # 한 파일 = 한 탭 전제 -> 첫 시트만 사용
    try:
        return excel_file.parse(sheet_name, header=0)
    except Exception as e:
        raise AppError(f"엑셀 시트를 해석할 수 없습니다: {e}")


def dataframe_preview(df: pd.DataFrame, n: int) -> list[dict]:
    """상위 N행을 JSON-safe(dict) 레코드로 변환한다 (NaN->null, Timestamp->ISO 문자열)."""
    head = df.head(n)
    return json.loads(head.to_json(orient="records", date_format="iso", force_ascii=False))
