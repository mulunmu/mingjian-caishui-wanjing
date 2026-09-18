# 阶段 23：LLM-first 迁移验收

日期：2026-09-18

分支：`release/rag-v2-canary-candidate-20260916`

基线提交：`6516b49 test: add semantic and report evaluation matrices`

## 1. 本阶段完成项

- SemanticPlan 已成为对话主链的语义决策契约，负责 action、scope、实体、指标、分析模式和工具组合方案。
- LangGraph 已接入主链，节点包括分类、语义规划、能力检索、计划校验、修复、执行、证据审查、金融复核、报告计划、响应合成和最终保护。
- 工具执行仍由异步 DAG 承担，LLM 不得直接执行工具或生成数字。
- 报告按“章节 -> Block -> 指标 -> Claim”组装，30 组章节组合全部通过。
- Topic Graph 支持跨轮引用、主题回滚和“最开始/上上个/第 N 个”等时间指代。
- 非分析语义计划现在会接管兼容 route，不再被旧 `raw_route.action` 覆盖。
- `metadata_query` 会正确处理系统级目录查询，并把行业目录上下文切换为 cohort。
- `overall_score` 执行层已尊重 `industry_l1` 维度，按行业拆分不再退化为总体雷达图。
- 计划中明确声明的 `industry_l1`、`province` 焦点会持久化到 `dialogue_state`，后续轮次和回滚可以继续使用。
- 旧语义规则已迁入 `backend/app/services/legacy_fallback.py`；迁移审计主链规则定义为 0。

## 2. 功能开关

以下开关已接入运行环境，默认保持当前已验收行为：

```text
SEMANTIC_PLANNER_ENABLED=true
SEMANTIC_PLANNER_PERCENT=100
SEMANTIC_PLAN_LANGGRAPH_NODE_ENABLED=true
SEMANTIC_REPORT_PLAN_ENABLED=true
SEMANTIC_TOPIC_RESOLVER_ENABLED=true
SEMANTIC_LEGACY_ROUTE_FALLBACK=true
```

`SEMANTIC_LEGACY_ROUTE_FALLBACK=false` 时，语义规划不可用会 fail-closed 到澄清，而不是继续走旧路由。

## 3. 最终验收证据

| 验收项 | 结果 |
| --- | --- |
| 后端全量测试 | `967 passed, 8 skipped` |
| 1108 条真实 HTTP 语义评测 | `1108/1108`，通过率 `1.0` |
| 30 组跨轮主题回滚 | `30/30`，通过率 `1.0` |
| 30 组报告章节/Block 组合 | `30/30`，通过率 `1.0` |
| 集成真实性审计 | `passed=true` |
| 意图路由审计 | `passed=true` |
| LLM-first 迁移审计 | `status=complete`，`semantic_overrides=0` |
| 前端生产构建 | `npm run build` 成功 |
| 桌面浏览器验收 | 登录、对话、行业目录、按行业拆风险、分类柱图、分析过程均正常 |

评测覆盖范围包括寒暄、能力询问、超纲、伪造请求、企业画像、单企业多指标、行业目录、地区目录、跨行业对比、报告和长对话回滚。

## 4. 回滚条件

出现以下任一情况应回退到上一候选版本：

- 答非所问率超过 2%。
- 工具不存在或执行失败超过 0.5%。
- Claim 数字缺失超过 0.5%。
- 报告重复 Block 超过 1%。
- PDF 少页、吞页或章节顺序错误。

## 5. 已知边界

- 金融复核模型当前未配置，`finance_review` 保持禁用；主链按设计跳过该节点。
- MySQL / ETL profile 未启用，启动时会出现 MySQL 探测告警；当前业务数据使用 PostgreSQL。
- 前端构建有单包超过 500 kB 的提示，不影响本轮功能验收。
- 手机端适配不属于本轮上线验收范围；桌面端已验收。
- 工作区存在历史未提交改动，本次没有为了覆盖它们而创建混合提交。迁移代码已通过当前工作区全量验证，提交前需要按业务边界拆分 staging。

## 6. 结论

本阶段要求的 LLM-first 语义主链、LangGraph 多节点编排、异步工具 DAG、长对话回滚、RAG 工具组合、报告 Block 组装、功能开关和旧规则隔离均已达到当前验收标准。

当前剩余的是工程发布动作，不是功能缺口：需要将历史未提交改动按归属拆分后，再做最终提交和候选版本冻结。
