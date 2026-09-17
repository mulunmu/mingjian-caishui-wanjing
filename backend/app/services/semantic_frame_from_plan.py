"""Build SemanticFrame from a validated SemanticPlan."""
from __future__ import annotations

from app.schemas.conversation_route import ConversationRoute
from app.schemas.semantic_frame import SemanticFrame
from app.schemas.semantic_plan import SemanticPlan
from app.services.analysis_patterns import ANALYSIS_PATTERNS


def frame_from_plan(
    plan: SemanticPlan,
    *,
    route: ConversationRoute,
    base: SemanticFrame,
) -> SemanticFrame:
    pattern_key = plan.analysis_patterns[0] if plan.analysis_patterns else "metric_lookup"
    spec = ANALYSIS_PATTERNS.get(pattern_key)
    steps = list(plan.steps)
    step_metrics = [
        step.tool_id.removeprefix("metric_")
        for step in steps
        if step.tool_id.startswith("metric_")
    ]
    metrics = step_metrics or list(plan.metrics)
    filters = dict(base.filters or {})
    filters.update(plan.filters or {})
    entities = list(plan.entities or base.entities)
    return base.model_copy(
        update={
            "policy_route": route.route,
            "task_type": spec.task_type if spec is not None else base.task_type,
            "analysis_pattern": pattern_key,
            "analysis_components": list(plan.analysis_patterns) or [pattern_key],
            "comparison_basis": plan.comparison_basis,
            "subject_scope": plan.scope,
            "entities": entities,
            "metrics": metrics,
            "filters": filters,
            "output_requirements": list(
                dict.fromkeys([*base.output_requirements, *plan.output_requirements])
            ),
            "confidence": plan.confidence,
            "missing_slots": [],
        }
    )
