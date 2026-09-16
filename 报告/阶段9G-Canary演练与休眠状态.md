# 阶段 9G：Canary 演练与休眠状态

日期：2026-09-16

## 范围

本阶段只验证 Canary 基础设施和回退边界，不切换生产流量。

```text
项目=mingjian-staging
后端=http://localhost:8000
数据库=独立脱敏 staging PostgreSQL
生产数据库=未连接
```

## 实现

- `SEMANTIC_CANARY_PERCENT` 使用 `session_id` 哈希稳定分流。
- 旧路径始终先执行；新语义路径失败时保留旧回答。
- 只有 `status=answered` 且回答非空时才允许替换。
- 会话历史必须先成功写入新回答，再替换 HTTP 返回值。
- 非法、NaN、负数或超过 100 的百分比按 0 处理。
- 异常信息只写服务日志，不向用户响应泄露内部细节。

## 专项与回归

```text
canary/session targeted tests=17 passed
full backend suite=1177 passed, 13 skipped, 0 failed
```

## 100% HTTP 演练

临时配置：

```text
SEMANTIC_CANARY_PERCENT=100
SHADOW_SEMANTIC_ENABLED=false
SHADOW_ANSWER_EVAL_ENABLED=false
SHADOW_SEMANTIC_INDEPENDENT_ROUTE=true
```

真实 HTTP 结果：

```text
cases=7
http_errors=0
analysis: canary_status=answered, reply_source=llm, history_match=true
greeting: canary_status=not_applicable, reply_present=true
capability: canary_status=not_applicable, reply_present=true
weather: canary_status=not_applicable, reply_present=true
refusal: canary_status=not_applicable, reply_present=true
abuse: canary_status=not_applicable, reply_present=true
multilingual: canary_status=not_applicable, reply_present=true
```

分析类问句已经真实进入语义执行链，并把新回答写回会话历史。非分析类问句全部
安全回退旧路径，没有 5xx，也没有 canary 替换副作用。

## 休眠验证

演练结束后恢复：

```text
SEMANTIC_CANARY_PERCENT=0
```

健康检查通过，随机分析请求结果：

```text
reply_present=true
reply_source=template
canary_present=false
```

## 已知边界

旧 `chat_router` 的天气和拒绝编造分支目前不写会话历史，因此这些消息不参与
后续回滚或跨话题记忆。该行为早于 Canary，不影响本轮语义替换安全，但应在后续
对话记忆阶段统一收口。

## 结论

Canary 激活、故障回退、历史一致性和休眠关闭均已通过真实 staging HTTP 验证。
候选版本可以进入提交冻结，生产灰度仍需从低比例开始。
