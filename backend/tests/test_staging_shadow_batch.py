from __future__ import annotations

from scripts.run_staging_shadow_batch import build_query_plan


def test_build_query_plan_covers_analysis_and_edge_cases():
    plan = build_query_plan(
        [
            {"name": "企业1", "enterprise_id": "ENT1"},
            {"name": "企业2", "enterprise_id": "ENT2"},
        ]
    )
    queries = [item["query"] for item in plan]
    assert len(queries) >= 20
    assert any("资产负债率" in query for query in queries)
    assert any("增值税税负" in query for query in queries)
    assert any("帮我编" in query for query in queries)
    assert any(query == "你好" for query in queries)


def test_diverse_query_plan_uses_different_supported_metrics():
    plan = build_query_plan(
        [{"name": "企业8", "enterprise_id": "ENT8"}],
        profile="diverse",
    )
    queries = [item["query"] for item in plan]
    assert any("流动比率" in query for query in queries)
    assert any("毛利率" in query for query in queries)
    assert any("应收账款周转" in query for query in queries)
    assert any("所得税税负" in query for query in queries)
    assert not any("资产负债率高不高" == query for query in queries)