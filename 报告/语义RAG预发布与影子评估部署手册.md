# 语义 RAG 预发布与影子评估部署手册

日期：2026-09-16  
适用范围：阶段 8 至阶段 9 前。此手册不会切换生产流量。

## 一、上线前原则

1. 主对话路径仍使用旧 `chat_router`。
2. 新语义路径默认关闭。
3. 金融模型不是必配项；未配置时跳过金融因果解读并回退主模型。
4. LangGraph、LangChain、pgvector 尚未进入当前生产依赖，不得在本阶段强行启用。
5. 所有数据库变更均为幂等增量，不删除旧表、不覆盖业务数据。

## 二、备份 PostgreSQL

在项目根目录执行：

```bash
docker compose exec db pg_dump -U risk_user -d risk_db -f /tmp/risk_backup_before_semantic.sql
docker compose cp db:/tmp/risk_backup_before_semantic.sql ./risk_backup_before_semantic.sql
```

确认备份文件存在后再继续。

## 三、部署并执行幂等迁移

```bash
docker compose up -d --build backend
docker compose exec -T backend python -m scripts.verify_semantic_readiness --apply
```

该命令会：

- 创建缺失的 Registry、Topic、Blueprint、Shadow 表。
- 为旧 `metric_definition` 表幂等补列。
- 幂等写入指标、工具、别名和阈值种子。
- 输出部署就绪报告。

期望关键字段：

```json
{
  "ok": true,
  "counts": {
    "validated_metrics": 52,
    "validated_tools": 60,
    "validated_thresholds": 14
  }
}
```

实际计数会随后续指标实现增加，但 `planned` 工具必须保持 `enabled=false`。

## 四、开启预发布影子评估

在预发布 `.env` 中设置：

```env
SHADOW_SEMANTIC_ENABLED=true
SHADOW_SEMANTIC_INDEPENDENT_ROUTE=true
SHADOW_ANSWER_EVAL_ENABLED=true
```

然后重启后端：

```bash
docker compose up -d backend
```

生产环境保持：

```env
SHADOW_SEMANTIC_ENABLED=false
```

影子钩子仅在旧路径成功返回后运行，且任何影子错误都会被吞掉，不会改变用户回答。

## 五、收集影子评估数据

先使用预发布真实流量或模拟流量运行至少 20 条，然后执行：

```bash
docker compose exec -T backend python -m scripts.shadow_evaluation_report --min-samples 20
```

当前切换门槛：

- 样本数不少于 20。
- 路由匹配率不低于 95%。
- 业务域匹配率不低于 95%。
- 平均工具覆盖率不低于 75%。
- `switch_eligible` 比例不低于 80%。

命令返回退出码 0 才表示达到阶段 9 评估门槛。退出码非 0 时不得切换流量。

## 六、金融模型配置

金融模型可选。未配置时：

- `FINANCIAL_LLM_MODEL` 为空。
- 金融因果解读层跳过。
- 主模型继续负责表达和校验。

需要启用时再配置：

```env
FINANCIAL_LLM_MODEL=
FINANCIAL_LLM_API_KEY=
FINANCIAL_LLM_BASE_URL=
```

当前 8GB 显存机器不建议部署 7B 金融模型 FP16。优先使用 API 或远程 GPU 验证。

## 七、回滚

回滚不需要删除新表。设置：

```env
SHADOW_SEMANTIC_ENABLED=false
```

重启后端即可恢复为纯旧路径。数据库新增表与新种子不会影响旧路径。

只有在数据损坏时才使用备份恢复；正常关闭影子模式不属于破坏性回滚。

## 八、阶段 9 前禁止事项

- 不切换主对话路径。
- 不让影子路径写业务结论或报告。
- 不给 `planned` 工具设置 `enabled=true`。
- 不在未通过影子门槛前把 `SHADOW_SEMANTIC_ENABLED` 开到生产。
- 不删除旧 `chat_router`、旧章节映射或兼容别名。
## 综合发布裁决

在影子样本达到数量后，必须使用综合门禁，而不是分别目测两个报告：

```bash
docker compose exec -T backend python -m scripts.deployment_gate --min-samples 20
```

只有同时满足以下条件才会输出 `decision=ready_for_canary`：

- 数据库和 Registry 就绪。
- 计划工具没有被启用。
- 影子样本数量达到要求。
- 路由、业务域、工具覆盖率和 switch-eligible 比例全部达标。

如果输出 `decision=stay_on_legacy`，必须继续使用旧路径，不得进入 canary。

## 九、Canary 演练与休眠回滚

Canary 仍然先执行旧路径；只有新语义回答状态为 `answered` 时才替换返回内容，
并且必须先成功覆盖会话历史。路由、组装、配置或历史持久化任一失败都会保留旧回答。

演练时临时设置：

```env
SHADOW_SEMANTIC_ENABLED=false
SHADOW_ANSWER_EVAL_ENABLED=false
SHADOW_SEMANTIC_INDEPENDENT_ROUTE=true
SEMANTIC_CANARY_PERCENT=100
```

重建后端并运行 HTTP 级冒烟：

```bash
docker compose up -d --build backend
STAGING_CONFIRM=true python backend/scripts/run_staging_canary_smoke.py
```

脚本会验证分析问句进入语义回答、回答与会话历史一致，并验证寒暄、能力询问、
天气、拒绝编造、脏话和多语言输入不会产生 5xx 或被 canary 替换。

演练完成后必须恢复休眠：

```env
SEMANTIC_CANARY_PERCENT=0
```

重新启动后端，并确认响应中不再出现 `data.canary`。生产灰度应从
`SEMANTIC_CANARY_PERCENT=1` 或 `5` 开始，以 `session_id` 稳定分流，先观察错误率、
回答延迟、历史一致性和回退日志，再逐级增加。

## 十、旧路径退役审计

Stage 9 已完成：旧 `route_chat`、正则软降级和 `backend/legacy` 已退役并物理删除。
当前活动入口只允许 semantic primary；内部异常受控返回 503，不得恢复旧路由兜底。
运行退役审计：

```bash
python -m scripts.audit_legacy_retirement --shadow-gate-passed
```

只有输出 `safe_to_retire=true` 且 `legacy_package_present=false` 才算通过。当前已删除
旧入口、无引用章节兼容别名和整个 `backend/legacy` 目录；章节唯一真源为
`CHAPTER_REGISTRY`，不得为了兼容旧代码重新引入第二套章节常量或旧路由模块。
