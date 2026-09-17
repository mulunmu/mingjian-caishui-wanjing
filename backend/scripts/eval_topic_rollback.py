"""Generate and execute long-conversation rollback evaluations."""
from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from dataclasses import asdict, dataclass

try:
    from scripts.eval_http import login, post_json
except ImportError:
    from backend.scripts.eval_http import login, post_json


@dataclass(frozen=True)
class RollbackSequence:
    sequence_id: str
    turns: list[str]
    expected_topic_hint: str


def build_rollback_sequences() -> list[RollbackSequence]:
    industries = ["制造", "批发零售", "服务", "建筑", "IT软件", "其他"]
    provinces = ["广东", "江苏", "山西", "浙江", "山东"]
    sequences = []
    for index in range(1, 31):
        industry = industries[(index - 1) % len(industries)]
        province = provinces[(index - 1) % len(provinces)]
        sequences.append(RollbackSequence(f"rollback-{index}", [f"{industry}行业的真实性风险怎么样？", "再看一下纳税准时率", "换成发票异常", f"回到最开始那个{industry}真实性问题继续分析"], industry))
    return sequences


async def run_evaluation(args) -> dict:
    token = login(args.base_url, args.email, args.password)
    failures = []
    passed = 0
    sequences = build_rollback_sequences()[: args.limit]
    for sequence in sequences:
        session_id = f"rollback-eval-{uuid.uuid4().hex[:10]}"
        last = {}
        try:
            for turn in sequence.turns:
                last = await asyncio.to_thread(post_json, f"{args.base_url.rstrip('/')}/api/v1/chat", {"query": turn, "session_id": session_id}, token=token)
            primary = ((last.get("data") or {}).get("primary") or {})
            reply = str(last.get("reply") or "")
            ok = bool(reply) and (sequence.expected_topic_hint in reply or sequence.expected_topic_hint in str(primary.get("analysis_focus") or {}) or primary.get("referenced_topic_id"))
            if ok:
                passed += 1
            else:
                failures.append({"sequence": asdict(sequence), "reply": reply, "primary": primary})
        except Exception as exc:
            failures.append({"sequence": asdict(sequence), "error": str(exc)})
    return {"total": len(sequences), "passed": passed, "failed": len(failures), "pass_rate": round(passed / max(1, len(sequences)), 4), "failures": failures}


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
