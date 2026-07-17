"""공통 예외. 라우터는 이 예외를 잡아 4xx + 사용자에게 보이는 메시지로 변환한다."""


class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
