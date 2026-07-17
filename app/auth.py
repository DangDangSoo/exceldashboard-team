"""
비밀번호 해싱·세션 토큰 생성을 담당하는 순수 유틸 모듈.
FastAPI를 모른다 — app/core/*.py와 같은 성격이지만 인증을 다루므로 core 밖에 둔다.
"""
import secrets

import bcrypt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)
