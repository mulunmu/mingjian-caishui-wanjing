from __future__ import annotations

try:
    from scripts.eval_semantic_planner import build_semantic_cases
    from scripts.eval_topic_rollback import build_rollback_sequences
except ImportError:
    from backend.scripts.eval_semantic_planner import build_semantic_cases
    from backend.scripts.eval_topic_rollback import build_rollback_sequences


def test_semantic_eval_contains_at_least_two_hundred_cases():
    cases = build_semantic_cases()

    assert len(cases) >= 200
    assert len({case.case_id for case in cases}) == len(cases)
    assert all(case.query and case.expected_action for case in cases)
    assert {case.expected_action for case in cases} >= {
        "analysis",
        "metadata_query",
        "profile",
        "report",
        "conversation",
    }


def test_rollback_eval_contains_at_least_thirty_sequences():
    sequences = build_rollback_sequences()

    assert len(sequences) >= 30
    assert all(len(sequence.turns) >= 4 for sequence in sequences)
    assert all(sequence.expected_topic_hint for sequence in sequences)
