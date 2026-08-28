# 企业风险评估系统 — 后续升级方案

> 本文档罗列系统从 Demo/MVP 走向生产可用的 **8 大升级方向**，每项包含：目标、现状缺口、具体任务、涉及文件、验收标准与优先级。  
> 架构与代码定位请参阅 [`PROJECT_GUIDE.md`](./PROJECT_GUIDE.md)。

**文档版本：** 2026-07-06  
**适用基线：** 综合评分约 79/100（B+），pytest 81 项 / vitest 34 项通过

---

## 目录

1. [升级总览与优先级](#1-升级总览与优先级)
2. [方向一：数据接入与 ETL（P0）](#2-方向一数据接入与-etlp0)
3. [方向二：评分与风控引擎深化（P1）](#3-方向二评分与风控引擎深化p1)
4. [方向三：智能研判 Chat 升级（P1–P2）](#4-方向三智能研判-chat-升级p1p2)
5. [方向四：报告与文档输出（P1–P2）](#5-方向四报告与文档输出p1p2)
6. [方向五：网络图谱与关联分析（P2–P3）](#6-方向五网络图谱与关联分析p2p3)
7. [方向六：预警与通知闭环（P1）](#7-方向六预警与通知闭环p1)
8. [方向七：集成与开放能力（P2–P3）](#8-方向七集成与开放能力p2p3)
9. [方向八：前端新模块与体验（P2–P3）](#9-方向八前端新模块与体验p2p3)
10. [分阶段实施路线图](#10-分阶段实施路线图)
11. [典型端到端升级示例](#11-典型端到端升级示例)
12. [依赖关系与风险](#12-依赖关系与风险)
13. [附录：待修复项（Quick Wins）](#13-附录待修复项quick-wins)

---

## 1. 升级总览与优先级

### 1.1 当前能力边界

| 已具备 | 尚未具备 |
|--------|----------|
| 五维评分引擎（单时点） | 真实税务/工商数据 ETL |
| 8 类 Chat 意图 + LLM | 评分历史与趋势分析 |
| PDF 报告生成 + 邮件 | 预警订阅与工单闭环 |
| 发票网络可视化 | 网络风险传导分析 |
| JWT 登录注册 | RBAC / API Key / SSO |
| mock → live 三层模式切换 | Alembic 迁移跑通 |
| 进程内会话/限流/缓存 | Redis 生产级持久化 |

### 1.2 优先级矩阵

| 优先级 | 方向 | 理由 | 预估工期 |
|--------|------|------|----------|
| **P0** | 数据接入与 ETL | 一切下游功能的前提 | 2–4 周 |
| **P1** | 预警与通知闭环 | 已有 email + warnings API，改动小、价值高 | 1–2 周 |
| **P1** | 报告输出完善 | Reports 预览接 live、批量生成 | 3–5 天 |
| **P1** | 评分引擎深化 | 历史趋势、行业权重 | 1–2 周 |
| **P2** | Chat 升级 | 新意图、Tool Use、任务流 | 2–3 周 |
| **P2** | 集成与开放 | RBAC、API Key | 2 周 |
| **P2** | 前端新模块 | 预警中心、批量任务 | 1–2 周/模块 |
| **P3** | 网络关联分析 | 图算法、产业链穿透 | 2–4 周 |

### 1.3 升级原则

1. **先 live 后增强** — 无真实数据时，下游功能都是「演示级」
2. **复用现有骨架** — `dataSource.ts`、`assessment.py`、`intent_engine.py` 是扩展锚点
3. **mock 不删** — 新功能需同时支持 `mock` / `mock_with_llm` / `live` 三模式
4. **Hub 交互约束** — 扩展 UI 时勿改 `HubPlanetOrb.tsx` 粒子参数；底部导航仅调 `MiniNavOrb.tsx`

---

## 2. 方向一：数据接入与 ETL（P0）

### 2.1 目标

将系统从「模拟数据演示」升级为「真实税务/工商/发票数据驱动」，使 Dashboard、Chat、报告、网络图全链路进入 `live` 模式。

### 2.2 现状缺口

- 无独立 ETL 管道；`seed_data.py` 仅生成合成数据
- Alembic 迁移目录存在但未跑通初始 revision
- `reference/taxDataAdapter.ts` 为参考实现，未接入运行时
- `mock_data.py` 与 `seed_data.py` 对 ENT001–010 评分不一致
- `/health` 返回 `database: disconnected` 时全系统降级 mock

### 2.3 升级任务清单

#### 任务 1.1：数据库迁移体系

| 项 | 内容 |
|----|------|
| **新建/修改** | `backend/migrations/versions/001_initial.py` |
| **参考** | `backend/app/models/core_metrics.py`、`backend/migrations/env.py` |
| **步骤** | 1. `alembic revision --autogenerate` 生成初始迁移<br>2. CI 加 `alembic upgrade head` 冒烟<br>3. Docker 启动时自动 migrate |
| **验收** | 空库 `alembic upgrade head` 后表结构与模型一致 |

#### 任务 1.2：原始数据适配层

| 项 | 内容 |
|----|------|
| **新建** | `backend/app/etl/adapters/tax_csv.py`、`public_finance.py`、`legal_events.py` |
| **参考** | `reference/taxDataAdapter.ts` 字段映射逻辑 |
| **输入** | CSV / JSON / 外部 API 响应 |
| **输出** | 对齐 `CoreMetrics` + `LegalEvent` 的字典或 ORM 对象 |
| **验收** | 单元测试：给定样例行 → 输出字段与模型一致 |

#### 任务 1.3：ETL 编排与入库

| 项 | 内容 |
|----|------|
| **新建** | `backend/app/etl/pipeline.py`、`backend/app/jobs/sync_metrics.py` |
| **模式** | 全量（首次）+ 增量（按 `updated_at` / 企业 ID） |
| **调度** | 开发：CLI `python -m app.jobs.sync_metrics`；生产：APScheduler / Celery Beat |
| **验收** | 跑完 pipeline 后 `/health` 返回 `mode: live`，企业数 > 0 |

#### 任务 1.4：发票边数据入库

| 项 | 内容 |
|----|------|
| **现状** | 静态 `backend/app/data/invoice_edges.json` |
| **新建** | 表 `invoice_edges(from_id, to_id, amount, invoice_count, period)` |
| **修改** | `backend/app/api/v1/network.py` — 优先查库，JSON 作 fallback |
| **前端** | `NetworkGraph.tsx` 的 `loadRealEdges()` 无需大改 |
| **验收** | live 模式下边数据来自 DB，mock 模式仍可用 JSON |

#### 任务 1.5：mock/seed 数据对齐

| 项 | 内容 |
|----|------|
| **修改** | `backend/app/services/mock_data.py` — ENT001–010 评分与 seed 一致 |
| **修改** | `frontend/src/lib/mockEnterprises.ts` — 同步前端 mock |
| **验收** | 同一企业在 mock 与 live 模式下五维分一致（live 有数据时） |

#### 任务 1.6：数据质量与监控

| 项 | 内容 |
|----|------|
| **新建** | `backend/app/etl/validators.py` |
| **能力** | 必填字段检查、数值范围、重复企业 ID、入库前后计数 |
| **暴露** | `GET /api/v1/admin/etl-status`（需鉴权） |
| **前端** | 可选「数据管理」页展示最近同步状态 |

### 2.4 涉及文件索引

```
backend/
├── app/
│   ├── etl/                    # 【新建】适配器 + pipeline
│   ├── jobs/                   # 【新建】定时同步
│   ├── models/core_metrics.py  # 【已有】目标 Schema
│   ├── api/v1/network.py       # 【改】边数据查库
│   └── services/mock_data.py   # 【改】对齐 seed
├── migrations/versions/        # 【新建】Alembic revision
├── seed_data.py                # 【参考】合成数据模板
└── reference/taxDataAdapter.ts # 【参考】字段映射

frontend/
└── src/lib/dataSource.ts       # 【已有】live 模式自动探测，一般无需改
```

### 2.5 验收标准（方向一整体）

- [ ] Docker Compose 一键启动后 DB 连通且 `/health` 为 `live`
- [ ] 至少 1 条真实/准真实数据源通过 ETL 入库
- [ ] 前端 MockDataBanner 在 live 下不显示
- [ ] pytest 新增 ETL 相关测试 ≥ 10 项

---

## 3. 方向二：评分与风控引擎深化（P1）

### 3.1 目标

在现有五维评分基础上，支持 **历史趋势、行业差异化、可配置规则、批量评估**，使评分从「快照」变为「可追踪的风控信号」。

### 3.2 现状

- 核心引擎：`backend/app/services/assessment.py`
- 权重配置：`backend/app/services/assessment_weights.py`（固定 25/25/20/15/15）
- 法律维度：`backend/app/services/legal_service.py`
- 评估结果 **无历史表**，每次请求重算（有进程内缓存）

### 3.3 升级任务清单

#### 任务 2.1：评分历史表

| 项 | 内容 |
|----|------|
| **新建表** | `assessment_history(id, enterprise_id, total_score, dimensions_json, computed_at)` |
| **修改** | `assessment.py` — 算分后异步写入 history |
| **新 API** | `GET /enterprise/{id}/score-history?days=90` |
| **前端** | `EnterpriseDetail.tsx` 增加「评分趋势」折线图（ECharts） |
| **验收** | 同一企业多次 sync 后可查历史曲线 |

#### 任务 2.2：行业差异化权重

| 项 | 内容 |
|----|------|
| **修改** | `assessment_weights.py` — 按 `industry_l1` 返回不同 `DIMENSION_WEIGHTS` |
| **示例** | 金融业提高 `finance` 权重；制造业提高 `authenticity` |
| **配置化** | 可选 YAML `backend/app/config/industry_weights.yaml` |
| **验收** | 同行业企业对比时分位逻辑不变；跨行业权重可解释 |

#### 任务 2.3：可配置规则引擎

| 项 | 内容 |
|----|------|
| **新建** | `backend/app/services/rule_engine.py` |
| **规则示例** | `tax_arrears_cnt >= 3 → severity=high`；`revenue_deviation > 0.3 → flag=authenticity_risk` |
| **存储** | JSON/YAML 规则文件或 DB 表 `risk_rules` |
| **集成** | `assessment.py` 算分后过规则层，输出 `flags[]` |
| **前端** | 企业详情展示规则触发明细 |
| **验收** | 修改规则文件后重启即生效，无需改 Python 代码 |

#### 任务 2.4：新评估维度（可选）

| 维度 key | 中文 | 数据来源 | 改动 |
|----------|------|----------|------|
| `supply_chain` | 供应链风险 | 发票网络中心度 | assessment + NetworkGraph |
| `esg` | ESG 合规 | 外部 API / 手工录入 | 新表 + 新权重 |
| `controller_risk` | 实控人关联 | 工商图谱 | graph_service 扩展 |

> 新增维度需同步改：`assessment_weights.py`、`EnterpriseRadarChart.tsx`、`intent_engine.py` 雷达 indicators、`chat_router._radar_chart`

#### 任务 2.5：批量评估 API

| 项 | 内容 |
|----|------|
| **新 API** | `POST /risk/batch-assess` — body: `{ enterprise_ids[], industry?, province? }` |
| **返回** | 任务 ID + 进度；或同步返回（<100 家） |
| **缓存** | 接入 `cache_service.py`（见 Quick Wins） |
| **验收** | 100 家企业批量评估 < 30s（有 DB 索引） |

#### 任务 2.6：归因与解释增强

| 项 | 内容 |
|----|------|
| **现状** | `assessment.py` 已有维度分项与 attribution |
| **增强** | 每项 attribution 增加「建议动作」字段（如「建议核查发票」） |
| **Chat** | `chat_router.py` 回复中引用 attribution |
| **验收** | 详情页与 Chat 展示的扣分原因一致 |

### 3.4 涉及文件

```
backend/app/services/assessment.py          # 主引擎
backend/app/services/assessment_weights.py  # 权重
backend/app/services/legal_service.py       # 法律维度
backend/app/services/rule_engine.py         # 【新建】
backend/app/api/v1/enterprise.py            # 新 history 端点
backend/app/api/v1/risk.py                  # batch-assess
frontend/src/pages/EnterpriseDetail.tsx     # 趋势图
frontend/src/components/EnterpriseRadarChart.tsx
```

---

## 4. 方向三：智能研判 Chat 升级（P1–P2）

### 4.1 目标

将 Chat 从「问答展示」升级为「 **可执行的操作入口** 」，支持新意图、工具调用、多步任务流与审计。

### 4.2 现状

| 组件 | 路径 |
|------|------|
| 意图识别 | `backend/app/services/intent_engine.py`（8 类 + general） |
| 路由执行 | `backend/app/services/chat_router.py` |
| LLM 回复 | `backend/app/services/llm_reply.py` |
| 会话存储 | `backend/app/services/session_store.py`（内存 30min TTL） |
| 前端 | `frontend/src/pages/ChatPanel.tsx` |
| 离线兜底 | `frontend/src/lib/mockChat.ts` |

### 4.3 升级任务清单

#### 任务 3.1：扩展意图类型

| 新意图 | 触发示例 | 下游动作 |
|--------|----------|----------|
| `alert_subscribe` | 「订阅深圳明达的风险预警」 | 写 `alert_subscriptions` 表 |
| `export_data` | 「导出 ENT001 指标 Excel」 | 生成 CSV/XLSX 返回下载链接 |
| `score_history` | 「最近三个月评分变化」 | 调 score-history API + 折线图 |
| `network_query` | 「这家公司的交易对手有哪些」 | 调 invoice-edges 过滤 |
| `batch_report` | 「给预警列表企业都生成报告」 | 异步 batch 任务 |

**改动：** `intent_engine.py`（VALID_INTENTS + INTENT_RULES + TEST_CASES）→ `chat_router.py` 分支 → 前端 `ChatInlineChart.tsx` 新 chart type

#### 任务 3.2：LLM Tool Use（Function Calling）

| 项 | 内容 |
|----|------|
| **修改** | `llm_reply.py` — 定义 tools：`get_enterprise`、`list_warnings`、`generate_report` |
| **流程** | 意图模糊时 LLM 自选 tool → chat_router 执行 → 结果回填 LLM 组织语言 |
| **依赖** | LiteLLM 支持 function calling 的模型 |
| **验收** | 「帮我查一下有风险的企业然后对比前两家」多步完成 |

#### 任务 3.3：多轮任务状态机

| 项 | 内容 |
|----|------|
| **修改** | `session_store.py` — 增加 `pending_action`、`context_entities` |
| **场景** | 用户：「生成报告」→ 系统：「请确认企业名」→ 用户：「明达」→ 执行 |
| **前端** | `ChatPanel.tsx` 展示确认按钮（可选） |
| **验收** | 代词「它」「这家」正确继承上一轮企业 |

#### 任务 3.4：Chat 审计日志

| 项 | 内容 |
|----|------|
| **新建表** | `chat_audit_log(id, user_id, session_id, query, intent, enterprise_ids, created_at)` |
| **修改** | `chat.py` — 每次请求写日志 |
| **新 API** | `GET /admin/chat-logs`（管理员） |
| **验收** | 可追溯谁在何时问了什么 |

#### 任务 3.5：会话持久化

| 项 | 内容 |
|----|------|
| **现状** | `session_store.py` 进程内存，重启丢失 |
| **升级** | Redis 存储（复用 `cache_service.py` 的 REDIS_URL） |
| **验收** | 后端重启后会话上下文仍可续聊 |

#### 任务 3.6：前端 Chat 体验

| 项 | 内容 |
|----|------|
| 快捷指令面板 | `ChatPanel.tsx` — 常用问题 chip |
| 流式输出 | SSE / WebSocket 逐字显示 LLM 回复 |
| 文件下载卡片 | 导出/报告类回复展示下载按钮 |
| 历史会话列表 | 侧边栏展示近期 session |

### 4.4 涉及文件

```
backend/app/services/intent_engine.py
backend/app/services/chat_router.py
backend/app/services/llm_reply.py
backend/app/services/session_store.py
backend/app/api/v1/chat.py
frontend/src/pages/ChatPanel.tsx
frontend/src/components/ChatInlineChart.tsx
frontend/src/lib/mockChat.ts              # 同步新意图离线规则
```

---

## 5. 方向四：报告与文档输出（P1–P2）

### 5.1 目标

完善 PDF 报告体系，支持 **多模板、批量生成、多格式导出**，并修复 Reports 页 live 预览缺口。

### 5.2 现状

| 组件 | 路径 |
|------|------|
| PDF 生成 | `backend/app/services/report_generator.py` |
| HTML 模板 | `backend/app/templates/report.html` |
| API | `backend/app/api/v1/report.py` |
| 邮件 | `backend/app/services/email_service.py` |
| 前端 | `frontend/src/pages/Reports.tsx`、`EnterpriseDetail.tsx` |
| **缺口** | Reports 预览仍部分依赖 `getMockEnterprise`，未调 `/enterprise/:id` |

### 5.3 升级任务清单

#### 任务 4.1：Reports 预览接 live API（Quick Win）

| 项 | 内容 |
|----|------|
| **修改** | `Reports.tsx` — 预览区调 `api.getEnterprise(id)` |
| **fallback** | live 失败时再用 mock |
| **验收** | live 模式下预览雷达图与详情页一致 |

#### 任务 4.2：多报告模板

| 模板 | 说明 | 文件 |
|------|------|------|
| `report_full.html` | 现有完整版 | 改名现有模板 |
| `report_summary.html` | 高管摘要（1 页） | 新建 |
| `report_regulatory.html` | 监管报送格式 | 新建 |

**API：** `POST /report/generate` 增加 `template: full|summary|regulatory`

#### 任务 4.3：批量报告生成

| 项 | 内容 |
|----|------|
| **新 API** | `POST /report/batch-generate` — `{ enterprise_ids[], template }` |
| **实现** | 后台队列逐份生成，返回 `{ job_id, status_url }` |
| **前端** | Reports 页或新「批量任务」页展示进度 |
| **验收** | 50 份报告异步生成，可轮询状态 |

#### 任务 4.4：多格式导出

| 格式 | 技术方案 |
|------|----------|
| PDF | 现有 WeasyPrint / fpdf2 |
| Excel | `openpyxl` — 指标明细 sheet |
| Word | `python-docx` — 简版报告 |
| JSON | 直接序列化 assessment 结果 |

**新 API：** `GET /enterprise/{id}/export?format=xlsx|docx|json`

#### 任务 4.5：报告存储与生命周期

| 项 | 内容 |
|----|------|
| **现状** | PDF 存本地目录，列表扫描文件 |
| **升级** | 表 `reports(id, enterprise_id, path, template, created_by, expires_at)` |
| **策略** | 90 天自动清理或归档 S3/OSS |
| **验收** | 列表 API 不依赖文件系统 scan |

#### 任务 4.6：定时报告推送

| 项 | 内容 |
|----|------|
| **新建** | `backend/app/jobs/weekly_digest.py` |
| **内容** | 行业风险周报 PDF + 邮件群发 |
| **配置** | 环境变量或 DB 订阅表 |
| **依赖** | 方向六预警订阅 |

### 5.4 涉及文件

```
backend/app/services/report_generator.py
backend/app/templates/report*.html
backend/app/api/v1/report.py
backend/app/services/email_service.py
frontend/src/pages/Reports.tsx
frontend/src/pages/EnterpriseDetail.tsx
frontend/src/lib/api.ts
```

---

## 6. 方向五：网络图谱与关联分析（P2–P3）

### 6.1 目标

从「发票关系可视化」升级为「 **风险传导、团伙识别、产业链穿透** 」分析能力。

### 6.2 现状

> ⚠️ 原「单企业交易图谱 / 关联分析」已整体下线（隐私红线：企业名/税号/法人/地址均不可得，UI 禁止定位单一企业）。
> `/network/invoice-edges`、`/graph/path`、`/graph/key-companies` 等路由已移除（返回 404，见 `test_removed_enterprise_routes`）。
> 涉及单企业的风险传导 / 团伙识别（任务 5.2/5.3）同样受此红线约束，需改为行业级聚合（去单企业）方可实现。
> 隐私安全替代：**行业级产业链图谱**，数据源已备于 `reference/chain_knowledge_graph.py`（ChainKnowledgeGraph：行业→产品上下游，无单企业 PII）。

| 组件 | 路径 | 状态 |
|------|------|------|
| 前端图谱 | `frontend/src/pages/NetworkGraph.tsx`（~1900 行 Canvas） | 已下线 |
| 边数据 API | `backend/app/api/v1/network.py` | 已下线 |
| 静态数据 | `backend/app/data/invoice_edges.json` | 已下线 |
| 产业链 | `backend/app/services/graph_service.py` + `api/v1/graph.py` | 已下线（行业级图谱可复用其思路） |

### 6.3 升级任务清单

#### 任务 5.1：边数据动态化

见 [方向一 任务 1.4](#任务-14发票边数据入库)

#### 任务 5.2：风险传导分析

| 项 | 内容 |
|----|------|
| **新建** | `backend/app/services/network_risk.py` |
| **算法** | 上游企业 score < 阈值 → 下游关联企业风险 +N |
| **新 API** | `GET /network/risk-propagate?enterprise_id=` |
| **前端** | NetworkGraph 高亮传导路径、红色边 |
| **验收** | 选中高风险节点可展示受影响下游列表 |

#### 任务 5.3：团伙/环路检测

| 项 | 内容 |
|----|------|
| **算法** | NetworkX `simple_cycles`、连通分量、度中心性 |
| **新 API** | `GET /network/clusters`、`GET /network/suspicious-cycles` |
| **前端** | 新筛选器「可疑循环开票」 |
| **验收** | 种子数据中能检出预设的循环结构 |

#### 任务 5.4：产业链 UI 整合

| 项 | 内容 |
|----|------|
| **已有 API** | `GET /graph/path`、`GET /graph/key-companies` |
| **前端** | NetworkGraph 增加 Tab「产业链路径」 |
| **联动** | 点击企业 → 展示 `graph_service` 返回的上下游行业 |
| **验收** | ENT001 可展示「专用设备 → … → 国民经济」路径 |

#### 任务 5.5：子图导出与报告

| 项 | 内容 |
|----|------|
| **前端** | 已有 PNG 导出，增加「导出子图 JSON」 |
| **报告** | 新模板 `report_network.html` — 嵌入子图快照 + 风险摘要 |
| **Chat** | 意图 `network_query` 返回子图 + 解读 |

#### 任务 5.6：大图性能

| 项 | 内容 |
|----|------|
| **问题** | 2000+ 边时 Canvas 帧率下降 |
| **方案** | 按 viewport 裁剪、LOD 聚合、Web Worker 布局 |
| **文件** | `NetworkGraph.tsx` 分模块重构（layout / render / interaction） |

### 6.4 涉及文件

```
backend/app/services/network_risk.py       # 【新建】
backend/app/services/graph_service.py
backend/app/api/v1/network.py
backend/app/api/v1/graph.py
frontend/src/pages/NetworkGraph.tsx
frontend/src/lib/api.ts
```

---

## 7. 方向六：预警与通知闭环（P1）

### 7.1 目标

将 `/risk/warnings` 从静态列表升级为 **可订阅、可分级、可处理** 的预警闭环，并打通邮件/Webhook 触达。

### 7.2 现状

- 预警 API：`backend/app/api/v1/risk.py` → `assessment.list_warnings()`
- 邮件：`email_service.py`（已支持报告附件，可复用）
- Dashboard：`Dashboard.tsx` 展示预警数量，无处理流程

### 7.3 升级任务清单

#### 任务 6.1：预警数据模型

| 项 | 内容 |
|----|------|
| **新建表** | `alerts(id, enterprise_id, rule_id, severity, message, status, created_at, resolved_at)` |
| **状态** | `open` / `acknowledged` / `resolved` / `dismissed` |
| **severity** | `critical` / `high` / `medium` / `low` |
| **生成** | 规则引擎（方向二 任务 2.3）触发时写入 |

#### 任务 6.2：订阅规则

| 项 | 内容 |
|----|------|
| **新建表** | `alert_subscriptions(user_id, enterprise_id?, industry?, min_severity, channel)` |
| **channel** | `email` / `webhook` / `in_app` |
| **新 API** | `POST /alerts/subscribe`、`DELETE /alerts/subscribe/{id}` |
| **Chat** | 意图 `alert_subscribe` 写入订阅 |
| **验收** | 企业评分下降触发邮件（需配置 EMAIL_*） |

#### 任务 6.3：预警中心页面

| 项 | 内容 |
|----|------|
| **新建** | `frontend/src/pages/AlertCenter.tsx` |
| **路由** | `/alerts` — 注册到 `App.tsx`、`solarModules.ts`（可选 Hub 第 6 轨道） |
| **功能** | 筛选 severity、批量 ack、跳转企业详情 |
| **验收** | 与 Dashboard 预警数一致 |

#### 任务 6.4：Webhook 推送

| 项 | 内容 |
|----|------|
| **新建** | `backend/app/services/webhook_service.py` |
| **新 API** | `POST /admin/webhooks` 配置 URL + secret |
| **payload** | `{ event: "alert.created", enterprise_id, severity, message }` |
| **验收** | 本地 webhook.site 可收到 POST |

#### 任务 6.5：工单流转（可选，P3）

| 项 | 内容 |
|----|------|
| **新建** | `cases` 模块 — 预警 → 指派分析师 → 处理备注 → 关闭 |
| **表** | `cases(id, alert_id, assignee_id, status, notes)` |
| **前端** | 预警详情页「创建工单」 |

### 7.4 涉及文件

```
backend/app/api/v1/risk.py                 # 扩展
backend/app/api/v1/alerts.py               # 【新建】
backend/app/services/alert_service.py      # 【新建】
backend/app/services/email_service.py      # 复用
backend/app/services/webhook_service.py    # 【新建】
frontend/src/pages/AlertCenter.tsx         # 【新建】
frontend/src/pages/Dashboard.tsx           # 跳转预警中心
```

---

## 8. 方向七：集成与开放能力（P2–P3）

### 8.1 目标

从单机 Demo 升级为可被 **其他系统调用、可按角色授权** 的风控中台。

### 8.2 现状

- 认证：`auth_service.py` + JWT
- 可选鉴权：`AUTH_REQUIRED=true` 时 `deps.get_current_user_optional`
- 无角色、无 API Key、无 SSO

### 8.3 升级任务清单

#### 任务 7.1：RBAC 角色权限

| 角色 | 权限 |
|------|------|
| `admin` | 全部 + 用户管理 + ETL 状态 |
| `analyst` | 查企业、Chat、生成报告 |
| `viewer` | 只读列表与详情 |
| `api_client` | 仅 API Key 访问 |

**改动：** 用户表加 `role`；`deps.py` 加 `require_role("analyst")` 装饰器

#### 任务 7.2：API Key 鉴权

| 项 | 内容 |
|----|------|
| **新建表** | `api_keys(id, user_id, key_hash, name, expires_at, scopes[])` |
| **Header** | `X-API-Key: xxx` |
| **新 API** | `POST /admin/api-keys` 生成、`DELETE` 吊销 |
| **验收** | 第三方 curl 可调 `/enterprise/list` |

#### 任务 7.3：SSO / OAuth2

| 项 | 内容 |
|----|------|
| **方案** | 企业微信、钉钉、Azure AD — FastAPI OAuth2 callback |
| **修改** | `auth.py` 增加 `/auth/oauth/{provider}` |
| **前端** | Login 页增加「企业登录」按钮 |

#### 任务 7.4：数据范围权限

| 项 | 内容 |
|----|------|
| **场景** | 某分析师只能看「广东省」企业 |
| **实现** | 用户表 `data_scope: { provinces[], industries[] }` |
| **修改** | `enterprise.py` list 接口加 scope filter |

#### 任务 7.5：OpenAPI 与 SDK

| 项 | 内容 |
|----|------|
| **已有** | `/docs` Swagger UI |
| **增强** | 导出 OpenAPI JSON → 生成 Python/TS client |
| **发布** | `packages/risk-assessment-sdk/`（可选 monorepo） |

#### 任务 7.6：Redis 生产化

| 项 | 内容 |
|----|------|
| **已有** | `cache_service.py` 支持 REDIS_URL，**未接入 assessment** |
| **接入点** | assessment 结果缓存、session_store、rate_limiter 共享 Redis |
| **docker-compose** | 增加 `redis` 服务 |

### 8.4 涉及文件

```
backend/app/services/auth_service.py
backend/app/api/deps.py
backend/app/api/v1/auth.py
backend/app/services/cache_service.py
backend/app/services/session_store.py
backend/app/services/rate_limiter.py
docker-compose.yml                         # 加 redis
```

---

## 9. 方向八：前端新模块与体验（P2–P3）

### 9.1 目标

在 Hub 五模块基础上扩展 **预警中心、批量任务、数据管理、审计日志** 等，并提升整体 UX。

### 9.2 新模块接入标准流程

每增加一个 Hub 模块，按以下顺序改动：

```
1. frontend/src/lib/solarModules.ts     — 模块元数据（id、label、route、color、orbitIndex）
2. frontend/src/lib/routes.ts           — 路由常量 ROUTES.xxx
3. frontend/src/App.tsx                 — <Route path=... element=... />
4. frontend/src/pages/Xxx.tsx           — 页面主体
5. frontend/src/lib/api.ts              — API 封装（如需）
6. backend/app/api/v1/xxx.py            — 后端端点（如需）
7. backend/app/main.py                  — router.include_router
8. frontend/src/components/nav/SolarNav.tsx — Hub 轨道自动读取 SOLAR_MODULES，一般无需改
```

> **约束：** 勿修改 `HubPlanetOrb.tsx` 粒子参数；底部 mini 导航样式仅改 `MiniNavOrb.tsx`。

### 9.3 可新增模块一览

| 模块 | 路由 | 页面 | 后端 | 优先级 |
|------|------|------|------|--------|
| 预警中心 | `/alerts` | `AlertCenter.tsx` | `/alerts/*` | P1 |
| 批量任务 | `/batch` | `BatchJobs.tsx` | `/jobs/*` | P2 |
| 数据管理 | `/admin/data` | `DataAdmin.tsx` | `/admin/etl-status` | P0 配套 |
| 审计日志 | `/admin/audit` | `AuditLog.tsx` | `/admin/chat-logs` | P2 |
| PK 实验室 | `/pk` | `EnterprisePK.tsx` | 已有 `/enterprise/pk` | P2 |
| 系统设置 | `/settings` | `Settings.tsx` | 用户/API Key 管理 | P3 |

### 9.4 升级任务清单

#### 任务 8.1：预警中心（见方向六 任务 6.3）

#### 任务 8.2：批量任务页

| 项 | 内容 |
|----|------|
| **功能** | 上传企业 ID 列表（CSV）→ 批量评估 / 批量报告 |
| **新建** | `frontend/src/pages/BatchJobs.tsx` |
| **API** | 复用 `POST /risk/batch-assess`、`POST /report/batch-generate` |
| **UX** | 进度条 + 失败重试 + 结果下载 |
| **验收** | 上传 20 家企业 CSV，一键生成报告 ZIP |

#### 任务 8.3：数据管理页

| 项 | 内容 |
|----|------|
| **功能** | 展示 ETL 最近同步时间、入库条数、错误日志 |
| **新建** | `frontend/src/pages/DataAdmin.tsx` |
| **权限** | 仅 `admin` 角色可见 |
| **验收** | 手动触发 sync 按钮（调 admin API） |

#### 任务 8.4：全局 UX 提升

| 项 | 内容 | 文件 |
|----|------|------|
| 统一空态/错误态 | 已有 `StateViews`，各页补齐 | 各 `pages/*.tsx` |
| 响应式适配 | 移动端 Hub / Dashboard 布局 | `Hub.tsx`、`Dashboard.tsx` |
| 键盘无障碍 | Tab 聚焦、Esc 关闭弹窗 | `SolarNav.tsx`、`ChatPanel.tsx` |
| 国际化预留 | 文案抽离 `lib/i18n/zh.ts` | 全 frontend |
| 性能 | 路由级 lazy load | `App.tsx` React.lazy |

#### 任务 8.5：Hub 第六轨道（可选）

| 项 | 内容 |
|----|------|
| **场景** | 预警中心作为 Hub 常驻模块 |
| **修改** | `solarModules.ts` 增加第 6 项； label「预警中心」 |
| **注意** | 轨道数增加需调 `SolarNav.tsx` 的 `computeHubOrbitLayout` 间距 |
| **验收** | 6 模块公转无重叠、标签可读 |

### 9.5 涉及文件

```
frontend/src/lib/solarModules.ts
frontend/src/lib/routes.ts
frontend/src/App.tsx
frontend/src/pages/                    # 各新页面
frontend/src/components/nav/SolarNav.tsx
frontend/src/components/nav/MiniNavOrb.tsx
frontend/src/components/MockDataBanner.tsx
frontend/src/lib/dataSource.ts
```

---

## 10. 分阶段实施路线图

### Phase 1 — 数据可用（约 3–4 周）

**目标：** 系统进入稳定 `live` 模式，修复已知缺口。

| 周次 | 任务 | 方向 |
|------|------|------|
| W1 | Alembic 初始迁移 + Docker 自动 migrate | 一.1.1 |
| W1 | mock/seed 数据对齐 | 一.1.5 |
| W2 | ETL 适配器 + pipeline（至少 1 数据源） | 一.1.2–1.3 |
| W2 | 发票边入库 + network API 改查库 | 一.1.4 |
| W3 | Reports 预览接 live API | 四.4.1 |
| W3 | cache_service 接入 assessment | 八.7.6 / 附录 |
| W4 | ETL 状态 API + 数据管理页（简版） | 一.1.6、八.8.3 |
| W4 | 全量回归测试 + `/health` live 验收 | — |

**Phase 1 里程碑：** `/health` → `live`，MockDataBanner 消失，200 企业全链路可查。

---

### Phase 2 — 风控闭环（约 3–4 周）

**目标：** 评分可追踪、预警可触达、报告可批量。

| 周次 | 任务 | 方向 |
|------|------|------|
| W5 | 评分历史表 + 趋势 API + 详情页折线图 | 二.2.1 |
| W5 | 规则引擎 v1（5 条硬编码规则） | 二.2.3 |
| W6 | alerts 表 + alert_service + 预警 API | 六.6.1 |
| W6 | 预警中心页面 + Dashboard 跳转 | 六.6.3 |
| W7 | 邮件订阅 + Chat 意图 alert_subscribe | 六.6.2、三.3.1 |
| W7 | 多报告模板（summary 版） | 四.4.2 |
| W8 | 批量报告 generate + BatchJobs 页 | 四.4.3、八.8.2 |
| W8 | 行业差异化权重 | 二.2.2 |

**Phase 2 里程碑：** 企业评分下降 → 自动预警 → 邮件通知 → 一键批量出报告。

---

### Phase 3 — 智能与开放（约 4–6 周）

**目标：** Chat 可执行、网络可分析、系统可集成。

| 周次 | 任务 | 方向 |
|------|------|------|
| W9–10 | Chat 新意图（export/history/network） | 三.3.1 |
| W10 | LLM Tool Use v1 | 三.3.2 |
| W11 | 会话 Redis 持久化 + Chat 审计 | 三.3.4–3.5 |
| W11 | 网络风险传导 API + UI 高亮 | 五.5.2 |
| W12 | 产业链 Tab 整合 graph API | 五.5.4 |
| W13 | RBAC + API Key | 七.7.1–7.2 |
| W14 | Webhook 推送 + Redis docker-compose | 六.6 at 6.4、七.7.6 |
| W15–16 | 团伙检测 / NetworkGraph 性能优化（按需） | 五.5.3、5.6 |

**Phase 3 里程碑：** 第三方系统可通过 API Key 拉取评估；Chat 完成「查预警 → 对比 → 出报告 → 发邮件」多步任务。

---

## 11. 典型端到端升级示例

### 示例 A：「评分下降自动邮件预警」

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────────┐
│ ETL 定时同步 │ → │ assessment   │ → │ rule_engine │ → │ alert_service│
│ sync_metrics │    │ 写 history   │    │ 触发规则    │    │ 写 alerts 表 │
└─────────────┘    └──────────────┘    └─────────────┘    └──────┬───────┘
                                                                    │
                    ┌───────────────────────────────────────────────┘
                    ▼
           ┌────────────────┐    ┌─────────────────┐
           │ 查 subscriptions│ → │ email_service   │
           │ 匹配 user+企业   │    │ 发送预警邮件    │
           └────────────────┘    └─────────────────┘
                    │
                    ▼
           ┌────────────────┐
           │ AlertCenter.tsx │  用户登录后可查看并 ack
           └────────────────┘
```

**涉及方向：** 一 → 二 → 六 → 八

---

### 示例 B：「Chat 一句话完成 PK + 报告 + 邮件」

```
用户：「对比深圳明达和杭州绿源，把报告发我邮箱」
  ↓
intent_engine → enterprise_pk（解析两家企业）
  ↓
chat_router → assessment 并行查两家 → 柱状图
  ↓
（多轮 task state）→ 确认邮箱
  ↓
report_generator → PDF
  ↓
email_service → 附件发送
  ↓
ChatPanel 展示「已发送」+ 下载链接
```

**涉及方向：** 三（Tool Use + 任务流）→ 四 → 已有 email

---

### 示例 C：「发票网络发现循环开票团伙」

```
ETL 导入 invoice_edges
  ↓
network_risk.detect_cycles()
  ↓
rule_engine：循环 ≥ 3 节点 → severity=high
  ↓
NetworkGraph 筛选「可疑循环」高亮
  ↓
Chat 意图 network_query：「有哪些可疑循环」
  ↓
可选：report_network.html 导出子图报告
```

**涉及方向：** 一 → 五 → 二 → 三 → 四

---

## 12. 依赖关系与风险

### 12.1 方向间依赖图

```
                    ┌──────────────┐
                    │ 方向一：ETL  │  ← P0 基础
                    └──────┬───────┘
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌────────────┐  ┌────────────┐  ┌────────────┐
    │ 方向二：评分│  │ 方向五：网络│  │ 方向四：报告│
    └──────┬─────┘  └────────────┘  └────────────┘
           │
           ▼
    ┌────────────┐
    │ 方向六：预警│
    └──────┬─────┘
           │
     ┌─────┴─────┐
     ▼           ▼
┌─────────┐ ┌─────────┐
│ 方向三  │ │ 方向八  │
│ Chat    │ │ 新模块  │
└────┬────┘ └─────────┘
     │
     ▼
┌─────────────┐
│ 方向七：集成 │
└─────────────┘
```

### 12.2 主要风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 真实数据源对接延迟 | Phase 1 阻塞 | 先用 seed_data 跑通 ETL pipeline，再换真实源 |
| LLM 成本与稳定性 | Chat Tool Use 体验差 | 规则层优先；LLM 仅兜底；保留 mockChat |
| NetworkGraph 重构引入回归 | 网络页不可用 | 分模块提取 + 快照测试 + 保留 mock edges |
| 进程内状态丢失 | 会话/限流/用户重启清空 | Phase 3 前接入 Redis |
| Hub 轨道增加导致布局破坏 | UI 回归 | 只加 mini 导航入口，Hub 轨道扩展需 UI 评审 |
| 鉴权收紧破坏 Demo | 本地开发不便 | `AUTH_REQUIRED` 默认 false，生产才开启 |

### 12.3 技术选型建议

| 需求 | 推荐方案 | 备注 |
|------|----------|------|
| 定时任务 | APScheduler（轻量）或 Celery（重） | 初期 APScheduler 足够 |
| 任务队列 | Redis + RQ 或 Celery Beat | 与 cache_service 共用 Redis |
| 对象存储 | 本地目录 → MinIO/S3 | 报告量大时再迁 |
| 消息通知 | 邮件（已有）→ 钉钉/企微 Webhook | webhook_service 抽象 channel |
| 图计算 | NetworkX（已有 graph_service） | 大图可考虑 igraph |

---

## 13. 附录：待修复项（Quick Wins）

以下为 **低成本、高收益** 的改进，建议在 Phase 1 并行完成：

| # | 项 | 文件 | 预估 |
|---|-----|------|------|
| Q1 | Reports 预览接 live API | `Reports.tsx` | 0.5 天 |
| Q2 | mock_data 与 seed 评分对齐 | `mock_data.py`、`mockEnterprises.ts` | 0.5 天 |
| Q3 | cache_service 接入 assessment 缓存 | `assessment.py`、`cache_service.py` | 1 天 |
| Q4 | Alembic 初始 revision | `migrations/versions/` | 1 天 |
| Q5 | Chat session_id 前后端同步（已部分完成，需持久化） | `session_store.py` | 1 天 |
| Q6 | `/health` 返回更细粒度组件状态 | `main.py` | 0.5 天 |
| Q7 | EnterpriseDetail 邮件发送错误提示优化 | `EnterpriseDetail.tsx` | 0.5 天 |
| Q8 | CI 增加 `alembic upgrade head` 冒烟 | `.github/workflows/ci.yml` | 0.5 天 |

---

## 14. 文档维护说明

| 变更类型 | 需同步更新的章节 |
|----------|------------------|
| 新增 API 端点 | 对应方向「涉及文件」+ [`PROJECT_GUIDE.md`](./PROJECT_GUIDE.md) §5.2 |
| 新增 Hub 模块 | §9.2 标准流程 + `solarModules.ts` |
| 新增 Chat 意图 | §4.3 任务 3.1 + `intent_engine.py` TEST_CASES |
| 新增数据表 | §2.3 / §3.3 等 + Alembic revision |
| Phase 完成 | §10 路线图打勾 |

---

*与 [`PROJECT_GUIDE.md`](./PROJECT_GUIDE.md)（架构定位）配合使用：GUIDE 回答「是什么、在哪」；本文档回答「下一步怎么升」。*