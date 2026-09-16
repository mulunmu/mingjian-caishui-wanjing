"""对话范围状态机：scope / subject / scenario 一等槽位（R1–R5）。

铁律：范围不清不算全库；数字仍只来自引擎。
"""
from __future__ import annotations

import re
import time
from typing import Any

from app.services import followup_items as fu

Scope = str  # unbound | individual | cohort
Scenario = str | None  # loan | rating | warn | audit | None

SCOPES = frozenset({"unbound", "individual", "cohort"})
SCENARIOS = frozenset({"loan", "rating", "warn", "audit"})

# 需要个体主体的问法（「这家」指代 / 四场景白话）
_INDIVIDUAL_RE = re.compile(
    r"(这家|该企业|这个企业|该户|本企业|"
    r"能贷|放贷|信用怎么样|评级|"
    r"哪里不对劲|不对劲|"
    r"哪里可疑|可疑要查|该查谁|优先核查)"
)

# 明确要全库/群体
_COHORT_RE = re.compile(
    r"(全库|全样本|全部样本|193|群体|整体风险|看全部|所有企业|行业分布|哪里信号最多|"
    r"各行业|行业趋势|趋势走向|走势|分布|信号最多|群体风险)"
)

_SCENARIO_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("loan", re.compile(r"能贷|放贷|贷不贷|额度")),
    ("rating", re.compile(r"信用怎么样|评级|信用等级|打分|评分")),
    ("warn", re.compile(r"不对劲|预警|哪里不对|异常信号")),
    ("audit", re.compile(r"可疑|该查|稽查|优先核查|要查谁")),
]


def empty_dialogue_state() -> dict[str, Any]:
    return {
        "scope": "unbound",
        "subject": None,
        "scenario": None,
        "inventory_focus": None,
        "analysis_focus": None,
        "focus_history": [],  # M2 焦点栈
    }


def normalize_dialogue_state(raw: dict[str, Any] | None) -> dict[str, Any]:
    """从会话条目归一化三槽位；兼容旧 enterprise_id。"""
    raw = raw or {}
    state = empty_dialogue_state()
    if isinstance(raw.get("dialogue_state"), dict):
        raw = {**raw, **(raw.get("dialogue_state") or {})}

    scope = (raw.get("scope") or "").strip()
    subject = raw.get("subject")
    eid = None
    if isinstance(subject, dict):
        eid = (subject.get("enterprise_id") or "").strip() or None
        state["subject"] = {
            "enterprise_id": eid,
            "display_name": subject.get("display_name") or subject.get("display_label") or "演示企业",
        } if eid else None
    elif raw.get("enterprise_id"):
        eid = str(raw["enterprise_id"]).strip()
        state["subject"] = {
            "enterprise_id": eid,
            "display_name": raw.get("enterprise_label") or raw.get("display_name") or "演示企业",
        }

    if scope in SCOPES:
        state["scope"] = scope
    elif eid:
        state["scope"] = "individual"
    else:
        state["scope"] = "unbound"

    # 互斥校正
    if state["scope"] == "individual" and not state.get("subject"):
        state["scope"] = "unbound"
    if state["scope"] != "individual":
        # cohort/unbound 不挂主体（cohort 可保留 last_subject 供切回，但不作为当前 subject）
        if state["scope"] == "cohort":
            state["subject"] = None

    sc = raw.get("scenario")
    state["scenario"] = sc if sc in SCENARIOS else None
    focus = raw.get("inventory_focus")
    if isinstance(focus, dict) and (focus.get("industry_l1") or focus.get("province")):
        state["inventory_focus"] = {
            "industry_l1": focus.get("industry_l1"),
            "province": focus.get("province"),
            "ask_kind": focus.get("ask_kind"),
        }
    else:
        state["inventory_focus"] = None
    af = raw.get("analysis_focus")
    if isinstance(af, dict) and (af.get("industry_l1") or af.get("province")):
        state["analysis_focus"] = {
            "industry_l1": af.get("industry_l1"),
            "province": af.get("province"),
        }
    else:
        state["analysis_focus"] = None
    # M2：焦点栈校验
    raw_fh = raw.get("focus_history")
    if isinstance(raw_fh, list):
        valid = []
        for item in raw_fh:
            if isinstance(item, dict) and item.get("kind") and item.get("value"):
                valid.append({
                    "kind": str(item["kind"]),
                    "value": str(item["value"]),
                    "ts": float(item.get("ts") or 0),
                })
        state["focus_history"] = valid[-20:]  # 上限 20 条
    else:
        state["focus_history"] = []
    return state


def detect_scenario(query: str | None) -> Scenario:
    q = (query or "").strip()
    if not q:
        return None
    for name, pat in _SCENARIO_PATTERNS:
        if pat.search(q):
            return name
    return None


def infer_required_scope(
    query: str | None,
    followup: dict | None = None,
    *,
    current_scope: str | None = None,
) -> Scope | None:
    """该问句需要的范围；None = 不强制（FAQ/闲聊/切换）。"""
    if followup and isinstance(followup, dict):
        t = followup.get("type")
        if t in ("switch_scope", "bootstrap", "action", "navigate"):
            return None
        if t == "drilldown":
            return "cohort"
        params = followup.get("params") if isinstance(followup.get("params"), dict) else {}
        if params.get("required_scope") in SCOPES:
            return params["required_scope"]

    q = (query or "").strip()
    if not q:
        return None
    if _COHORT_RE.search(q) and not re.search(r"这家|该企业|该户", q):
        return "cohort"
    if _INDIVIDUAL_RE.search(q):
        # 已在全库视角且无「这家」指代 → 群体稽查/预警，不强制切回个体
        if current_scope == "cohort" and not re.search(r"这家|该企业|该户|本企业", q):
            return "cohort"
        return "individual"
    return None


def resolve_scope(
    query: str | None,
    state: dict[str, Any],
    *,
    followup: dict | None = None,
    required: Scope | None = None,
    scenario: Scenario = None,
    use_infer: bool = True,
) -> dict[str, Any]:
    """路由前校验。status: ok | ask_bind | confirm_switch。

    DialogAct 路径：传入 required/scenario，且仅对 analyze/drill 调用本函数。
    use_infer=False 时不走正则 infer（避免非分析句被误判）。
    """
    state = normalize_dialogue_state(state)
    current = state.get("scope") or "unbound"
    if required is None and use_infer:
        required = infer_required_scope(query, followup, current_scope=current)
    if scenario is None:
        scenario = detect_scenario(query) or state.get("scenario")
    elif scenario not in SCENARIOS:
        scenario = state.get("scenario")

    if required is None:
        return {"status": "ok", "required": None, "state": state, "scenario": scenario}

    if required == current:
        if required == "individual" and not (state.get("subject") or {}).get("enterprise_id"):
            return _ask_bind(state, scenario)
        return {"status": "ok", "required": required, "state": state, "scenario": scenario}

    if required == "individual" and current in ("unbound", "cohort"):
        return _ask_bind(state, scenario, from_cohort=(current == "cohort"))

    if required == "cohort" and current == "individual":
        name = (state.get("subject") or {}).get("display_name") or "当前企业"
        return {
            "status": "confirm_switch",
            "required": "cohort",
            "state": state,
            "scenario": scenario,
            "reply": (
                f"当前在分析「{name}」（个体）。要切到全库群体再看吗？"
                "确认后我会按全样本回答，不再用「这家」。"
            ),
            "followup_items": [
                fu.item(
                    type="switch_scope",
                    label="切到全库 193 家",
                    target="cohort",
                    params={"required_scope": "cohort"},
                ),
                fu.item(
                    type="switch_scope",
                    label=f"继续看「{name}」",
                    target="individual",
                    params={
                        "enterprise_id": (state.get("subject") or {}).get("enterprise_id"),
                        "display_name": name,
                    },
                ),
                fu.item(type="query", label="哪里可疑要查？", params={"required_scope": "individual"}),
            ],
        }

    if required == "cohort" and current == "unbound":
        new_state = switch_scope(state, target="cohort")
        return {"status": "ok", "required": "cohort", "state": new_state, "scenario": scenario, "auto_switched": True}

    return {"status": "ok", "required": required, "state": state, "scenario": scenario}


def switch_scope(
    state: dict[str, Any],
    *,
    target: str,
    subject: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = dict(state)
    if target == "unbound":
        out["scope"] = "unbound"
        out["subject"] = None
        out["scenario"] = None
    elif target == "cohort":
        out["scope"] = "cohort"
        out["subject"] = None
    elif target == "individual":
        if not subject or not subject.get("enterprise_id"):
            raise ValueError("individual 需要 subject.enterprise_id")
        out["scope"] = "individual"
        out["subject"] = {
            "enterprise_id": subject["enterprise_id"],
            "display_name": subject.get("display_name") or "演示企业",
        }
    else:
        raise ValueError(f"unknown scope target: {target}")
    return out


def _ask_bind(state: dict[str, Any], scenario: Scenario, *, from_cohort: bool = False) -> dict[str, Any]:
    prefix = (
        "当前是全库群体视角，这条问的是「某一家」。"
        if from_cohort
        else "这条问的是「某一家企业」，我还不知道要看哪家。"
    )
    return {
        "status": "ask_bind",
        "required": "individual",
        "state": state,
        "scenario": scenario,
        "reply": (
            f"{prefix}"
            "请先选一家：试用演示企业、从列表选，或改看全库群体。"
        ),
        "followup_items": unbound_entry_items(),
    }


def unbound_entry_items() -> list[dict[str, Any]]:
    """首屏 / 反问绑槽：库存协商 + 三入口（演示不是静默默认）。"""
    return [
        fu.item(
            type="dialog_act",
            label="我能分析哪些企业？",
            params={"act": "negotiate_scope", "confidence": 1.0},
        ),
        fu.item(
            type="switch_scope",
            label="试用演示企业",
            target="individual",
            params={"use_demo": True},
        ),
        fu.item(
            type="switch_scope",
            label="从列表选一家",
            target="individual",
            params={"open_picker": True},
        ),
        fu.item(
            type="switch_scope",
            label="看全库 193 家群体",
            target="cohort",
        ),
    ]


def ui_bundle(state: dict[str, Any], *, sample_count: int | None = None) -> dict[str, Any]:
    """前端纯派生：欢迎语 / chips / 范围条。"""
    state = normalize_dialogue_state(state)
    scope = state["scope"]
    subject = state.get("subject") or {}
    n = sample_count if isinstance(sample_count, int) and sample_count > 0 else 193
    name = subject.get("display_name") or "演示企业"

    if scope == "unbound":
        welcome = (
            "我是明鉴风控顾问。可以先问「能分析哪些企业」，"
            "或试用演示企业、从列表选一家、看全库群体。"
        )
        chips = unbound_entry_items()
        scope_bar = {"label": "尚未选择范围", "scope": "unbound", "hint": "请先选个体或全库"}
    elif scope == "individual":
        welcome = (
            f"当前范围：个体 · {name}。"
            "可以直接问：这家能贷吗？信用怎么样？哪里不对劲？哪里可疑要查？"
            "也可换一家或切到全库。"
        )
        chips = [
            fu.item(type="query", label="这家能贷吗？", params={"required_scope": "individual"}),
            fu.item(type="query", label="信用怎么样？", params={"required_scope": "individual"}),
            fu.item(type="query", label="哪里不对劲？", params={"required_scope": "individual"}),
            fu.item(type="query", label="哪里可疑要查？", params={"required_scope": "individual"}),
        ]
        scope_bar = {
            "label": f"个体 · {name}",
            "scope": "individual",
            "enterprise_id": subject.get("enterprise_id"),
            "display_name": name,
            "hint": "换一家 / 看全库",
        }
    else:
        welcome = (
            f"当前范围：全库群体 · {n} 家。"
            "可以问：哪里信号最多？按行业拆风险；或生成报告。"
            "若要问「这家能不能贷」，请先切到某一家企业。"
        )
        chips = [
            fu.item(type="query", label="哪里信号最多？", params={"required_scope": "cohort"}),
            fu.item(type="query", label="哪里可疑要查？", params={"required_scope": "cohort"}),
            fu.item(type="query", label="按行业拆风险等级", params={"required_scope": "cohort"}),
            fu.item(type="navigate", label="生成报告", target="report_generate"),
        ]
        scope_bar = {
            "label": f"全库 · {n} 家",
            "scope": "cohort",
            "hint": "换一家个体 / 重新选范围",
        }

    return {
        "welcome": welcome,
        "chips": chips,
        "scope_bar": scope_bar,
        "dialogue_state": state,
        "scenario_buttons": _scenario_buttons(scope),
    }


def _scenario_buttons(scope: str) -> list[dict[str, Any]]:
    if scope != "individual":
        # 全库/未绑定：场景按钮改为群体问法或先绑主体
        if scope == "cohort":
            return [
                {"id": "warn", "label": "预警", "question": "哪里信号最多？", "hint": "全库信号"},
                {"id": "audit", "label": "稽查", "question": "哪里可疑要查？", "hint": "优先核查"},
                {"id": "trend", "label": "行业", "question": "按行业拆风险等级", "hint": "行业集中"},
                {"id": "report", "label": "报告", "question": "生成报告", "hint": "出报告"},
            ]
        return [
            {"id": "demo", "label": "演示", "question": "", "hint": "试用企业", "action": "use_demo"},
            {"id": "pick", "label": "选户", "question": "", "hint": "列表选", "action": "open_picker"},
            {"id": "cohort", "label": "全库", "question": "", "hint": "193 家", "action": "use_cohort"},
            {"id": "ingest", "label": "接入", "question": "", "hint": "导入数据", "action": "ingest"},
        ]
    return [
        {"id": "loan", "label": "放贷", "question": "这家能贷吗？", "hint": "能不能贷"},
        {"id": "rating", "label": "评级", "question": "信用怎么样？", "hint": "信用等级"},
        {"id": "warn", "label": "预警", "question": "哪里不对劲？", "hint": "异常信号"},
        {"id": "audit", "label": "稽查", "question": "哪里可疑要查？", "hint": "优先核查"},
    ]


def state_public(state: dict[str, Any]) -> dict[str, Any]:
    s = normalize_dialogue_state(state)
    return {
        "scope": s["scope"],
        "subject": s.get("subject"),
        "scenario": s.get("scenario"),
        "inventory_focus": s.get("inventory_focus"),
    }

def merge_analysis_focus(
    state: dict[str, Any],
    *,
    industry_l1: str | None = None,
    province: str | None = None,
    clear: bool = False,
) -> dict[str, Any]:
    """写入/清除分析焦点（cohort 切片，供后续 analyze 继承）。"""
    state = normalize_dialogue_state(state)
    if clear:
        state["analysis_focus"] = None
        return state
    if industry_l1 or province:
        prev = state.get("analysis_focus") if isinstance(state.get("analysis_focus"), dict) else {}
        state["analysis_focus"] = {
            "industry_l1": industry_l1 if industry_l1 is not None else prev.get("industry_l1"),
            "province": province if province is not None else prev.get("province"),
        }
        # M2：焦点入栈
        history = state.get("focus_history") or []
        now = time.time()
        if industry_l1:
            history.append({"kind": "industry", "value": industry_l1, "ts": now})
        if province:
            history.append({"kind": "province", "value": province, "ts": now})
        state["focus_history"] = history[-20:]
    return state


def resolve_focus_from_history(
    state: dict[str, Any], kind: str, *, skip_current: bool = True
) -> str | None:
    """从焦点栈回溯匹配焦点。skip_current=True 时跳过栈顶同 kind（回到上一层）。"""
    matches = [
        item for item in reversed(state.get("focus_history") or [])
        if item.get("kind") == kind
    ]
    if not matches:
        return None
    if skip_current and len(matches) >= 2:
        return matches[1].get("value")
    return matches[0].get("value")

