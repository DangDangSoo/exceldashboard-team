"""
세션 메모리 저장소 (이음새 원칙 #3): 데이터셋은 uuid로 식별되고,
전역 상태 하나에 다 담기지 않는다. Basic은 프로세스 메모리에만 두지만,
Pro에서는 이 자리를 DB 조회로 바꾸기만 하면 된다.
"""
import threading
from dataclasses import dataclass, field

import pandas as pd

from app.models import ColumnMeta, ColumnType


@dataclass
class SessionEntry:
    df: pd.DataFrame
    filename: str
    columns: list[ColumnMeta] = field(default_factory=list)


class SessionStore:
    def __init__(self) -> None:
        self._entries: dict[str, SessionEntry] = {}
        self._lock = threading.Lock()

    def put(self, dataset_id: str, entry: SessionEntry) -> None:
        with self._lock:
            self._entries[dataset_id] = entry

    def get(self, dataset_id: str) -> SessionEntry | None:
        with self._lock:
            return self._entries.get(dataset_id)

    def set_column_type(self, dataset_id: str, column: str, dtype: ColumnType) -> list[ColumnMeta] | None:
        with self._lock:
            entry = self._entries.get(dataset_id)
            if entry is None:
                return None
            for col_meta in entry.columns:
                if col_meta.name == column:
                    col_meta.dtype = dtype
                    return entry.columns
            return None

    def remove(self, dataset_id: str) -> None:
        with self._lock:
            self._entries.pop(dataset_id, None)


session_store = SessionStore()
