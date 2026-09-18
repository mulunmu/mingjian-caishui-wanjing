from __future__ import annotations

from app.schemas.claim import Claim, ClaimTrace, ClaimValue
from app.services.semantic_primary import _comparison_claims_from_groups


def _claim(group: str, metric: str, number: float, unit: str) -> Claim:
    return Claim(
        claim=f"{group}的{metric}为{number}{unit}。",
        value=ClaimValue(metric=metric, number=number, unit=unit),
        trace=ClaimTrace(table="assessment", field=metric, query_id=f"Q_{metric}"),
        confidence="computed",
        evidence_chain=[f"industry_group={group}"],
    )


def test_group_comparison_builds_deterministic_cross_group_claims():
    claims = [
        _claim("制造", "overall_score", 42.69, "分"),
        _claim("IT软件", "overall_score", 42.76, "分"),
        _claim("制造", "tax_health_score", 21.0, "分"),
        _claim("IT软件", "tax_health_score", 26.99, "分"),
    ]
    out = _comparison_claims_from_groups(claims, ["制造", "IT软件"])
    assert len(out) == 2
    assert any("综合经营表现对比" in item.claim for item in out)
    assert any("税务健康得分对比" in item.claim for item in out)
    assert all((item.value.metric or "").startswith("compare_") for item in out)
