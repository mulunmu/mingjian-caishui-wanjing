"""Generate and execute report-plan evaluations."""
from __future__ import annotations

import argparse
import asyncio
import itertools
import json

from app.schemas.custom_report import CustomReportSpec
try:
    from scripts.eval_http import login, post_json
except ImportError:
    from backend.scripts.eval_http import login, post_json


def build_report_eval_specs() -> list[CustomReportSpec]:
    chapters = ["financial", "tax", "authenticity", "fraud", "signal", "trend"]
    specs = []
    for size in (4, 3, 2, 1):
        for index, combo in enumerate(itertools.combinations(chapters, size), start=1):
            if len(specs) >= 40:
                break
            specs.append(CustomReportSpec(chapters=list(combo), title=f"评测报告 {size}-{index}", purpose="验证章节和 Block 组合"))
        if len(specs) >= 40:
            break
    return specs


async def run_evaluation(args) -> dict:
    token = login(args.base_url, args.email, args.password)
    failures = []
    passed = 0
    specs = build_report_eval_specs()[: args.limit]
    for spec in specs:
        try:
            response = await asyncio.to_thread(post_json, f"{args.base_url.rstrip('/')}/api/v1/report/custom/plan", {"spec": spec.model_dump(mode="json")}, token=token)
            plan = response.get("report_plan") or {}
            plan_chapters = plan.get("chapters") or []
            ok = bool(response.get("ok")) and [chapter.get("module_key") for chapter in plan_chapters] == spec.chapters and all(chapter.get("blocks") for chapter in plan_chapters)
            if ok:
                passed += 1
            else:
                failures.append({"spec": spec.model_dump(mode="json"), "response": response})
        except Exception as exc:
            failures.append({"spec": spec.model_dump(mode="json"), "error": str(exc)})
    return {"total": len(specs), "passed": passed, "failed": len(failures), "pass_rate": round(passed / max(1, len(specs)), 4), "failures": failures}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--email", default="admin@example.com")
    parser.add_argument("--password", default="admin123")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)
    report = asyncio.run(run_evaluation(args))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        from pathlib import Path
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
