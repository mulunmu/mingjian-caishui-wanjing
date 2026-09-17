# 阶段 16 生产质量与 LLM 延迟闭环报告

日期：2026-09-17

候选标签：`rag-v2-stage16-accepted-20260917`

## 一、结论

阶段 16 已完成可核验闭环。核心分析回答保持 LLM 生成，不再存在固定模板兜底或直接拼接 Claim 原文的生产入口。当前生产链路同时满足：

- 两轮 105 条真实生产对话矩阵全部通过。
- P50 从阶段 16 前的约 `10.09s` 降至约 `1.22s-1.39s`。
- P95 从阶段 16 前的约 `19.19s-28.8s` 降至 `6.25s-6.59s`。
- 全量后端回归 `800 passed, 8 skipped`。
- 严格覆盖与 readiness 审计无失败项。

## 二、最终 LLM 路径

```text
DialogAct 分类
-> 单次异步 instructor + Pydantic schema
-> max_retries=0

常规回答
-> 单次异步快速模型 JSON
-> LLM_DIALOGUE_MODEL=deepseek-v4-flash

快速模型失败
-> 一次异步主模型 instructor 路径
-> LLM_MODEL=deepseek-v4-pro
-> 空结论或结构违约时，最多一次显式 schema 修复重试

最终
-> Claim 数字锚定
-> 事实闸门
-> LLM 文本输出或受控 503
```

生产主路径不返回固定模板。`reply_source=llm` 只在模型输出通过结构校验和事实闸门后产生。

## 三、本轮发现并关闭的根因

### 1. 同步模型调用阻塞事件循环

分类和通用结构化输出原先把同步 Instructor 或 LiteLLM 调用放在 `async` 函数内。现已改为异步调用，避免阻塞其他请求。

### 2. JSON 模式缺少明确 JSON 指令

主模型升级请求曾触发 `response_format=json_object` 要求 prompt 包含 `json` 的系统错误。统一异步 JSON 层现在保证系统消息包含明确 JSON 输出契约。

### 3. 空结论和空白结论被误判为有效

`conclusions=[]` 与 `["   "]` 都曾通过宽松模型并被当成成功。新增 `GeneratedClaimBundle`：

- 至少一条结论。
- 最多三条结论。
- 空白结论自动拒绝。
- 主模型路径允许一次显式 schema 修复重试。

### 4. 实体编号被误算成指标数字

“企业1”里的 `1` 曾被事实闸门当成未授权业务数字，导致整句被删除并最终 503。数字锚定现在会先排除 `企业N`、`主体N`、`ENTN` 等实体标识。

### 5. 千分位与普通数字锚定不一致

`1,477.7` 与 `1477.7` 曾被当作不同数字。数字正则与归一化现在使用同一口径，避免正常模型表达被错误拦截。

### 6. 死模板代码仍可被误接回生产

已删除旧 `_template_reply`、`_template_from_claims`、`build_advisor_reply` 及只覆盖死模板路径的参数化测试。生产模块不再保留固定回答模板入口。

## 四、验收证据

### 真实生产对话矩阵

```text
run A: 105/105, P50 1392.40ms, P95 6593.86ms
run B: 105/105, P50 1217.37ms, P95 6250.07ms
重点复测: 3 类问题 × 10 轮 = 30/30
```

重点复测问题：

```text
企业1发票数量有多少
企业1净利率怎么样
企业1欠税多不多
```

### 后端与前端

```text
backend: 800 passed, 8 skipped
frontend: npm run build passed
```

8 个 skip 均来自测试库环境缺样本，不是本轮 LLM 路径失败。

### 严格审计

```text
registry_metrics_total=101
metrics_validated=53
metrics_planned=48
metrics_executable=53
thresholds_missing_required=0
validated_missing_surface_label=0
validated_without_executor=0
chapter_gaps=0
```

readiness：

```text
ok=true
missing_tables=[]
missing_conversation_topic_columns=[]
planned_enabled_tools=[]
failures=[]
```

checkpoint 清理演练：

```text
ok=true
dry_run=true
thread_count=0
```

### 生产状态

```text
backend health=ok
database=connected
redis=connected
LANGGRAPH_OUTER_ENABLED=true
LANGGRAPH_REPORT_APPROVAL_REQUIRED=true
LLM_DIALOGUE_MODEL=deepseek-v4-flash
LLM_MODEL=deepseek-v4-pro
LLM_TIMEOUT_SECONDS=15
```

## 五、仍未完成但不能误报的事项

- Sentry SDK 已安装，但没有配置 `SENTRY_DSN`，因此没有实际事件上报。
- 金融模型仍未配置，本轮未进入每轮必经路径。
- 完整 LangChain 与 pgvector 混合检索仍属于后续阶段，不能宣称已经上线。
- 48 个 planned 指标仍不可执行、不会进入 RAG。

## 六、冻结条件

本候选版本满足以下冻结条件：

- 核心回答无固定模板兜底。
- 两轮 105 条真实生产矩阵连续全通过。
- 全量回归、前端构建、readiness 和严格覆盖审计通过。
- 回滚标签和运行手册可执行。
