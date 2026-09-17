"""Evaluate the optional financial review layer without letting it own facts."""
from __future__ import annotations

import argparse
import asyncio
import json
import time

from app.schemas.claim import Claim, ClaimValue
from app.services.financial_model import load_financial_model_config
from app.services.financial_model_eval import FINANCIAL_EVAL_CASES, score_financial_text
from app.services.llm_reply import generate_financial_interpretation


async def run() -> dict:
    config = load_financial_model_config()
    if not config.available:
        return {"ok": False, "skipped": True, "reason": "financial_model_unavailable", "config": config.public_dict()}

    results: list[dict] = []
    latencies: list[float] = []
    for case in FINANCIAL_EVAL_CASES:
        claim = Claim(
            claim=case.claim,
            value=ClaimValue(metric=case.metric, number=case.number, unit=""),
            confidence="computed",
        )
        started = time.perf_counter()
        text = await generate_financial_interpretation([claim])
        latency = (time.perf_counter() - started) * 1000
        latencies.append(latency)
        score = score_financial_text(case, text)
        results.append({"case_id": case.case_id, "latency_ms": round(latency, 2), **score})

    failures = [item for item in results if not item["ok"]]
    ordered = sorted(latencies)
    def percentile(ratio: float) -> float:
        if not ordered:
            return 0.0
        return round(ordered[min(len(ordered) - 1, int(round((len(ordered) - 1) * ratio)))], 2)
    pass_rate = round((len(results) - len(failures)) / max(1, len(results)), 4)
    return {
        "ok": pass_rate >= 0.80,
        "skipped": False,
        "config": config.public_dict(),
        "total": len(results),
        "passed": len(results) - len(failures),
        "failed": len(failures),
        "pass_rate": pass_rate,
        "p50_latency_ms": percentile(0.50),
        "p95_latency_ms": percentile(0.95),
        "digit_leakage": sum(1 for item in results if "digit_leakage" in item["issues"]),
        "failures": failures,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = asyncio.run(run())
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"ok={report.get('ok')} skipped={report.get('skipped')} pass_rate={report.get('pass_rate')}")
    raise SystemExit(0 if report.get("ok") else 1)


if __name__ == "__main__":
    main()
