import json

from fastapi.responses import JSONResponse


class UTF8JSONResponse(JSONResponse):
    """JSON 响应，UTF-8 编码且不转义中文"""

    media_type = "application/json; charset=utf-8"

    def render(self, content) -> bytes:
        return json.dumps(content, ensure_ascii=False, default=str).encode("utf-8")


def error_response(status_code: int, code: str, message: str, detail: dict | None = None) -> JSONResponse:
    """标准化错误响应 — 所有 API 错误统一走此格式"""
    body: dict = {"error": {"code": code, "message": message}}
    if detail:
        body["error"]["detail"] = detail
    return UTF8JSONResponse(content=body, status_code=status_code)
