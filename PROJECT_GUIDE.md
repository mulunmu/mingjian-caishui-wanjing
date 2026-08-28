# 企业风险评估系统 — 项目介绍与架构指南

> 本文档说明整个项目的架构、功能模块及代码位置，便于新人快速定位「做什么、放在哪」。

---

## 1. 项目概览

**企业风险评估系统**是一套面向税务与经营数据的多维风险分析平台，支持：

- 五维企业评分（税务 / 经营真实性 / 行业 / 法律 / 财务）
- 自然语言智能研判（Chat + 意图路由 + LLM）
- 交易关系网络图谱
- PDF 评估报告生成与邮件发送
- 宇宙风「透镜 Hub」交互导航

| 层级 | 技术栈 | 目录 |
|------|--------|------|
| 前端 | React 19 + TypeScript + Vite + Tailwind + ECharts + Three.js | `frontend/` |
| 后端 | FastAPI + SQLAlchemy async + PostgreSQL + LiteLLM | `backend/` |
| 部署 | Docker Compose（Postgres + backend + frontend） | `docker-compose.yml` |

**访问地址（本地开发）：**

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost:5173 |
| 后端 API | http://localhost:8000 |
| Swagger 文档 | http://localhost:8000/docs |

---

## 2. 系统架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        浏览器 (React SPA)                        │
│  pages/  components/  lib/dataSource.ts  lib/api.ts             │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP /api/v1  (Vite proxy → :8000)
┌────────────────────────────▼────────────────────────────────────┐
│                     FastAPI (backend/app/main.py)                │
│  api/v1/*  →  services/*  →  models/  →  PostgreSQL             │
│  mock 回退层 (mock_data.py)  │  LLM (LiteLLM)  │  静态 JSON      │
└─────────────────────────────────────────────────────────────────┘
```

### 2.1 数据模式（三层）

前端 `frontend/src/lib/dataSource.ts` 与后端 `/api/v1/health` 共同决定当前模式：

| 模式 | 条件 | 行为 |
|------|------|------|
| `mock` | 后端不可达 | 纯前端 mock，不调 API |
| `mock_with_llm` | DB 无数据 + LLM 已配置 | 模拟企业数据 + 真实 AI 对话 |
| `live` | DB 已连接且有企业数据 | 全链路真实数据 |

横幅提示：`frontend/src/components/MockDataBanner.tsx`

---

## 3. 目录结构（根级）

```
risk-assessment/
├── frontend/                 # React 前端
├── backend/                  # FastAPI 后端
├── docker-compose.yml        # 容器编排
├── README.md                 # 快速开始
├── PROJECT_GUIDE.md          # 本文档
└── opensource/               # 参考开源项目（非运行时依赖）
```

---

## 4. 前端架构

### 4.1 入口与路由

| 文件 | 职责 |
|------|------|
| `frontend/src/main.tsx` | React 挂载入口 |
| `frontend/src/App.tsx` | 路由表、Layout 壳、鉴权守卫 |
| `frontend/src/lib/routes.ts` | 路由常量 `ROUTES`、Chat 快捷 query |
| `frontend/vite.config.ts` | 开发服 :5173，`/api` 代理到 :8000 |

**路由地图：**

| 路径 | 页面组件 | 说明 |
|------|----------|------|
| `/login` | `pages/Login.tsx` | 登录 |
| `/register` | `pages/Register.tsx` | 注册 |
| `/hub` | `pages/Hub.tsx` | 透镜中心（轨道导航入口） |
| `/dashboard` | `pages/Dashboard.tsx` | 风控总览 KPI |
| `/enterprises` | `pages/EnterpriseSearch.tsx` | 企业搜索列表 |
| `/enterprise/:id` | `pages/EnterpriseDetail.tsx` | 企业详情画像 |
| `/chat` | `pages/ChatPanel.tsx` | 智能研判对话 |
| `/network` | ~~`pages/NetworkGraph.tsx`~~ | 交易网络图谱（已下线：隐私红线，禁止定位单一企业） |
| `/reports` | `pages/Reports.tsx` | 报告中心 |
| `/search`, `/pk`, `/warnings` | `components/legacy/LegacyRedirects.tsx` | 旧链重定向到 Chat |

**布局结构：**

- **Hub 页**：独立全屏，无底部 mini 导航 → `Hub.tsx` + `SolarNav mode="hub"`
- **业务页**：`App.tsx` 中 `Layout` = 宇宙背景 + Mock 横幅 + 内容区 + 底部 `SolarNav mode="mini"`

---

### 4.2 数据层（核心）

| 文件 | 职责 |
|------|------|
| `lib/dataSource.ts` | **数据模式中枢**：health 探测、fetchEnterprises、sendChatMessage |
| `lib/apiClient.ts` | Axios 实例、Bearer Token、401 跳转 |
| `lib/api.ts` | 类型定义 + 各 API 封装（enterprise/report/chat/network） |
| `lib/auth.ts` | localStorage JWT 读写 |
| `lib/mockEnterprises.ts` | 200 家确定性 mock 企业 + 预警 + buildMockReports |
| `lib/mockChat.ts` | 离线 Chat 规则模板回复 |
| `lib/taxDataAdapter.ts` | 原始税务行 → 评估对象（**预留，尚未接入**） |

**调用链示例（企业列表）：**

```
Dashboard / EnterpriseSearch
  → useEnterpriseCatalog.ts
    → getInstantEnterprises()     // 首屏 mock
    → fetchEnterprises()          // dataSource → GET /enterprise/list
```

---

### 4.3 功能页面详解

#### ① Hub 透镜中心

| 项目 | 位置 |
|------|------|
| 页面 | `frontend/src/pages/Hub.tsx` |
| 轨道导航 | `frontend/src/components/nav/SolarNav.tsx`（`mode="hub"`） |
| 行星粒子球 | `frontend/src/components/nav/HubPlanetOrb.tsx` |
| 模块配置（5 大模块颜色/轨道） | `frontend/src/lib/solarModules.ts` |
| 背景 shader | `frontend/src/components/background/CosmicShaderBackground.tsx` |

**交互：** CSS 公转动画、悬停停轨、背景 focus 联动、点击进入模块。

---

#### ② 风控总览 Dashboard

| 项目 | 位置 |
|------|------|
| 页面 | `frontend/src/pages/Dashboard.tsx` |
| 数据 | `fetchEnterprises()` + `fetchRiskWarnings()` |
| 图表 | ECharts 风险分布柱状图 |
| 快捷入口 | 跳转 Chat（对比/预警 query 见 `lib/constants.ts`） |

---

#### ③ 企业画像

| 项目 | 位置 |
|------|------|
| 搜索列表 | `frontend/src/pages/EnterpriseSearch.tsx` |
| 详情页 | `frontend/src/pages/EnterpriseDetail.tsx` |
| _catalog Hook | `frontend/src/hooks/useEnterpriseCatalog.ts` |
| 搜索框（拼音） | `frontend/src/components/SearchBox.tsx` + `lib/pinyin.ts` |
| 雷达图 | `frontend/src/components/EnterpriseRadarChart.tsx` |
| 维度卡片 | `frontend/src/components/EnterpriseDimensionCard.tsx` |
| 骨架屏 | `frontend/src/components/EnterpriseSkeleton.tsx` |
| API | `GET /enterprise/list`、`GET /enterprise/:id`、`GET .../legal-events` |

---

#### ④ 智能研判 Chat

| 项目 | 位置 |
|------|------|
| 页面 | `frontend/src/pages/ChatPanel.tsx` |
| 发送消息 | `dataSource.sendChatMessage()` → `POST /chat` |
| 内嵌图表 | `frontend/src/components/ChatInlineChart.tsx` |
| 离线回复 | `lib/mockChat.ts` |
| 会话 ID | 前端 `sessionId` ↔ 后端 `session_store.py` |

**后端意图（8 类）：** 见 `backend/app/services/intent_engine.py`

`tax_health` · `authenticity` · `industry_compare` · `risk_warning` · `enterprise_pk` · `full_report` · `email_report` · `chat`

---

#### ⑤ 交易网络

| 项目 | 位置 |
|------|------|
| 页面 | `frontend/src/pages/NetworkGraph.tsx`（~1900 行，Canvas 2D） |
| 发票边 API | `lib/api.ts` → `GET /network/invoice-edges` |
| 边数据加载 | `loadRealEdges()`，失败回退 `buildMockEdges()` |
| 画布主题 | `lib/canvasTheme.ts` |
| 静态边 JSON | `backend/app/data/invoice_edges.json` |

**能力：** 星团预览 → 企业子图穿透、缩放/拖拽/导出 PNG。

---

#### ⑥ 报告中心

| 项目 | 位置 |
|------|------|
| 页面 | `frontend/src/pages/Reports.tsx` |
| 列表 | 优先 `GET /report/list`，否则 `buildMockReports()` |
| 生成 | `lib/api.ts` → `POST /report/generate` |
| 下载 | `GET /report/:id/download` |
| PDF 模板 | `backend/app/templates/report.html` |
| PDF 引擎 | `backend/app/services/report_generator.py` |

---

#### ⑦ 登录 / 注册

| 项目 | 位置 |
|------|------|
| 登录 | `pages/Login.tsx` + `components/LoginForm.tsx` |
| 注册 | `pages/Register.tsx` |
| 后端 | `POST /auth/login`、`POST /auth/register` |
| 鉴权服务 | `backend/app/services/auth_service.py` |

---

### 4.4 视觉与动效层

| 模块 | 位置 | 说明 |
|------|------|------|
| 宇宙背景 | `components/background/CosmicShaderBackground.tsx` | R3F Canvas 入口 |
| 场景组合 | `components/background/cosmic/CosmicScene.tsx` | 星尘/银河/光晕 |
| Shader | `components/background/cosmic/shaders.ts` | GLSL |
| 行星几何 | `components/background/cosmic/planetGeometry.ts` | 粒子球参数 |
| 底部 Mini 球 | `components/nav/MiniNavOrb.tsx` | 业务页导航 orb |
| 页面过渡 | `components/PageTransition.tsx` + `lib/RouteTransitionContext.tsx` | 路由淡入淡出 |
| 动效常量 | `lib/motion.ts` | 时长/缓动 |
| 设计 Token | `frontend/src/styles/tokens.css` + `lib/theme.ts` | 颜色/图表主题 |
| 设计 Lint | `frontend/scripts/lint-design.mjs` | 禁止硬编码样式 |

---

### 4.5 前端测试

| 目录 | 内容 |
|------|------|
| `frontend/src/lib/__tests__/` | api、dataSource、utils、labels |
| `frontend/src/components/__tests__/` | ErrorBoundary、StateViews |
| `frontend/src/pages/__tests__/` | Login、Dashboard 冒烟 |
| `frontend/vitest.config.ts` | Vitest 配置 |

---

## 5. 后端架构

### 5.1 入口与中间件

| 文件 | 职责 |
|------|------|
| `backend/app/main.py` | FastAPI 应用、CORS、全局限流、`/health` |
| `backend/app/api/deps.py` | JWT 鉴权依赖 `get_current_user_optional` |
| `backend/app/responses.py` | UTF-8 JSON 响应类 |
| `backend/app/db/session.py` | 异步 SQLAlchemy + `get_db()` |
| `backend/Dockerfile` | 镜像构建 + seed + uvicorn |
| ⚠️ `backend/main.py` | **遗留 stub，勿用**；正确入口 `app.main:app` |

**环境变量：** 见 `README.md`（`DATABASE_URL`、`LLM_API_KEY`、`AUTH_REQUIRED`、`JWT_SECRET`、`CORS_ORIGINS`）

---

### 5.2 API 路由一览

所有路由前缀：`/api/v1`

| 模块 | 文件 | 端点 | 功能 |
|------|------|------|------|
| 健康 | `main.py` | `GET /health` | 数据库/LLM/数据模式探测 |
| 认证 | `api/v1/auth.py` | `POST /auth/login` | 登录发 JWT |
| | | `POST /auth/register` | 注册 |
| 企业 | `api/v1/enterprise.py` | `GET /enterprise/list` | 分页企业列表+评分 |
| | | `GET /enterprise/pk?ids=` | 多企业 PK |
| | | `GET /enterprise/{id}` | 单企业完整评估 |
| | | `GET /enterprise/{id}/legal-events` | 法律事件 |
| | | `GET /enterprise/{id}/dimensions` | 维度明细 |
| 预警 | `api/v1/risk.py` | `GET /risk/warnings` | 风险预警清单 |
| 对话 | `api/v1/chat.py` | `POST /chat` | 智能研判 |
| 报告 | `api/v1/report.py` | `GET /report/list` | 已生成 PDF 列表 |
| | | `POST /report/generate` | 生成 PDF |
| | | `POST /report/email` | 邮件发送 |
| | | `GET /report/{id}/download` | 下载 PDF |
| 网络 | ~~`api/v1/network.py`~~ | ~~`GET /network/invoice-edges`~~ | 发票交易边（已下线：隐私红线） |
| 图谱 | ~~`api/v1/graph.py`~~ | ~~`GET /graph/path`~~ | 产业链路径（已下线：隐私红线） |
| | | ~~`GET /graph/key-companies`~~ | 关键企业中心性（已下线：隐私红线） |

> 业务端点均支持 `AUTH_REQUIRED=true` 时 JWT 保护（health/auth 除外）。

---

### 5.3 服务层（业务核心）

```
api/v1/*.py  →  services/*.py  →  models/  →  PostgreSQL
                    ↓ mock 回退
              mock_data.py
```

| 服务文件 | 职责 |
|----------|------|
| **`assessment.py`** | **五维评分引擎**：算分、归因、预警、同业分位、缓存 |
| `assessment_weights.py` | 维度权重与中文标签 |
| `legal_service.py` | 法律维度扣分逻辑 |
| `mock_data.py` | 10 家完整 mock + ENT011–200 占位 |
| `intent_engine.py` | 意图识别（规则 + LLM）+ 企业名解析 |
| `chat_router.py` | 意图 → 数据查询 → 图表 → LLM/模板回复 |
| `llm_reply.py` | LiteLLM 调用 + 规则模板兜底 |
| `session_store.py` | Chat 多轮会话内存（30min TTL） |
| `report_generator.py` | Jinja2 + WeasyPrint/fpdf2 PDF |
| `email_service.py` | SMTP 发报告（yagmail） |
| `graph_service.py` | NetworkX 产业链图谱（已下线；行业级图谱数据源见 `reference/chain_knowledge_graph.py`） |
| `auth_service.py` | 用户注册/登录/JWT |
| `rate_limiter.py` | API 20 req/s + LLM 日配额 100 |
| `cache_service.py` | Redis/内存缓存（**预留，未接入 assessment**） |

**评分五维权重（`assessment_weights.py`）：**

| 维度 key | 中文 | 权重 |
|----------|------|------|
| `tax_health` | 税务健康 | 25% |
| `authenticity` | 经营真实性 | 25% |
| `industry` | 行业地位 | 20% |
| `legal` | 法律合规 | 15% |
| `finance` | 财务健康 | 15% |

---

### 5.4 数据模型

| 文件 | 表/模型 |
|------|---------|
| `backend/app/models/core_metrics.py` | `CoreMetrics`（企业宽表 27+ 指标） |
| | `LegalEvent`（法律事件明细） |

**种子数据：**

| 文件 | 说明 |
|------|------|
| `backend/seed_data.py` | 生成 200 企业 + 法律事件 + 发票边，导入 PG |
| `backend/seed_data.sql` | 生成的 SQL |
| `backend/app/data/companies_registry.json` | 企业注册表 JSON |
| `backend/app/data/invoice_edges.json` | 2000 条发票边 |
| `backend/migrations/` | Alembic 迁移骨架（真实接入时用） |

---

### 5.5 后端测试

| 目录/文件 | 内容 |
|-----------|------|
| `backend/tests/test_app.py` | FastAPI TestClient 集成冒烟 |
| `backend/tests/test_intent_engine.py` | 意图识别准确率 ≥85% |
| `backend/tests/test_auth.py` | JWT/注册 |
| `backend/tests/test_mock_data.py` | Mock 契约 |
| `backend/tests/test_chat_router.py` | Chat 图表辅助 |
| 等共 15 个文件 | `pytest tests/` → 81 项 |
| `.github/workflows/ci.yml` | CI：import 冒烟 + pytest + vitest + build |

---

## 6. 功能 → 代码定位速查表

| 用户看到的功能 | 前端页面 | 前端数据/API | 后端 API | 后端服务 |
|----------------|----------|--------------|----------|----------|
| 透镜 Hub 导航 | `Hub.tsx` + `SolarNav.tsx` | — | — | — |
| 登录注册 | `Login/Register.tsx` | `apiClient` | `/auth/*` | `auth_service.py` |
| 风控 KPI 总览 | `Dashboard.tsx` | `dataSource` | `/enterprise/list` `/risk/warnings` | `assessment.py` |
| 企业搜索 | `EnterpriseSearch.tsx` | `useEnterpriseCatalog` | `/enterprise/list` | `assessment.py` |
| 企业详情雷达 | `EnterpriseDetail.tsx` | `api.getEnterprise` | `/enterprise/:id` | `assessment.py` |
| 法律事件时间线 | `EnterpriseDetail.tsx` | `getLegalEvents` | `.../legal-events` | `legal_service.py` |
| 智能对话 | `ChatPanel.tsx` | `sendChatMessage` | `POST /chat` | `intent_engine` + `chat_router` + `llm_reply` |
| 对话内雷达/柱状图 | `ChatInlineChart.tsx` | Chat response charts | — | `chat_router._radar_chart` |
| 交易网络图谱 | ~~`NetworkGraph.tsx`~~ | ~~`getInvoiceEdges`~~ | ~~`/network/invoice-edges`~~ | 静态 JSON（已下线：隐私红线） |
| 报告列表 | `Reports.tsx` | `/report/list` | `/report/list` | `report_generator` |
| PDF 生成下载 | `EnterpriseDetail` / `Reports` | `generateReport` | `/report/generate` | `report_generator.py` |
| 邮件发报告 | `EnterpriseDetail.tsx` | `emailReport` | `/report/email` | `email_service.py` |
| 模拟数据横幅 | `MockDataBanner.tsx` | `resolveDataMode` | `/health` | `main.health` |
| 底部轨道导航 | `SolarNav.tsx` mini | — | — | — |
| 宇宙背景 | `CosmicShaderBackground` | — | — | — |

---

## 7. Chat 智能研判流程

```
用户输入 (ChatPanel.tsx)
    ↓
dataSource.sendChatMessage() 或 mockChat.ts
    ↓
POST /api/v1/chat  (chat.py)
    ↓
intent_engine.recognize()     ← 规则优先，LLM 兜底
    ↓
chat_router.route_chat()      ← 按意图查 assessment / report / warnings
    ↓
llm_reply.generate_reply()    ← LiteLLM 或规则模板
    ↓
返回 { reply, intent, data, charts, session_id }
    ↓
ChatPanel 渲染 Markdown + ChatInlineChart
```

**意图 → 输出类型：**

| 意图 | 典型问题 | 输出 |
|------|----------|------|
| tax_health | 「纳税信用怎么样」 | 雷达图 + 税务指标 |
| authenticity | 「经营真实吗」 | 雷达图 + 偏差数据 |
| industry_compare | 「同行排第几」 | 排名/柱状图 |
| enterprise_pk | 「对比 A 和 B」 | 多企业柱状对比 |
| risk_warning | 「有哪些风险」 | 预警列表 |
| full_report | 「生成报告」 | 报告 ID + 下载链接 |
| email_report | 「发到邮箱」 | 发送状态 |

---

## 8. 部署与开发命令

```bash
# Docker 一键
docker compose up -d

# 本地开发
cd backend && pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

cd frontend && npm install && npm run dev

# 导入 200 家模拟企业（需 Postgres）
cd backend && python seed_data.py

# 测试
cd backend && python -m pytest tests/ -q
cd frontend && npx vitest run && npm run build
```

---

## 9. 扩展与接入真实数据

| 步骤 | 操作位置 |
|------|----------|
| 1. Schema 迁移 | `backend/migrations/` + `alembic.ini` |
| 2. ETL 入库 | 写入 `core_metrics` / `legal_events` 表（对齐 `models/core_metrics.py`） |
| 3. 发票边 | 更新 `invoice_edges.json` 或扩展 `/network/invoice-edges` 查库 |
| 4. 意图企业库 | `intent_engine._load_companies()` 自动读 DB |
| 5. 前端切换 live | `dataSource.resolveDataMode()` 检测 `/health` 自动升级 |
| 6. 生产鉴权 | 设置 `AUTH_REQUIRED=true` + `JWT_SECRET` |

**预留但未接线：**

- `frontend/src/lib/taxDataAdapter.ts` — 原始税务行适配
- `backend/app/services/cache_service.py` — Redis 缓存

---

## 10. 附录：关键配置文件

| 文件 | 用途 |
|------|------|
| `frontend/package.json` | 前端依赖与脚本 |
| `frontend/tailwind.config.js` | Tailwind |
| `frontend/tsconfig.app.json` | TS 严格模式 |
| `backend/requirements.txt` | Python 依赖 |
| `backend/.env.example` | 环境变量模板 |
| `docker-compose.yml` | 三服务编排 |
| `.github/workflows/ci.yml` | GitHub Actions CI |

---

*文档版本：与代码库同步至 2026-07-06。如有模块增删，请优先更新 `App.tsx` 路由表与 `backend/app/main.py` 路由注册。*
