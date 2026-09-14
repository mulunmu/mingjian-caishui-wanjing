"""会话存储单元测试（含 M0：owner / TTL 拆分 / 历史列表）"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_ensure_session_id():
    from app.services.session_store import ensure_session_id

    sid1 = ensure_session_id(None)
    assert len(sid1) > 0
    sid2 = ensure_session_id("")
    assert len(sid2) > 0
    sid3 = ensure_session_id("my-session")
    assert sid3 == "my-session"


def test_store_and_retrieve():
    from app.services.session_store import ensure_session_id, store_session, get_session

    sid = ensure_session_id("test-123", owner="u@example.com")
    store_session(
        sid,
        "trend_industry",
        query="分析各行业的趋势走向",
        function="trend",
        dimension="industry",
        owner="u@example.com",
        reply="各行业趋势整体平稳。",
        followups=["哪里异常？"],
    )
    session = get_session(sid)
    assert session is not None
    assert session.get("last_intent") == "trend_industry"
    assert session.get("last_function") == "trend"
    assert "trend" in session.get("covered_functions", [])
    assert session.get("owner") == "u@example.com"
    assert session["history"][-1].get("reply")


def test_expired_session():
    from app.services.session_store import get_session

    s = get_session("nonexistent-session-id")
    assert s is None


def test_list_and_load_history_memory():
    from app.services import session_store

    session_store.store.clear()
    owner = "demo@mingjian.test"
    sid = session_store.ensure_session_id(None, owner=owner)
    session_store.store_session(
        sid,
        "score_overall",
        query="整体风险评分如何？",
        function="score",
        dimension="overall",
        owner=owner,
        reply="整体评分中等偏稳。",
    )
    listed = session_store.list_sessions(owner)
    assert any(item["session_id"] == sid for item in listed)
    assert listed[0]["summary"].startswith("整体风险")

    detail = session_store.load_history(owner, sid)
    assert detail is not None
    assert detail["session_id"] == sid
    roles = [m["role"] for m in detail["messages"]]
    assert roles == ["user", "assistant"]


def test_history_survives_active_ttl():
    """活跃 30min 过期后，7 天内历史仍可加载。"""
    from app.services import session_store

    session_store.store.clear()
    owner = "ttl@mingjian.test"
    sid = session_store.ensure_session_id("ttl-session", owner=owner)
    session_store.store_session(
        sid,
        "fraud_overall",
        query="哪里不对劲？",
        function="fraud",
        dimension="overall",
        owner=owner,
        reply="进销存在错配信号。",
    )
    # 模拟活跃过期但仍在历史窗口内
    session_store.store[sid]["updated_at"] = time.time() - (session_store.ACTIVE_TTL_SECONDS + 60)
    loaded = session_store.get_session(sid)
    assert loaded is not None
    assert loaded["history"]
    detail = session_store.load_history(owner, sid)
    assert detail is not None
    assert len(detail["messages"]) >= 2


def test_owner_isolation():
    from app.services import session_store

    session_store.store.clear()
    sid = session_store.ensure_session_id("owned-1", owner="a@x.com")
    session_store.store_session(
        sid,
        "score_overall",
        query="私有问题",
        owner="a@x.com",
        reply="私有答复",
    )
    assert session_store.load_history("b@x.com", sid) is None
    assert session_store.delete_session("b@x.com", sid) is False
    assert session_store.delete_session("a@x.com", sid) is True
