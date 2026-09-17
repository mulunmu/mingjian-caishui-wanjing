# LLM-First 语义规划、多 Agent 与报告闭环实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把现有项目从“正则路由 + LLM 辅助 + 固定组合”迁移为“LLM 提出语义计划，确定性层验证并异步执行，报告按章节和 Block 引用 Claim 组装”的完整闭环。

**Architecture:** LLM 负责语义理解、上下文指代、动作判断、工具候选和组合方案；`SemanticPlan` 是语义真源。确定性层只负责工具存在性、真实筛选值、DAG 合法性、权限、预算、Claim 溯源和报告 Block 契约。LangGraph 负责会话级多 Agent 编排和 checkpoint，现有 AsyncDAGRuntime 负责工具并发执行。

**Tech Stack:** FastAPI、Pydantic v2、SQLAlchemy async、PostgreSQL、pgvector、Redis、LangGraph、LangChain 工具适配层、instructor/litellm、现有 Claim/Tool RAG/Composition DAG。

---

## 0. 当前基线与约束

当前分支：`release/rag-v2-canary-candidate-20260916`。

当前工作区包含大量未提交改动，执行本计划时不得回滚用户改动。

当前已验证基线：

- 容器全量测试：`910 passed, 8 skipped`。
- `行业有哪些？` 返回 `inventory`，覆盖 193 家、6 个行业。
- `企业1有哪些值得分析的点？` 进入 LLM 规划，执行 6 个模块的 `plan-semantic-*` DAG。
- `制造业和IT软件的经营真实性对比` 生成 `compare_suspicious_count` Claim。
- 已存在：`SemanticPlan`、`semantic_planner.py`、计划校验、计划到 DAG 转换、真实筛选值校验、比较基准归一。

仍然存在的问题：

- `dialog_act`、`route_normalize`、`frame_from_route` 仍参与语义判断。
- 20 路 route 仍可能覆盖 LLM 计划。
- semantic planner 当前在 `execute` 内部调用，还没有成为 LangGraph 独立 planning 节点。
- `compose_semantic_turn` 在部分路径仍取候选列表第一个工具。
- Redis 缓存不能独立承担长对话和语义回滚。
- 自定义报告仍是会话状态机和报告模板组合，尚未升级为 `ReportPlan`。

执行原则：

1. LLM 只提出方案，不产生数字、阈值、企业名单或最终事实。
2. 确定性 Validator 不重新理解自然语言，只判断方案是否可执行。
3. 无 LLM 时允许降级到旧链路；有 LLM 时禁止静默回到旧语义路由。
4. 每个里程碑必须有失败测试、实现、通过测试和全量回归。
5. 旧规则先兼容、再旁路、最后删除，不能一次性硬删。

---

## 1. 目标架构

```text
HTTP/UI
  -> LangGraph
       -> Context Agent
       -> Semantic Planner Agent
       -> Capability/RAG Agent
       -> Plan Validator Agent
       -> Repair/Clarify 或 Async DAG Executor
       -> Evidence Critic Agent
       -> Report Planner 或 Response Composer
       -> Final Guard
  -> Claim/Chart/Report 持久化
```

核心契约：

```text
SemanticPlan
- action
- scope
- entities
- filters
- metrics
- analysis_patterns
- comparison_basis
- steps
- confidence
- ambiguous
- clarification_question
- plan_summary
```

报告契约：

```text
ReportPlan
- action=report
- report_mode=fixed|custom
- subject_scope
- chapters[]
  - chapter_id
  - title
  - analysis_patterns[]
  - blocks[]
    - block_id
    - block_kind
    - metric_keys[]
    - filters
    - comparison_basis
    - claim_ids[]
    - chart_ids[]
```

---

## 2. 文件责任划分

已有文件：

- `backend/app/schemas/semantic_plan.py`：SemanticPlan、步骤和校验报告 schema。
- `backend/app/services/semantic_planner.py`：LLM 规划、计划归一化、计划到 DAG。
- `backend/app/services/semantic_primary.py`：primary 回合编排和计划接入。
- `backend/app/services/composition_execution_bridge.py`：DAG 执行和跨群体对比 Claim。
- `backend/app/services/outer_orchestrator.py`：LangGraph 外层状态机。
- `backend/app/services/topic_memory.py`：主题和 Claim 记忆。
- `backend/app/services/report_blocks.py`：报告 Block 契约和指纹。
- `backend/app/services/custom_report.py`：自定义报告状态机和生成。

计划新增文件：

- `backend/app/schemas/semantic_action.py`：精简 action 和 policy tag 契约。
- `backend/app/services/semantic_policy.py`：action -> policy/permission 映射，不再做关键词路由。
- `backend/app/services/semantic_frame_from_plan.py`：由 SemanticPlan 构造 SemanticFrame。
- `backend/app/services/semantic_nodes.py`：LangGraph 的语义规划、检索、校验、修复节点。
- `backend/app/schemas/topic_state.py`：主题图、引用解析和回滚状态。
- `backend/app/services/topic_reference_resolver.py`：LLM + 语义检索的主题指代解析。
- `backend/app/schemas/report_plan.py`：ReportPlan、ReportChapter、ReportBlock。
- `backend/app/services/report_planner.py`：LLM 报告组合规划。
- `backend/app/services/report_plan_validator.py`：报告 Block、Claim、指标和权限校验。
- `backend/app/services/report_plan_executor.py`：按 Block 执行并组装报告。
- `backend/tests/test_semantic_action_policy.py`
- `backend/tests/test_semantic_plan_v2.py`
- `backend/tests/test_llm_first_route_migration.py`
- `backend/tests/test_langgraph_semantic_nodes.py`
- `backend/tests/test_topic_reference_resolver.py`
- `backend/tests/test_report_plan.py`
- `backend/tests/test_report_plan_http.py`

---

## 3. 里程碑与任务

### Task 1: 固化当前基线并建立迁移审计

**Files:**
- Create: `backend/scripts/audit_llm_first_migration.py`
- Test: `backend/tests/test_llm_first_route_migration.py`

- [x] **Step 1: 写失败测试，固定主链中不应再出现的语义规则**

测试扫描以下文件的 AST 和字符串：

- `backend/app/services/route_normalize.py`
- `backend/app/services/semantic_frame.py`
- `backend/app/services/semantic_primary.py`

断言主链不会通过 `is_industry_distribution_query`、固定关键词 pattern 或 route 名称来决定 analysis、inventory、profile 和 report。

- [x] **Step 2: 运行测试确认失败**

Run: `docker exec 20-backend-1 python -m pytest -q tests/test_llm_first_route_migration.py`

Expected: FAIL，指出当前 `route_normalize` 和 `frame_from_route` 仍含语义规则。

- [x] **Step 3: 建立审计输出**

脚本输出 JSON：

```json
{
  "semantic_overrides": [],
  "route_derived_from_plan": true,
  "planner_in_langgraph_node": false,
  "report_plan_enabled": false
}
```

- [x] **Step 4: 运行脚本**

Run: `docker exec 20-backend-1 python scripts/audit_llm_first_migration.py`

Expected: 成功输出当前缺口，不修改业务行为。

- [x] **Step 5: Commit**

```bash
git add backend/scripts/audit_llm_first_migration.py backend/tests/test_llm_first_route_migration.py
git commit -m "test: add llm-first migration audit"
```

---

### Task 2: 定义精简 Action 与 Policy 契约

**Files:**
- Create: `backend/app/schemas/semantic_action.py`
- Create: `backend/app/services/semantic_policy.py`
- Test: `backend/tests/test_semantic_action_policy.py`

- [x] **Step 1: 写失败测试**

覆盖以下 action：

```python
from app.schemas.semantic_action import SemanticAction

assert SemanticAction.ANALYSIS.value == "analysis"
assert SemanticAction.METADATA_QUERY.value == "metadata_query"
assert SemanticAction.PROFILE.value == "profile"
assert SemanticAction.REPORT.value == "report"
assert SemanticAction.CONVERSATION.value == "conversation"
assert SemanticAction.CLARIFY.value == "clarify"
assert SemanticAction.REFUSE.value == "refuse"
```

测试 policy 只根据 action、safety、permission、tool availability 决定行为，不读取 query 关键词。

- [x] **Step 2: 运行测试确认失败**

Run: `docker exec 20-backend-1 python -m pytest -q tests/test_semantic_action_policy.py`

Expected: FAIL with `ModuleNotFoundError: app.schemas.semantic_action`。

- [x] **Step 3: 实现 Action**

```python
from enum import Enum


class SemanticAction(str, Enum):
    ANALYSIS = "analysis"
    METADATA_QUERY = "metadata_query"
    PROFILE = "profile"
    REPORT = "report"
    CONVERSATION = "conversation"
    CLARIFY = "clarify"
    REFUSE = "refuse"
```

- [x] **Step 4: 实现 Policy Resolver**

`semantic_policy.resolve_policy(action, *, safety, permissions, tools_available)` 返回：

```python
{
    "execute_tools": bool,
    "retrieve_knowledge": bool,
    "allow_report": bool,
    "requires_confirmation": bool,
    "response_mode": str,
}
```

- [x] **Step 5: 运行测试并通过**

Run: `docker exec 20-backend-1 python -m pytest -q tests/test_semantic_action_policy.py`

Expected: PASS。

- [x] **Step 6: Commit**

```bash
git add backend/app/schemas/semantic_action.py backend/app/services/semantic_policy.py backend/tests/test_semantic_action_policy.py
git commit -m "feat: add semantic action policy contract"
```

---

### Task 3: 扩展 SemanticPlan V2

**Files:**
- Modify: `backend/app/schemas/semantic_plan.py`
- Modify: `backend/app/services/semantic_planner.py`
- Test: `backend/tests/test_semantic_plan_v2.py`

- [x] **Step 1: 写失败测试**

测试 SemanticPlan 必须支持：

- `action` 使用 `SemanticAction`
- `route_hint` 只作兼容标签
- `planner_version`
- `policy_tags`
- `requires_confirmation`
- `resolved_references`
- `report_plan`
- `plan_summary`
- `ambiguity_reason`
- `repair_history`

断言 `route_hint` 不参与工具选择。

- [x] **Step 2: 运行测试确认失败**

Run: `docker exec 20-backend-1 python -m pytest -q tests/test_semantic_plan_v2.py`

Expected: FAIL，缺少新字段。

- [x] **Step 3: 扩展 schema**

新增字段默认值，保持旧数据可反序列化。`action` 改为 `SemanticAction`，但通过 `field_validator` 兼容旧字符串。

- [x] **Step 4: 更新规划提示词**

Planner 必须要求：

- 只能从真实 action 中选择。
- `route_hint` 只填兼容标签。
- 不确定时填 `ambiguous=true` 和 `clarification_question`。
- 任何步骤只能来自真实工具目录。

- [x] **Step 5: 运行测试和既有 planner 测试**

Run: `docker exec 20-backend-1 python -m pytest -q tests/test_semantic_plan_v2.py tests/test_semantic_planner.py`

Expected: PASS。

- [x] **Step 6: Commit**

```bash
git add backend/app/schemas/semantic_plan.py backend/app/services/semantic_planner.py backend/tests/test_semantic_plan_v2.py
git commit -m "feat: extend semantic plan contract"
```

---

### Task 4: 把 Semantic Planner 提升为 LangGraph 独立节点

**Files:**
- Modify: `backend/app/services/outer_orchestrator.py`
- Create: `backend/app/services/semantic_nodes.py`
- Test: `backend/tests/test_langgraph_semantic_nodes.py`
- Test: `backend/tests/test_semantic_primary.py`

- [x] **Step 1: 写失败测试**

构造 LangGraph state，断言顺序为：

```text
memory -> semantic_planner -> capability_retrieval -> plan_validator -> execute
```

断言 `semantic_plan`、`composition_plan`、`planner_errors` 都在 state 中传递。

- [x] **Step 2: 运行测试确认失败**

Run: `docker exec 20-backend-1 python -m pytest -q tests/test_langgraph_semantic_nodes.py`

Expected: FAIL，当前 planner 仍藏在 execute 内部。

- [x] **Step 3: 扩展 OuterTurnState**

增加：

```python
semantic_plan: dict[str, Any]
composition_plan: dict[str, Any]
planner_errors: list[str]
planner_attempts: int
policy_decision: dict[str, Any]
```

- [x] **Step 4: 新增 `semantic_planner_node`**

节点调用 `plan_semantic_turn`，只负责产生计划和错误，不执行工具。

- [x] **Step 5: 新增 `capability_retrieval_node` 和 `plan_validation_node`**

检索节点返回候选工具、真实行业和地区值。校验节点调用 `validate_semantic_plan`，合法进入执行，不合法进入 repair 或 clarify。

- [x] **Step 6: 从 `run_primary_turn` 移除 planner 调用**

`run_primary_turn` 只接收已验证的 `semantic_plan` 和 `composition_plan`，不再自行决定 planner eligibility。

- [x] **Step 7: 运行测试**

Run: `docker exec 20-backend-1 python -m pytest -q tests/test_langgraph_semantic_nodes.py tests/test_semantic_primary.py tests/test_outer_orchestrator.py`

Expected: PASS。

- [x] **Step 8: Commit**

```bash
git add backend/app/services/outer_orchestrator.py backend/app/services/semantic_nodes.py backend/app/services/semantic_primary.py backend/tests/test_langgraph_semantic_nodes.py
git commit -m "refactor: move semantic planning into langgraph node"
```

---

### Task 5: 退役 route_normalize 的语义决策权

**Files:**
- Modify: `backend/app/services/route_normalize.py`
- Modify: `backend/app/services/shadow_integration.py`
- Test: `backend/tests/test_route_normalization.py`

- [ ] **Step 1: 写失败测试**

覆盖：

- `action=metadata_query` 不因“行业”变成 `analysis`。
- `action=report` 不因“定制”变成 `custom_report` 路由。
- `action=analysis` 只表示允许执行分析，不指定指标或模式。
- `route_hint` 冲突时记录 telemetry，不覆盖 plan action。

- [ ] **Step 2: 运行测试确认失败**

Run: `docker exec 20-backend-1 python -m pytest -q tests/test_route_normalization.py`

Expected: FAIL，当前仍有 `_REPORT_REQUEST_RE` 和 `is_industry_distribution_query` 覆盖。

- [ ] **Step 3: 删除 route_normalize 中的语义覆盖**

仅保留：

- 实体编号规整。
- 安全等级。
- action 与 route_hint 的兼容映射。
- 缺失槽位标记。

- [ ] **Step 4: 兼容旧 API**

旧 route 名称继续出现在响应中，但由 `action + plan` 派生。前端不因迁移立即改动。

- [ ] **Step 5: 运行测试**

Run: `docker exec 20-backend-1 python -m pytest -q tests/test_route_normalization.py tests/test_shadow_integration.py tests/test_conversation_policy.py`

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/route_normalize.py backend/app/services/shadow_integration.py backend/tests/test_route_normalization.py
git commit -m "refactor: remove semantic routing overrides"
```

---

### Task 6: 用 Plan 构造 SemanticFrame

**Files:**
- Create: `backend/app/services/semantic_frame_from_plan.py`
- Modify: `backend/app/services/semantic_primary.py`
- Modify: `backend/app/services/semantic_frame.py`
- Test: `backend/tests/test_semantic_frame_integration.py`

- [ ] **Step 1: 写失败测试**

测试 `frame_from_plan(plan)` 的 metrics、analysis_pattern、subject_scope、filters、comparison_basis 全部来自 plan。

- [ ] **Step 2: 运行测试确认失败**

Run: `docker exec 20-backend-1 python -m pytest -q tests/test_semantic_frame_integration.py`

Expected: FAIL，当前主路径仍调用 `frame_from_route`。

- [ ] **Step 3: 实现 frame_from_plan**

只做结构映射和枚举校正，不读取 query 关键词。

- [ ] **Step 4: 主路径切换**

`semantic_primary` 使用 `frame_from_plan`。`frame_from_route` 只保留给无 LLM 降级链路。

- [ ] **Step 5: 运行回归**

Run: `docker exec 20-backend-1 python -m pytest -q tests/test_semantic_frame_integration.py tests/test_semantic_primary.py tests/test_dynamic_composition.py`

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/semantic_frame_from_plan.py backend/app/services/semantic_primary.py backend/app/services/semantic_frame.py backend/tests/test_semantic_frame_integration.py
git commit -m "refactor: build frames from semantic plans"
```

---

### Task 7: 建立完整多 Agent 图

**Files:**
- Modify: `backend/app/services/outer_orchestrator.py`
- Modify: `backend/app/services/semantic_nodes.py`
- Test: `backend/tests/test_langgraph_semantic_nodes.py`

- [ ] **Step 1: 写节点级测试**

节点：

```text
context_agent
semantic_planner_agent
capability_retriever_agent
plan_validator_agent
plan_repair_agent
executor_agent
evidence_critic_agent
report_planner_agent
response_composer_agent
final_guard_agent
```

覆盖合法计划、可修复计划、不可修复计划、报告计划和闲聊计划。

- [ ] **Step 2: 实现状态和条件边**

条件边：

```text
validator -> execute       # valid
validator -> repair        # repairable
validator -> clarify       # ambiguous
validator -> refuse        # unsafe or fabricated
execute -> report_planner  # report action
execute -> evidence_critic # analysis/conversation action
```

- [ ] **Step 3: 加入 checkpoint**

使用 PostgreSQL checkpointer，Redis 只做短期缓存。每次 plan、validation、execution 和 final result 都写入 checkpoint。

- [ ] **Step 4: 加入预算和并发**

规划、修复、校验串行；RAG、工具 DAG 节点并发。所有节点有超时、重试和取消。

- [ ] **Step 5: 运行测试**

Run: `docker exec 20-backend-1 python -m pytest -q tests/test_langgraph_semantic_nodes.py tests/test_async_dag_runtime.py tests/test_composition_execution_bridge.py`

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/outer_orchestrator.py backend/app/services/semantic_nodes.py backend/tests/test_langgraph_semantic_nodes.py
git commit -m "feat: add llm-first multi-agent graph"
```

---

### Task 8: 长对话主题图和语义回滚

**Files:**
- Create: `backend/app/schemas/topic_state.py`
- Create: `backend/app/services/topic_reference_resolver.py`
- Modify: `backend/app/services/topic_memory.py`
- Modify: `backend/app/services/semantic_turn_persistence.py`
- Test: `backend/tests/test_topic_reference_resolver.py`

- [ ] **Step 1: 写失败测试**

覆盖：

- 间隔 10 轮后问“回到上上个问题”。
- 问“刚才广东那个对比继续”。
- 问“企业3的，不是企业1”。
- 模糊引用同时匹配多个 topic 时返回澄清。

- [ ] **Step 2: 实现 TopicState**

字段：

```text
topic_id
parent_topic_id
summary
action
entities
filters
metrics
analysis_patterns
claim_ids
chart_ids
report_ids
created_at
status
```

- [ ] **Step 3: 实现两阶段解析**

先由确定性检索缩小候选，再由 LLM 在候选中选择 topic。LLM 不能发明 topic_id。

- [ ] **Step 4: 实现回滚语义**

回滚生成新的 branch state，引用旧 topic 的实体、filters、plan 和 Claim。不得删除原历史，也不得仅按消息索引倒回。

- [ ] **Step 5: 运行测试**

Run: `docker exec 20-backend-1 python -m pytest -q tests/test_topic_reference_resolver.py tests/test_topic_memory.py tests/test_long_conversation_memory_http.py`

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/topic_state.py backend/app/services/topic_reference_resolver.py backend/app/services/topic_memory.py backend/app/services/semantic_turn_persistence.py backend/tests/test_topic_reference_resolver.py
git commit -m "feat: add semantic topic rollback"
```

---

### Task 9: 补齐 Tool RAG、指标阈值和组合算子

**Files:**
- Modify: `backend/app/services/tool_rag.py`
- Modify: `backend/app/services/hybrid_tool_rag.py`
- Modify: `backend/app/services/composition_catalog.py`
- Modify: `backend/app/services/composition_execution_bridge.py`
- Modify: `backend/app/services/semantic_tool_executors.py`
- Test: `backend/tests/test_semantic_planner.py`
- Test: `backend/tests/test_composition_execution_bridge.py`

- [ ] **Step 1: 写失败测试**

覆盖：

- 同一指标和不同群体生成 `compare_*` Claim。
- 同指标不同时间生成趋势 Claim。
- 不同指标组合生成结构、贡献、归因 Claim。
- LLM 选择不存在工具时拒绝。
- LLM 选择未验证工具时拒绝。

- [ ] **Step 2: 补齐可执行算子**

优先实现：

```text
operator_compare_industry
operator_compare_province
operator_compare_peer
operator_trend
operator_change_rate
operator_proportion
operator_anomaly
operator_rank
operator_root_cause
operator_summary
```

- [ ] **Step 3: 统一算子输入输出**

每个算子声明输入 port、输出 port、数据来源和对应 Claim metric 前缀。Validator 用同一份 ModuleSpec 校验。

- [ ] **Step 4: 运行测试**

Run: `docker exec 20-backend-1 python -m pytest -q tests/test_semantic_planner.py tests/test_composition_execution_bridge.py tests/test_dynamic_composition.py tests/test_composition_validator.py`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/tool_rag.py backend/app/services/hybrid_tool_rag.py backend/app/services/composition_catalog.py backend/app/services/composition_execution_bridge.py backend/app/services/semantic_tool_executors.py backend/tests/test_semantic_planner.py backend/tests/test_composition_execution_bridge.py
git commit -m "feat: expand semantic composition operators"
```

---

### Task 10: 实现 ReportPlan

**Files:**
- Create: `backend/app/schemas/report_plan.py`
- Create: `backend/app/services/report_planner.py`
- Create: `backend/app/services/report_plan_validator.py`
- Create: `backend/app/services/report_plan_executor.py`
- Modify: `backend/app/services/report_blocks.py`
- Modify: `backend/app/services/custom_report.py`
- Modify: `backend/app/services/slice_report.py`
- Test: `backend/tests/test_report_plan.py`
- Test: `backend/tests/test_report_plan_http.py`

- [ ] **Step 1: 写失败测试**

覆盖：

- 用户说“财务总览、税务风险、真实性对比和趋势”。
- LLM 生成章节和 Block 计划。
- 每个 Block 必须绑定真实 metric、filters 和 Claim。
- 不可执行 Block 返回澄清。
- 生成 PDF 时章节顺序与 ReportPlan 一致。
- 封面 page 1 不被预览吞掉。
- 判断段不出现“回答：回答”和重复结论。

- [ ] **Step 2: 实现 ReportPlan schema**

ReportPlan、ReportChapter、ReportBlock 均使用稳定 ID，支持 fingerprint 去重和 Claim 引用。

- [ ] **Step 3: 实现 ReportPlanner**

输入：用户报告描述、SemanticPlan、可用指标、阈值、章节、Block kind、历史 Claim。

输出：结构化 ReportPlan，不给最终散文。

- [ ] **Step 4: 实现 ReportPlanValidator**

校验：

- metric 存在。
- filter 值真实。
- block_kind 与 chapter 兼容。
- claim/chart 引用存在。
- 章节没有空 Block。

- [ ] **Step 5: 实现 ReportPlanExecutor**

逐 Block 生成事实段落和图表，再组装章节。LLM 只改写 Claim，不创造数字。

- [ ] **Step 6: 接入自定义报告工作台**

工作台逐步展示章节和 Block，允许用户添加、删除、替换分析方式。每次修改都经过同一 Validator。

- [ ] **Step 7: 运行测试**

Run: `docker exec 20-backend-1 python -m pytest -q tests/test_report_plan.py tests/test_report_plan_http.py tests/test_custom_report.py tests/test_report_blocks.py tests/test_stage14_report_block_matrix.py`

Expected: PASS。

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/report_plan.py backend/app/services/report_planner.py backend/app/services/report_plan_validator.py backend/app/services/report_plan_executor.py backend/app/services/report_blocks.py backend/app/services/custom_report.py backend/app/services/slice_report.py backend/tests/test_report_plan.py backend/tests/test_report_plan_http.py
git commit -m "feat: add llm report plan and block assembly"
```

---

### Task 11: 前端过程可视化和兼容层

**Files:**
- Modify: `src/components/chat/ProcessTimeline.tsx`
- Modify: `src/components/chat/AIMessage.tsx`
- Modify: `src/stores/chatStore.ts`
- Modify: `src/types/chat.ts`
- Test: `src` build and browser smoke.

- [ ] **Step 1: 写前端契约失败测试或类型检查**

前端必须能渲染：

- `semantic_plan_summary`
- `semantic_composition_tool_ids`
- `semantic_planner_status`
- `semantic_planner_errors`
- `report_plan_id`

- [ ] **Step 2: 更新类型和 store**

这些字段作为 API 结果的一部分传递，不硬编码在本地组件文案中。

- [ ] **Step 3: 更新 ProcessTimeline**

显示真实节点：理解、规划、检索、校验、执行、对比、报告组装、最终校验。禁止显示模型隐藏推理。

- [ ] **Step 4: 运行前端构建**

Run: `npm run build`

Expected: 构建成功。

- [ ] **Step 5: 浏览器验收**

验证：

- 规划摘要出现。
- 候选工具数量出现。
- 报告生成时出现章节和 Block 进度。
- 清空对话不会触发旧 bootstrap 文案。
- 企业列表显示行业和地区。

- [ ] **Step 6: Commit**

```bash
git add src/components/chat/ProcessTimeline.tsx src/components/chat/AIMessage.tsx src/stores/chatStore.ts src/types/chat.ts
git commit -m "feat: expose llm plan progress in chat ui"
```

---

### Task 12: 建立离线评测和回归矩阵

**Files:**
- Create: `backend/scripts/eval_semantic_planner.py`
- Create: `backend/scripts/eval_topic_rollback.py`
- Create: `backend/scripts/eval_report_plan.py`
- Test: `backend/tests/test_semantic_planner_eval.py`
- Test: `backend/tests/test_report_plan_eval.py`

- [ ] **Step 1: 建立 200 条语义规划集**

分类：

```text
40 条分析意图
30 条目录和画像
30 条多轮指代和回滚
30 条对比、趋势、排名、分布
20 条系统功能、寒暄、脏话、天气和其他公司
20 条报告和自定义报告
30 条边界、歧义、伪造和权限
```

- [ ] **Step 2: 定义验收指标**

```text
answer_relevance >= 0.98
tool_id_validity = 1.00
filter_value_validity = 1.00
claim_traceability = 1.00
clarify_on_unknown >= 0.98
topic_rollback_accuracy >= 0.98
report_block_coverage >= 0.98
```

- [ ] **Step 3: 执行评测**

Run: `docker exec 20-backend-1 python scripts/eval_semantic_planner.py --base-url http://127.0.0.1:8000`

Expected: 输出 JSON 和失败案例，不产生补丁式白名单。

- [ ] **Step 4: 回归失败根因**

每个失败必须归类为：

- planner prompt/contract 问题。
- tool catalog/executor 问题。
- validator 问题。
- memory/checkpoint 问题。
- report contract 问题。

同类问题统一修，不写单句正则。

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/eval_semantic_planner.py backend/scripts/eval_topic_rollback.py backend/scripts/eval_report_plan.py backend/tests/test_semantic_planner_eval.py backend/tests/test_report_plan_eval.py
git commit -m "test: add semantic and report evaluation matrices"
```

---

### Task 13: 灰度、回滚和旧链路退役

**Files:**
- Modify: `docker-compose.yml`
- Modify: `backend/app/services/rollout.py`
- Modify: `backend/app/services/outer_orchestrator.py`
- Create: `报告/阶段23-LLM-first迁移验收.md`

- [ ] **Step 1: 功能开关拆分**

```text
SEMANTIC_PLANNER_ENABLED
SEMANTIC_PLANNER_PERCENT
SEMANTIC_PLAN_LANGGRAPH_NODE_ENABLED
SEMANTIC_REPORT_PLAN_ENABLED
SEMANTIC_TOPIC_RESOLVER_ENABLED
SEMANTIC_LEGACY_ROUTE_FALLBACK
```

- [ ] **Step 2: 灰度顺序**

```text
5% -> 25% -> 50% -> 100%
```

每档至少跑：

- 全量 pytest。
- 200 条语义评测。
- 30 条多轮回滚。
- 30 条报告生成。
- PDF 封面、判断段、章节和 Block 检查。

- [ ] **Step 3: 回滚条件**

出现任一情况立即回退：

- 答非所问率超过 2%。
- 工具不存在或执行失败超过 0.5%。
- Claim 数字缺失超过 0.5%。
- 报告重复 Block 超过 1%。
- PDF 少页、吞页或章节顺序错误。

- [ ] **Step 4: 删除旧语义规则**

只有在 100% 灰度和评测通过后，删除：

- `dialog_act` 主链关键词意图。
- `route_normalize` 语义覆盖。
- `frame_from_route` 主链调用。
- `_PATTERN_CANDIDATE_PRIORITY` 主链优先级。

保留无 LLM 降级代码，放在明确命名的 `legacy_fallback` 模块。

- [ ] **Step 5: 最终审计**

Run:

```bash
docker exec 20-backend-1 python -m pytest -q
docker exec 20-backend-1 python scripts/eval_semantic_planner.py --base-url http://127.0.0.1:8000
docker exec 20-backend-1 python scripts/eval_topic_rollback.py --base-url http://127.0.0.1:8000
docker exec 20-backend-1 python scripts/eval_report_plan.py --base-url http://127.0.0.1:8000
```

Expected: 全部通过，输出验收报告和回滚记录。

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml backend/app/services/rollout.py backend/app/services/outer_orchestrator.py 报告/阶段23-LLM-first迁移验收.md
git commit -m "chore: complete llm-first rollout and retire legacy semantic routing"
```

---

## 4. 依赖顺序

必须按以下顺序执行：

```text
Task 1
  -> Task 2
  -> Task 3
  -> Task 4
  -> Task 5
  -> Task 6
  -> Task 7
  -> Task 8
  -> Task 9
  -> Task 10
  -> Task 11
  -> Task 12
  -> Task 13
```

Task 9 和 Task 10 的部分开发可以并行，但必须在 Task 7 的 LangGraph state 稳定后合并。

## 5. 完成标准

只有同时满足以下条件才算完成：

- 主链语义决策来自 SemanticPlan，不来自关键词。
- LangGraph 中 planning、validation、execution、report 都有独立节点和 checkpoint。
- 长对话可以按语义引用和回滚到过去的 topic。
- 自定义报告由 ReportPlan 的章节和 Block 组装。
- 所有数字来自 Claim，所有 Claim 可追溯。
- 旧规则只在 LLM 不可用时降级。
- 全量测试、语义评测、报告评测和浏览器验收全部通过。
- 没有为单个失败语句新增特例正则。
