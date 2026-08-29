"""FastAPI 集成测试 — TestClient 验证路由可访问性"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient


def test_app_creates():
    from app.main import app
    assert app.title == "明鉴・财税票・万景"


def test_client_health():
    from app.main import app
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "data_mode" in data


def test_client_auth_register():
    from app.main import app
    client = TestClient(app)
    response = client.post("/api/v1/auth/register", json={
        "email": "integration-test@example.com",
        "password": "test123456"
    })
    assert response.status_code in (200, 400)


def test_client_chat():
    from app.main import app
    client = TestClient(app)
    response = client.post("/api/v1/chat", json={
        "query": "分析各行业的趋势走向",
        "session_id": None
    })
    assert response.status_code in (200, 429)
    if response.status_code == 200:
        data = response.json()
        assert "reply" in data
        assert "intent" in data


def test_removed_enterprise_routes():
    from app.main import app
    client = TestClient(app)
    for path in (
        "/api/v1/enterprise/list",
        "/api/v1/enterprise/ENT001",
        "/api/v1/network/invoice-edges",
        "/api/v1/graph/industry-path",
    ):
        resp = client.get(path)
        assert resp.status_code == 404


def test_all_routes_accessible():
    from app.main import app
    client = TestClient(app)
    routes_to_test = [
        ("GET", "/api/v1/health"),
        ("GET", "/api/v1/risk/warnings"),
        ("GET", "/api/v1/risk/summary"),
        ("POST", "/api/v1/chat", {"query": "有哪些风险预警", "session_id": None}),
        ("POST", "/api/v1/chat", {"query": "综合评分怎么样", "session_id": None}),
    ]
    # 数据端点 DB 不可用返回 503（不伪造 mock）、聊天限流返回 429，均属预期降级而非故障。
    for method, path, *body in routes_to_test:
        if method == "GET":
            resp = client.get(path)
        else:
            resp = client.post(path, json=body[0] if body else {})
        assert resp.status_code in (200, 429, 503), f"{method} {path} returned {resp.status_code}"


def test_risk_endpoints_no_mock_fallback_on_db_error(monkeypatch):
    """DB 异常时 /risk/warnings 与 /risk/summary 返回 503，而非伪造 mock。"""
    from app.main import app
    import app.api.v1.risk as risk_api

    async def boom(*_args, **_kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(risk_api.assessment, "get_all_warnings", boom)
    monkeypatch.setattr(risk_api.assessment, "get_dashboard_summary", boom)

    client = TestClient(app)
    assert client.get("/api/v1/risk/warnings").status_code == 503
    assert client.get("/api/v1/risk/summary").status_code == 503


def test_report_preview_html_structure():
    """报告预览 API 返回含封面/KPI/章节的 HTML（结构回归）；须订阅鉴权。"""
    from app.main import app
    from app.services.auth_service import create_access_token

    client = TestClient(app)
    token = create_access_token("preview@example.com", "admin", "subscriber")
    resp = client.post(
        "/api/v1/report/preview",
        json={"scenario": "general", "query": "生成行业趋势风控报告"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    html = resp.text
    assert "行业" in html or "报告" in html
    assert "抗幻觉" in html or "validation" in html.lower() or "claims" in html.lower()


def test_report_preview_requires_auth():
    from app.main import app

    client = TestClient(app)
    resp = client.post(
        "/api/v1/report/preview",
        json={"scenario": "general", "query": "生成行业趋势风控报告"},
    )
    assert resp.status_code == 401


def test_chat_returns_chart_payload():
    """对话层 charts 字段结构正确（line/bar/radar/heatmap/funnel 之一或 null）"""
    from app.main import app

    client = TestClient(app)
    for query in ("分析各行业的趋势走向", "有哪些风险预警", "综合评分"):
        resp = client.post("/api/v1/chat", json={"query": query, "session_id": None})
        if resp.status_code != 200:
            continue
        charts = resp.json().get("charts")
        if charts is None:
            continue
        assert charts["type"] in ("line", "bar", "pie", "radar", "heatmap", "funnel", "warnings")
        if charts["type"] in ("radar", "funnel"):
            assert "data" in charts
        break
