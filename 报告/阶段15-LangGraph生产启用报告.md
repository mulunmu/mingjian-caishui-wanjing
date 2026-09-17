# 阶段 15 LangGraph 生产启用报告

## 结论

LangGraph 已在生产后端启用，并实际参与对话外层编排。确定性金融执行仍在内层由 `AsyncDagRuntime` 完成。

## 生产状态

```text
langgraph_installed=true
LANGGRAPH_OUTER_ENABLED=true
LANGGRAPH_REPORT_APPROVAL_REQUIRED=true
```

当前多 Agent 图角色：

```text
memory_agent
classification_agent
planning_agent
approval_agent
execution_agent
verification_agent
```

## 内容级历史召回

用户无需记住“第几轮”。系统会对历史话题摘要、实体和过滤条件进行关键词与语义重合匹配。

实测：

```text
query=那个税负的事继续分析
referenced_topic_id=prod-content-ref-...-topic-1
topic_match_reason=税负
topic_match_score=0.3333
```

## 报告审批

报告请求会先进入 `approval_agent` 中断，用户确认后从 PostgreSQL checkpoint 恢复执行。

实测 Agent 轨迹：

```text
memory_agent
classification_agent
planning_agent
approval_agent
execution_agent
verification_agent
```

## 验证结果

```text
1296 passed, 4 skipped full backend regression
production health ok
production canary smoke ok
production approval interrupt/resume ok
production content topic recall ok
```

## 回滚

- 旧后端镜像：`20-backend-pre-langgraph-20260917`
- 紧急禁用：`LANGGRAPH_OUTER_ENABLED=false`
- 不删除 PostgreSQL checkpoint 表，保持可恢复状态
