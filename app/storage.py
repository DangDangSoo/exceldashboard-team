"""
업로드 원본 파일을 디스크에 저장/조회/삭제하는 순수 입출력 모듈.
FastAPI를 모른다 — app/core/*.py와 같은 성격이지만 파일시스템을 다루므로 core 밖에 둔다.
"""
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
UPLOADS_DIR = PROJECT_ROOT / "uploads"


def save_upload(dataset_id: str, filename: str, content: bytes) -> Path:
    dataset_dir = UPLOADS_DIR / dataset_id
    dataset_dir.mkdir(parents=True, exist_ok=True)
    file_path = dataset_dir / filename
    file_path.write_bytes(content)
    return file_path


def read_upload(file_path: Path) -> bytes:
    return file_path.read_bytes()


def delete_upload(dataset_id: str) -> None:
    dataset_dir = UPLOADS_DIR / dataset_id
    if dataset_dir.exists():
        shutil.rmtree(dataset_dir)
