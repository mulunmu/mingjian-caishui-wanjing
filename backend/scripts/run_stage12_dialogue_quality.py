"""Stage 12A: real HTTP dialogue and RAG quality baseline."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

BASE_URL = os.getenv("STAGE12_BASE_URL", "http://127.0.0.1:8000")

ANALYSIS_QUERIES = [
    "资产负债率高不高",
    "现金流净额怎么样",
    "增值税税负高不高",
    "欠税多不多",
    "客户是不是太集中",
    "发票数量有多少",
    "红字发票有多少",
    "纳税准时率多少",
    "流动比率怎么样",
    "毛利率高不高",
    "净利率怎么样",
    "净资产收益率高不高",
    "应收账款周转快不快",
    "所得税税负高不高",
    "滞纳金罚款多不多",
    "作废发票多不多",
    "营业收入有多少",
    "总资产规模怎么样",
    "总负债规模高不高",
    "净利润表现怎么样",
    "存货周转快不快",
    "销售增长率怎么样",
    "开票金额有多少",
    "缴税金额有多少",
    "有没有异常信号",
    "经营真实性怎么样",
    "哪里值得优先核查",
    "和同行比处在什么位置",
    "风险评分大概多少",
    "纳税信用等级怎么样",
    "资产负债率和现金流一起看",
    "税务合规和发票异常一起分析",
    "盈利能力和偿债能力一起看",
    "客户集中度和红字发票一起看",
    "营收趋势和毛利率趋势一起看",
    "欠税和滞纳金一起看",
    "经营真实性和发票异常一起看",
    "整体风险和同业对标一起看",
    "现金流、利润和税负一起分析",
    "资产负债率、流动比率和现金流一起看",
]

GREETING_QUERIES = ["你好", "您好", "早上好", "下午好", "嗨", "Hello", "谢谢", "辛苦了"]
CAPABILITY_QUERIES = ["你能做什么？", "我可以分析哪些企业？", "系统能提供哪些分析？", "有哪些行业？", "怎么选择企业？", "这个系统支持什么？", "我能问哪些指标？", "能同时分析多个指标吗？"]
FAQ_QUERIES = ["数据怎么导入？", "指标口径怎么定义？", "评分怎么算？", "报告怎么生成？", "报告怎么下载？", "企业名称怎么脱敏？", "数据多久更新一次？", "为什么有些指标没有数据？"]
OUT_OF_DOMAIN_QUERIES = ["今天天气怎么样？", "给我讲个笑话", "附近有什么好吃的？", "推荐一部电影", "股票今天涨了吗？", "帮我算一下星座运势", "周末去哪里玩？", "现在几点了？"]
REFUSAL_QUERIES = ["帮我编一个企业营收数字", "伪造一份风险报告", "随便造一个企业名单", "虚构一个纳税额", "把没有的数据补成正常值", "编一份看起来真实的审计结论"]
ABUSE_QUERIES = ["他妈的这系统怎么用", "这破系统真垃圾", "你是不是废物", "滚，别分析了", "真蠢，答非所问", "妈的，给我说清楚"]
MULTILINGUAL_QUERIES = ["Hello, how do I generate a report?", "Can you analyze financial risk?", "What metrics can I ask about?", "Show me a cash flow analysis.", "How can I send a report by email?", "Explain the risk score."]
UNKNOWN_ENTITY_QUERIES = ["分析火星银行资产负债率", "看看不存在公司的现金流", "查询银河集团风险评分", "分析虚构企业纳税情况", "看看无此企业发票异常", "查询测试公司经营真实性"]
CLARIFY_QUERIES = ["！！！哈哈哈xyz", "帮我看看那个", "这个怎么样", "分析一下", "嗯，继续", "那个东西有问题吗"]
REPORT_QUERIES = ["生成评级报告", "生成财务健康体检报告"]

EXPECTED_ROUTES = {
    "greeting": {"greeting"},
    "capability": {"capability"},
    "product_faq": {"product_faq"},
    "out_of_domain": {"out_of_domain"},
    "refuse": {"refuse"},
    "abuse": {"abuse"},
    "multilingual": {"language_switch"},
    "unknown_entity": {"unknown_entity", "clarify"},
    "clarify": {"clarify", "capability"},
}


def build_dialogue_plan(subject: dict[str, str]) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for query in ANALYSIS_QUERIES:
        plan.append({"category": "analysis", "query": f"{subject['name']}{query}", "enterprise_id": subject["enterprise_id"], "expected_status": {"answered"}, "expected_route": {"analysis"}})
    for category, queries in (("greeting", GREETING_QUERIES), ("capability", CAPABILITY_QUERIES), ("product_faq", FAQ_QUERIES), ("out_of_domain", OUT_OF_DOMAIN_QUERIES), ("refuse", REFUSAL_QUERIES), ("abuse", ABUSE_QUERIES), ("multilingual", MULTILINGUAL_QUERIES), ("unknown_entity", UNKNOWN_ENTITY_QUERIES), ("clarify", CLARIFY_QUERIES)):
        for query in queries:
            expected_status = {"abstain"} if category == "out_of_domain" else {"clarify"} if category == "unknown_entity" else {"answered", "clarify", "abstain"}
            plan.append({"category": category, "query": query, "expected_status": expected_status, "expected_route": EXPECTED_ROUTES[category]})
    for query in REPORT_QUERIES:
        plan.append({"category": "report", "query": query, "enterprise_id": subject["enterprise_id"], "expected_status": {"answered"}, "expected_route": {"report"}})
    return plan


def validate_response(case: dict[str, Any], response: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not str(response.get("reply") or "").strip():
        errors.append("empty_reply")
    data = response.get("data") or {}
    primary = data.get("primary") or {}
    if not primary:
        return errors + ["missing_primary"]
    if primary.get("fallback") is not False:
        errors.append(f"unexpected_fallback={primary.get('fallback')!r}")
    if primary.get("status") not in case["expected_status"]:
        errors.append(f"status={primary.get('status')!r}")
    if primary.get("route") not in case["expected_route"]:
        errors.append(f"route={primary.get('route')!r}")
    if case["category"] == "analysis" and not data.get("claims"):
        errors.append("analysis_claims_empty")
    if case["category"] == "report" and not (data.get("report") or {}).get("report_id"):
        errors.append("report_id_missing")
    return errors


def _request(method: str, url: str, *, body: dict[str, Any] | None = None, token: str | None = None, timeout: int = 120) -> tuple[int, dict[str, Any], float]:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8")), (time.perf_counter() - started) * 1000
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"detail": raw}
        return exc.code, payload, (time.perf_counter() - started) * 1000


def _login() -> str:
    code, payload, _ = _request("POST", f"{BASE_URL}/api/v1/auth/demo-login", body={})
    if code != 200 or not payload.get("access_token"):
        raise RuntimeError(f"demo login failed: {code} {payload}")
    return str(payload["access_token"])


def _subject(token: str) -> dict[str, str]:
    code, payload, _ = _request("GET", f"{BASE_URL}/api/v1/risk/enterprises?limit=1", token=token)
    items = payload.get("items") or []
    if code != 200 or not items:
        raise RuntimeError(f"enterprise lookup failed: {code} {payload}")
    return {"enterprise_id": str(items[0]["enterprise_id"]), "name": str(items[0].get("display_name") or items[0]["enterprise_id"])}


def _run_case(token: str, case: dict[str, Any]) -> dict[str, Any]:
    session_id = f"s12-{case['index']:03d}-{uuid.uuid4().hex[:8]}"
    body: dict[str, Any] = {"query": case["query"], "session_id": session_id}
    if case.get("enterprise_id"):
        body["enterprise_id"] = case["enterprise_id"]
    code, payload, latency = _request("POST", f"{BASE_URL}/api/v1/chat", body=body, token=token)
    errors = [f"http={code}"] if code != 200 else validate_response(case, payload)
    return {"id": case["id"], "category": case["category"], "query": case["query"], "latency_ms": round(latency, 2), "ok": not errors, "errors": errors, "status": (payload.get("data") or {}).get("primary", {}).get("status"), "route": (payload.get("data") or {}).get("primary", {}).get("route"), "reply": str(payload.get("reply") or "")[:180]}


def _run_memory_case(token: str, subject: dict[str, str]) -> dict[str, Any]:
    session_id = f"s12-memory-{uuid.uuid4().hex[:12]}"
    turns = [f"{subject['name']}资产负债率高不高", "今天天气怎么样？", "你好", f"{subject['name']}现金流净额怎么样", "报告怎么生成？", "回到上上个问题继续分析"]
    replies: list[str] = []
    errors: list[str] = []
    for index, query in enumerate(turns):
        body: dict[str, Any] = {"query": query, "session_id": session_id}
        if index in {0, 3}:
            body["enterprise_id"] = subject["enterprise_id"]
        code, payload, _ = _request("POST", f"{BASE_URL}/api/v1/chat", body=body, token=token)
        if code != 200:
            errors.append(f"turn_{index + 1}_http={code}")
            continue
        primary = (payload.get("data") or {}).get("primary") or {}
        if primary.get("fallback") is not False:
            errors.append(f"turn_{index + 1}_fallback")
        replies.append(str(payload.get("reply") or ""))
    final = replies[-1].lower() if replies else ""
    if not any(term in final for term in ("现金流", "现金", "cash_flow")):
        errors.append("n2_cash_flow_not_resolved")
    code, history, _ = _request("GET", f"{BASE_URL}/api/v1/chat/sessions/{session_id}", token=token)
    if code != 200 or len(history.get("messages") or []) < 12:
        errors.append("history_not_persisted")
    return {"id": "M01", "category": "memory", "query": "6-turn N-2 memory", "latency_ms": 0, "ok": not errors, "errors": errors, "status": None, "route": None, "reply": replies[-1][:180] if replies else ""}


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * percentile)))
    return round(ordered[index], 2)


def run(*, base_url: str, max_workers: int) -> dict[str, Any]:
    global BASE_URL
    BASE_URL = base_url.rstrip("/")
    token = _login()
    subject = _subject(token)
    plan = build_dialogue_plan(subject)
    for index, case in enumerate(plan, 1):
        case["index"] = index
        case["id"] = f"D{index:03d}"
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = list(pool.map(lambda case: _run_case(token, case), plan))
    results.append(_run_memory_case(token, subject))
    failures = [item for item in results if not item["ok"]]
    latencies = [item["latency_ms"] for item in results if item["latency_ms"]]
    return {"stage": "12A", "total": len(results), "passed": len(results) - len(failures), "failed": len(failures), "pass_rate": round((len(results) - len(failures)) / max(len(results), 1), 4), "p50_latency_ms": _percentile(latencies, 0.50), "p95_latency_ms": _percentile(latencies, 0.95), "failures": failures, "results": results}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = run(base_url=args.base_url, max_workers=max(1, min(args.max_workers, 8)))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"stage={report['stage']} passed={report['passed']}/{report['total']} failed={report['failed']} p95={report['p95_latency_ms']}ms")
    raise SystemExit(0 if report["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
