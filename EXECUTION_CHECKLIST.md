# 执行清单（交给 Cursor 改造用）

> 目标：把当前「查企业的风险评估系统」改造成「风控报告产品」。
> 蓝图依据：`jiegou.md`（技术架构）+ 报告产出规格（真实性/可追溯性/风控算法）。
> 本清单只覆盖「简化 UI、接入算法、融入数据、删除冗余」四步，其余由人工确认。

---

## 0. 改造总原则（Cursor 动手前先读）

1. **框架留下来，业务层换一遍**：保留 FastAPI + React + Vite + Tailwind + LLM + PDF 框架，业务从「查企业」换成「功能展示 + AI 研判 + 组合报告」。
2. **LLM 只组织语言、不下结论**：所有风险结论由确定性算法算出，LLM 只负责把结论改写成段落并挂上证据链。
3. **数据是匿名的**：企业名 MD5 不可得，UI 层禁止任何「定位到单一企业」的入口。

---

## 任务一：接入开源算法库

### 1.1 已克隆到 `opensource/` 的源码（参考/集成用）

| 目录 | 用途 |
|------|------|
| `opensource/search_benford_law_compatibility/` | Benford 定律（真实性检测，含卡方/MAD 检验） |
| `opensource/acc_fraud_detections/` | 会计欺诈检测脚本（Benford + 审计规则） |
| `opensource/pyod/` | 异常检测库（反欺诈：发票/集中度/频次） |
| `opensource/instructor/` | 结构化输出（Pydantic 校验 + 重试） |
| `opensource/selfcheckgpt/` | 幻觉自检（多采样一致性） |
| `opensource/outlines/` | 约束解码（保证 JSON schema 合法） |

### 1.2 用 pip 装进后端环境（比 clone 更该做）

```bash
# 国内镜像；若后端用 venv 先激活。pip 不在 PATH 时用 python -m pip
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple \
    pyod instructor selfcheckgpt outlines ragas great_expectations
```

> 依赖已有：`networkx`（在 requirements.txt）。`pyod` 依赖 numba，**Python 3.14 可能缺 wheel**，建议后端用 3.11/3.12。

### 1.3 集成落点（告诉 Cursor 把库接在哪）

- `pyod` → 新建 `backend/app/services/fraud_engine.py`：进销错配、开票频次、集中度三类异常打分。
- Benford 工具 → 新建 `backend/app/services/authenticity_engine.py`：财报数字分布异常。
- `instructor` / `outlines` → 改造 `backend/app/services/llm_reply.py`：LLM 输出强制走「报告 claim schema」。
- `selfcheckgpt` / `ragas` → 报告生成后的离线抽检脚本（不阻塞主流程）。

### 1.4 验收

- `python -c "import pyod, instructor, selfcheckgpt"` 不报错。
- 后端能对一条假发票样本输出「进销错配」异常分。

---

## 任务二：简化 UI（界面简洁可用）

### 2.1 目标

只留一个「研判中心」入口 + 登录/注册，去掉所有企业浏览/搜索/详情/网络图谱的复杂页面。

### 2.2 涉及文件

| 动作 | 文件 |
|------|------|
| 改路由表 | `frontend/src/App.tsx` |
| 改导航模块配置 | `frontend/src/lib/solarModules.ts`（5 模块精简） |
| 改路由常量 | `frontend/src/lib/routes.ts` |
| 重点改 | `frontend/src/pages/ChatPanel.tsx`（升级为「研判中心」，唯一业务入口） |
| 可保留 | `frontend/src/pages/Login.tsx`、`Register.tsx`、`Dashboard.tsx`（简化为入口卡片） |

### 2.3 目标页面结构（研判中心）

```
进入 → AI 打招呼 + 两类卡片
  ├─ 维度卡：整体 / 按行业 / 按地区 / 按时间 / 按信号
  └─ 功能卡：评分 / 真实性 / 反欺诈 / 基准 / 趋势
点卡片 → 输入框填好问句 → 发送 → AI 给「结论 + 追问」（证据链隐藏）
追问累积 → 覆盖度够 → AI 提示「生成 XX 报告」→ 确认 → 组合报告（证据链完整）
```

### 2.4 验收

- 首屏无企业搜索框、无网络图、无企业列表。
- 点「按行业 + 趋势」能填出「分析各行业的趋势走向」并得到结论。

---

## 任务三：融入数据

### 3.1 数据现实（`jiegou.md` §2，开发前必须对齐）

- 200 家小微，180 万条，3.5 年，100% 非上市，企业名 MD5 不可得。
- 覆盖率：信用 100%、增值税 99.5%、发票 96%、财报 95%、缴税 91%、现金流 61%、社保 50%。
- 行业 107 个 → 聚合 6 大类：批发零售 / 制造 / 建筑 / IT软件 / 服务 / 其他。

### 3.2 ETL 步骤

1. 解析 `数据.sql`（1.95GB，`REPLACE INTO`，13 张表）→ 入库 PostgreSQL。
2. 建 `core_metrics` 宽表：`enterprise_id` = taxpayer_id 哈希，`display_label` = 地区+行业大类+规模（**不含股东姓名**）。
3. 五维指标字段从税务表直接算，零名字依赖。
4. 保留原始明细表（如 `invoice_details`）供溯源下钻。

### 3.3 重写模型

`backend/app/models/core_metrics.py` 现模型是「上市公司宽表」（含 `market_cap`/`pe_ratio`/`roe`/`z_score`），与小微/非上市冲突，**需重写**为新 schema（对齐 jiegou.md §4）。

### 3.4 验收

- `GET /api/v1/health` 返回 `data_mode: live`，`enterprise_count > 0`。
- 前端 MockDataBanner 在 live 下不显示。

---

## 任务四：删除不需要的部分

### 4.1 后端删除/重写（对照 jiegou.md §9）

| 动作 | 文件 |
|------|------|
| ✂️ 删 | `backend/app/api/v1/enterprise.py`（企业查询） |
| ✂️ 删 | `backend/app/api/v1/network.py`（网络图） |
| ✂️ 删 | `backend/app/api/v1/graph.py`（产业链） |
| ✂️ 删 | `backend/app/services/graph_service.py` |
| ✂️ 删 | `backend/app/services/legal_service.py`（企查查口径） |
| ✂️ 删 | `backend/app/data/invoice_edges.json`、`companies_registry.json` |
| ❌ 重写 | `backend/app/models/core_metrics.py`（见任务三） |
| ❌ 重写 | `backend/app/services/assessment.py`（数据源换税务表，算分框架可复用） |
| ❌ 重写 | `backend/app/services/intent_engine.py`（企业名解析 → 「功能×维度切片」意图） |
| ❌ 重写 | `backend/app/services/mock_data.py`（去掉企业名，改成匿名样机） |
| ✅ 复用 | `main.py`/`deps.py`/`session.py`/`responses.py`/`auth_service`/`rate_limiter`/`session_store`/`email_service`/`report_generator`(改模板)/`llm_reply`(改 prompt) |

### 4.2 前端删除

| 动作 | 文件 |
|------|------|
| ✂️ 删 | `frontend/src/pages/EnterpriseSearch.tsx` |
| ✂️ 删 | `frontend/src/pages/EnterpriseDetail.tsx` |
| ✂️ 删 | `frontend/src/pages/NetworkGraph.tsx` |
| ✂️ 删 | `frontend/src/pages/Reports.tsx`（独立报告中心，报告并入研判中心） |
| ✂️ 删 | `frontend/src/components/EnterpriseRadarChart.tsx`、`EnterpriseDimensionCard.tsx`、`EnterpriseSkeleton.tsx`、`SearchBox.tsx`、`WarningSignalBadge.tsx` |
| ✂️ 删 | `frontend/src/lib/pinyin.ts`、`mockEnterprises.ts`、`canvasTheme.ts` |
| ✂️ 删 | `frontend/src/components/legacy/LegacyRedirects.tsx` |

### 4.3 删除后的收尾（容易被忽略）

- `backend/app/main.py`：去掉 `enterprise_router`/`network_router`/`graph_router` 的 `include_router`。
- `frontend/src/App.tsx`：去掉对应 `<Route>` 与懒加载。
- `frontend/src/lib/solarModules.ts`：Hub 轨道从 5 模块精简，删掉指向已删页的模块。
- `frontend/src/lib/api.ts` / `apiClient.ts`：去掉 enterprise/network 相关封装。
- 全局搜 `enterprise`、`network`、`graph`、`legal` 引用，清干净后跑一遍 `npm run build` + `python -m pytest` 确认不红。

### 4.4 验收

- 前后端 build/test 全绿，无残留引用已删文件的 import。
- 系统只剩：登录/注册 → 研判中心（AI 对话 + 组合报告）。

---

## 优先级建议（给 Cursor 的执行顺序）

1. **任务四（删除冗余）先做** —— 减负后再改，避免改半天还带着旧代码。
2. **任务二（简化 UI）** —— 依赖删除后的干净路由。
3. **任务三（融入数据）** —— 重写 CoreMetrics + ETL，是最大块。
4. **任务一（接入算法）** —— 最后接 pyod/Benford/instructor。

> ⚠️ 关键决策点（需你本人拍板后再让 Cursor 动）：
> 「报告对象」是**匿名群体/行业切片**（当前数据名字不可得，只能如此），还是**具体企业**（需真实姓名数据，与当前匿名约束冲突）。这个决定会影响任务三的 schema 和任务二的产品形态，务必先定。
