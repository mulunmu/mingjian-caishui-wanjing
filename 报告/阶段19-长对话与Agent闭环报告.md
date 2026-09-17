# 阶段 19 长对话与 Agent 闭环报告

日期：2026-09-17

候选标签：`rag-v2-stage19-accepted-20260917`

## 一、结论

阶段 19 已完成长对话记忆、纠错、内容级回指、金融复核 Agent、最终守卫 Agent 和 Agent 时间预算闭环。核心事实仍由确定性 Claims、工具执行器和事实闸门掌握，可选 Agent 不会越权修改数字或结论。

## 二、长对话记忆

最终能力：

```text
ConversationTopic 持久化
轮次引用：N-1 / N-2 / 绝对轮次
内容引用：摘要、实体、过滤条件、场景、意图的语义匹配
纠错检测：不对 / 我说的是 / 改成 / 纠正
摘要压缩：最近优先、按摘要去重、字符上限
外层 memory Agent 结果直接传入主执行器
```

内存语义匹配使用现有 `BAAI/bge-small-zh-v1.5` FastEmbed，仅在需要话题引用时触发。匹配失败时回退到确定性 bigram 重叠，不伪造历史。

40 轮真实对话验收：

```text
total=4
passed=4
failed=0
```

覆盖：

```text
税负纠错回指
现金流跨话题内容回指
N-2 回滚
客户数量跨 38 轮内容回指
```

验收文件：

```text
报告/阶段19-40轮长对话验收.json
```

## 三、Agent 拓扑

```text
memory_agent
-> classification_agent
-> planning_agent
-> approval_agent（按需）
-> execution_agent
-> finance_review_agent（可选）
-> final_guard_agent（默认启用）
-> verification_agent
```

### finance_review_agent

- 金融模型未配置时明确记录 `skipped`，不阻塞主流程。
- 只能在已有 Claims 基础上提供金融因果解释。
- 不修改 reply，不新增数字、阈值、名单或最终风险结论。

当前生产状态：

```text
LANGGRAPH_FINANCE_REVIEW_ENABLED=false
financial_model_unavailable
```

### final_guard_agent

默认启用。拒绝：

```text
empty_reply
fallback_response
untraceable_claim
agent_budget_exceeded
```

当前预算：

```text
LANGGRAPH_AGENT_BUDGET_MS=15000
```

## 四、最终验证

后端全量回归：

```text
834 passed, 8 skipped
```

8 个 skip 仍为测试环境缺少指定样本，不属于阶段 19 功能失败。

105 条生产对话矩阵：

```text
run A: 105/105, P50 1100.15ms, P95 3970.13ms
run B: 105/105, P50 1059.46ms, P95 4344.40ms
```

其它门禁：

```text
readiness: ok=true
strict coverage: passed
hybrid retrieval: Recall@5=1.0, Recall@1=0.922078, MRR=0.958874
report block matrix: 31/31
frontend build: passed
```

## 五、配置与回滚

生产配置：

```text
MEMORY_SEMANTIC_ENABLED=true
LANGGRAPH_FINANCE_REVIEW_ENABLED=false
LANGGRAPH_FINAL_GUARD_ENABLED=true
LANGGRAPH_AGENT_BUDGET_MS=15000
```

回滚：

```text
MEMORY_SEMANTIC_ENABLED=false
```

该设置只关闭语义话题匹配，保留 bigram 引用、持久化历史、纠错和 N-2 回滚能力。

## 六、边界说明

- 金融模型仍未配置；未配置时 finance review 明确 skip，不伪造复核结果。
- 36 个指标仍因源数据缺失保持 unsupported。
- Sentry DSN 仍未配置，不能宣称已实际上报。
- 当前最终守卫是确定性的，不替代 Claims 数字锚定和业务执行器。
