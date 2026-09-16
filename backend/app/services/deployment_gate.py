"""Combined release gate for readiness and shadow-evaluation evidence."""
from __future__ import annotations

from sqlalchemy.engine import Engine

from app.services.deployment_readiness import build_semantic_readiness_report
from app.services.shadow_answer_evaluation import build_shadow_answer_summary
from app.services.shadow_reporting import build_shadow_evaluation_summary


def build_deployment_gate(
    engine: Engine,
    *,
    min_shadow_samples: int = 20,
    min_answer_samples: int = 20,
    require_answer_eval: bool = True,
) -> dict:
    readiness = build_semantic_readiness_report(engine)
    try:
        shadow = build_shadow_evaluation_summary(
            engine,
            min_samples=min_shadow_samples,
        )
    except Exception as exc:
        shadow = {
            "ok": False,
            "samples": 0,
            "failures": [f"shadow_table_unavailable:{exc}"],
        }
    if require_answer_eval:
        try:
            answer = build_shadow_answer_summary(
                engine,
                min_samples=min_answer_samples,
            )
        except Exception as exc:
            answer = {
                "ok": False,
                "samples": 0,
                "failures": [f"answer_table_unavailable:{exc}"],
            }
    else:
        answer = {"ok": True, "samples": 0, "failures": []}

    blockers = [f"readiness:{item}" for item in readiness.get("failures", [])]
    blockers.extend(f"shadow:{item}" for item in shadow.get("failures", []))
    if require_answer_eval:
        blockers.extend(f"answer:{item}" for item in answer.get("failures", []))
    ok = (
        bool(readiness.get("ok"))
        and bool(shadow.get("ok"))
        and (not require_answer_eval or bool(answer.get("ok")))
        and not blockers
    )

    if ok:
        next_actions = [
            "freeze candidate revision",
            "run anonymized canary with explicit percentage",
            "compare canary route, latency, and hallucination guards",
            "rollback immediately on any hard-gate failure",
        ]
        decision = "ready_for_canary"
    else:
        next_actions = [
            "run scripts.verify_semantic_readiness --apply",
            "enable shadow mode in pre-release only",
            "enable shadow answer evaluation in pre-release only",
            "collect the required shadow and answer observations",
            "resolve every reported gate failure",
        ]
        decision = "stay_on_legacy"

    return {
        "ok": ok,
        "decision": decision,
        "blockers": blockers,
        "next_actions": next_actions,
        "readiness": readiness,
        "shadow": shadow,
        "answer": answer,
    }