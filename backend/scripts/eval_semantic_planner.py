"""Generate and execute semantic-planning conversation evaluations."""
from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    from scripts.eval_http import login, post_json
except ImportError:
    from backend.scripts.eval_http import login, post_json


@dataclass(frozen=True)
class SemanticEvalCase:
    case_id: str
    query: str
    expected_action: str
    expected_route: str


def build_semantic_cases() -> list[SemanticEvalCase]:
    industries = ["制造", "批发零售", "服务", "建筑", "IT软件", "其他"]
    provinces = ["广东", "江苏", "山西", "浙江", "山东"]
    metrics = ["资产负债率", "现金流", "净利率", "纳税准时率", "真实性得分", "发票风险"]
    cases: list[SemanticEvalCase] = []
    for index, industry in enumerate(industries * 8, start=1):
        cases.append(SemanticEvalCase(f"metadata-{index}", f"{industry}有哪些企业？", "metadata_query", "inventory"))
    for index, province in enumerate(provinces * 7, start=1):
        cases.append(SemanticEvalCase(f"region-{index}", f"{province}有哪些行业？", "metadata_query", "inventory"))
    for enterprise in range(1, 31):
        cases.append(SemanticEvalCase(f"profile-{enterprise}", f"企业{enterprise}的地区和行业是什么？", "profile", "profile"))
    for enterprise in range(1, 41):
        metric = metrics[(enterprise - 1) % len(metrics)]
        cases.append(SemanticEvalCase(f"analysis-{enterprise}", f"企业{enterprise}的{metric}怎么样？", "analysis", "analysis"))
    for index, industry in enumerate(industries * 5, start=1):
        cases.append(SemanticEvalCase(f"compare-{index}", f"{industry}和{industries[index % len(industries)]}的风险对比", "analysis", "analysis"))
    for index in range(1, 21):
        cases.append(SemanticEvalCase(f"report-{index}", f"生成一份包含财务、税务和真实性的风险报告 {index}", "report", "report"))
    for index, query in enumerate(["你好", "谢谢", "你能做什么？", "系统有哪些功能？", "天气怎么样？", "帮我编一个营收"], start=1):
        action = "conversation" if index <= 4 else "refuse"
        cases.append(SemanticEvalCase(f"conversation-{index}", query, action, action))
    return cases


def _passes(case: SemanticEvalCase, response: dict) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not str(response.get("reply") or "").strip():
        errors.append("empty_reply")
    primary = ((response.get("data") or {}).get("primary") or {})
    route = str(primary.get("route") or response.get("intent") or "")
    if route and route != case.expected_route:
        errors.append(f"route:{route}!={case.expected_route}")
    if primary.get("fallback") is not False:
        errors.append("fallback")
    claims = (response.get("data") or {}).get("claims") or []
    if case.expected_action == "analysis":
        if not claims:
            errors.append("analysis_without_claims")
        for index, claim in enumerate(claims):
            trace = claim.get("trace") if isinstance(claim, dict) else None
            if not trace or not trace.get("table") or not trace.get("field"):
                errors.append(f"untraceable_claim:{index}")
    return not errors, errors


async def run_evaluation(args) -> dict:
    token = login(args.base_url, args.email, args.password)
    cases = build_semantic_cases()[: args.limit]
    failures = []
    passed = 0
    semaphore = asyncio.Semaphore(max(1, args.concurrency))

    async def one(case: SemanticEvalCase):
        async with semaphore:
            try:
                response = await asyncio.to_thread(
                    post_json,
                    f"{args.base_url.rstrip('/')}/api/v1/chat",
                    {"query": case.query, "session_id": f"eval-{case.case_id}-{uuid.uuid4().hex[:8]}"},
                    token=token,
                )
                ok, errors = _passes(case, response)
                return case, ok, errors
            except Exception as exc:
                return case, False, [f"request_error:{exc}"]

    for case, ok, errors in await asyncio.gather(*(one(case) for case in cases)):
        if ok:
            passed += 1
        else:
            failures.append({"case": asdict(case), "errors": errors})
    return {"total": len(cases), "passed": passed, "failed": len(failures), "pass_rate": round(passed / max(1, len(cases)), 4), "failures": failures}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--email", default="admin@example.com")
    parser.add_argument("--password", default="admin123")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)
    report = asyncio.run(run_evaluation(args))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
