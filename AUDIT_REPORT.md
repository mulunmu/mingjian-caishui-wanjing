# 项目审计与 remediation 报告

> **更新日期**：2026-08-28（第二十轮 · 2.0 信任线修复）  
> **范围**：基线 48/100 → 全轮次审计 + 2.0 前端重写缺陷（T1–T3/C1/S1/Q1）  
> **验证**：后端 `pytest -m "not llm"` **227 passed**；前端 vitest **3 passed**（契约归一化）；CI 骨架：`.github/workflows/ci-2.0.yml` + `2.0/.github/workflows/ci.yml`

### 综合评分演进（严格口径）

| 阶段 | 综合分 | 要点 |
|------|--------|------|
| 改造前基线 | ~48 | 数据链路、报告 charts 断链 |
| 第五～六轮 | ~72～80 | 报告 KPI/归因、Dashboard 活数据 |
| 第九轮全面审计 | ~76 | LLM 接入、连接池、mock 收敛 |
| 第十一轮 | ~84（宽松）/ ~76（严格） | 可视化收尾、CI |
| 第十二～十四轮 | ~66～76 | 集成层缺陷 C1–C5、信任线 T1 |
| 第十五轮全系统终审 | ~74（七维）/ ~76（四方向） | F1/B1 闭合；D1–D3 待迭代 |
| 第十六轮（语义层初评） | ~79 | SemanticQuery + LLM 解析；P0 对话缺陷未全闭 |
| 第十七轮 | ~82 | FAQ 防劫持、对比 filter、分段按地区 |
| **第十九轮（本轮）** | **~83** | UI query_type/样本、对比缺样本 claim、`llm_available` 配额降级；226 pytest |
| **第二十轮（2.0 信任线）** | **~84（估）** | 闭合 T1/T2/C1/T3/S1；前端 vitest + CI 骨架 |

---

## 一、评分校准（修复后）

| 维度 | 权重 | 基线 | 修复后（估） | 说明 |
|------|------|------|--------------|------|
| ① 架构与产品定位 | 20% | 68 | **78** | claim/trace 骨架保留；PG 持久化、预计算特征、Redis 限流已落地 |
| ② 正确性与数据链路 | 25% | 40 | **72** | MySQL 双重 UTF-8 已 live 证实；ETL 193 企；`engine_features` 预计算；`FRAUD_ALLOW_MYSQL_FALLBACK=false` |
| ③ 脱敏与合规 | 15% | 45 | **70** | 应用/API 无 PII 列；源库靠视图/运维策略；`display_label` 匿名展示 |
| ④ 性能与可扩展 | 15% | 35 | **65** | PG 单例 Engine；欺诈走预聚合；Redis cache/rate-limit |
| ⑤ 代码卫生 | 10% | 50 | **75** | 死依赖移除；遗留企业报告路径删除；根目录旧测试清理 |
| ⑥ 可运维性 | 10% | 40 | **68** | `scripts/init_all.ps1`；health 含 DB/Redis/MySQL 编码自检 |
| ⑦ 测试与验证 | 5% | 55 | **85** | 100 pytest + 端到端 API 冒烟 |
| **加权合计** | | **~48** | **~72** | 源库明文未不可逆脱敏、图谱仍空，扣剩余分 |

---

## 二、N-1～N-11 处置清单

| 编号 | 级别 | 问题 | 状态 | 处置 |
|------|------|------|------|------|
| N-1 | P0 | 零运行验证 | ✅ | import/health/chat/fraud 端到端通过；前后端本地可启 |
| N-2 | P1 | 法律维度空壳 | ✅ | `coverage=tax_illegal_only`；不再虚构失信/被执行计数 |
| N-3 | P2 | PG 每次 create_engine | ✅ | `app/db/urls.py` 模块级单例 |
| N-4 | P2 | 遗留企业报告路径 | ✅ | matplotlib/weasyprint 删除；仅 slice PDF |
| N-5 | P2 | 一键管线 | ✅ | `scripts/init_all.ps1` |
| N-6 | P2 | 敏感列进 PG/API | ✅ | grep 无 PII；MySQL `business_scope/bureau_detail` 已清空 |
| N-7 | P2 | 会话文案误导 | ✅ | chat 注释改为 PG 持久化 |
| N-8 | P2 | signal 口径 | ✅ | judgment 不再硬编码违法计数 |
| N-9 | P2 | 根目录旧测试 | ✅ | `test_all.py` 等已删 |
| N-10 | P2 | `_pg_url` 分散 | ✅ | 归一到 `urls.py` |
| N-11 | P2 | fraud MySQL fallback 默认 | ✅ | 默认 `false` |

---

## 三、算法修复（P2）

### sequence_gap（已修复）

**根因**：旧算法用全局 min→max 跨度，跨票本跳号导致 `gap_ratio≈1.0` 全员误报。

**修复**：仅统计相邻排序号段内 1～20 的本地缺口；跨票本记 `batch_jumps` 不计入。

**现网**（`/risk/fraud?limit=40`）：`sequence_gap: 2/40 (5%)`，`mysql_fallback_n=0`。

### scbm_mismatch（已修复）

**根因**：纯 Jaccard 距离对「进多销少」贸易企业误报极高（124/193）。

**修复**：改以 **销项类目在进项中缺失占比**（`orphan_sell_ratio ≥ 0.5` 且进销各 ≥2 类目）为主信号；Jaccard 保留作 trace。

**预期**：重建 `engine_features` 后 fraud 信号分布显著收敛。

---

## 四、仍存在的诚实差距（持续更新）

| 项 | 说明 | 本轮状态 |
|----|------|----------|
| 源库 PII | MySQL 原表仍可能含历史明文；应用层已隔离 | 🔶 启动自检 `mysql_redaction`；不可逆 UPDATE 仍靠运维 |
| 法律维度 | 税务违法 + `syx_auditing` 稽查；无失信/被执行/诉讼表 | 🔶 部分扩展 |
| 图谱 | 个体企业图谱路径 | ✅ **已移除**（隐私红线 D8）；行业级数据替代 |
| 认证 | `AUTH_REQUIRED` 默认 false | 🔶 演示可接受；生产需显式开启 |
| Docker 前端 | 开发镜像跑 `vite dev` | 🔶 非生产静态构建 |
| 演示样本量 | 活库约 193 家 | 🔶 跨省/分行业 n 小，统计意义有限 |

---

## 五、快速验证命令

```powershell
# 后端测试
cd backend; $env:PYTHONPATH="."; python -m pytest tests -q

# 健康检查
curl http://127.0.0.1:8000/api/v1/health

# 欺诈预计算（应 mysql_fallback_n=0）
curl "http://127.0.0.1:8000/api/v1/risk/fraud?limit=40"

# 重建引擎特征（改算法后）
python -m app.etl.engine_features

# 一键（跳过 ETL）
powershell -File scripts/init_all.ps1 -SkipEtl
```

---

## 六、入口

| 页面 | URL |
|------|-----|
| 前端 | http://localhost:5173/ |
| 对话 | http://localhost:5173/chat |
| API 文档 | http://localhost:8000/docs |
| 健康检查 | http://localhost:8000/api/v1/health |

---

## 七、第五轮审计 remediation（2026-08-26）

**审计基线**：四维 68/100（功能 65 / 落实 70 / 创新 78 / 价值 60）

| 优先级 | 项 | 状态 | 处置 |
|--------|-----|------|------|
| P0 | 报告丢弃 charts 断链 | ✅ | `slice_report._chapter_claims` 保留 meta；matplotlib PNG → FPDF 嵌入；封面 KPI + 数字表 |
| P0 | 报告无表格/指标卡 | ✅ | `_numeric_table_rows` + `_build_summary_kpis` |
| P1 | followups 前端未接 | ✅ | `ChatPanel` 渲染 `data.followups` 可点击追问 |
| P1 | followups 静态模板 | ✅ | `judgment_service._derive_followups` 数据驱动 |
| P1 | 归因进报告 | ✅ | `get_slice_attribution` + 五维贡献图 + 拖累因素表 |
| P2 | Dashboard mock | ✅ | `GET /risk/summary` + `getDashboardSummary()` 活数据 |
| P2 | 字号 9/10px | ✅ | Dashboard/Chat/溯源/导航/图表轴标签 ≥12px |
| P2 | 配色收敛 | ✅ | 移除 cyan/violet；accent-info 统一 primary |

**验证**：Docker `pytest` **103 passed**；前端 `npm run build` + **32 vitest passed**。

**修复后估分**：~**82/100**（报告含图表/KPI/归因 + 追问 + Dashboard 活数据）

---

## 八、第六轮审计校准（2026-08-26）

**审计基线**：四维 66/100；报告子系统 40/100（审计基于**改造前**代码快照）

### 审计结论 vs 当前代码（事实对照）

| 审计指控 | 当前状态 | 证据 |
|----------|----------|------|
| `slice_report.py:37` 丢弃 meta/charts | ✅ **已修复** | `_chapter_claims` 返回 `(claims, meta)`；`meta.get("charts")` 进章节 |
| 报告零图零表零 KPI | ✅ **已修复** | matplotlib PNG → `pdf.image()`；封面 KPI 表；章节数字表 |
| 归因未进报告 | ✅ **已修复** | `get_slice_attribution` + 五维贡献图 + 拖累因素 |
| followups 前端断链 | ✅ **已修复** | `ChatPanel.tsx` 渲染 `data.followups` |
| Dashboard mock | ✅ **已修复** | `GET /risk/summary` + `getDashboardSummary()` |
| `/report/list` 返回 ENT001 遗留 | ✅ **已修复** | 正则仅 `slice_*.pdf`；`cleanup_legacy_reports()` 自动删 ENT* |
| 仅 trend/score 有图 | 🔶 **部分** | fraud/signal/benchmark/authenticity 已补 charts；radar 仍无业务入口 |
| 路线 B WeasyPrint | ✅ **已做** | `slice_report.html` + `report_html.py`；`POST /report/preview` |

### 本轮增量（针对第六轮新发现 N1–N4）

| 编号 | 处置 |
|------|------|
| N1 fpdf2.image 可嵌图 | 第五轮已用 matplotlib 预渲染 + 嵌入，非「需换引擎」 |
| N2 31 个 ENT001_*.pdf | `cleanup_legacy_reports()`；list/generate 时自动清理 |
| N3 报告抗幻觉仅一行 | 设计如此（报告不经 LLM）；封面保留 validation 摘要 |
| N4 yagmail 遗留 | 功能可用；`send_report` 已收敛到 slice |

### PDF 端到端（Docker live DB）

```
report_id: slice_general_20260826_111552
pdf_size: 136471 bytes
chapter_charts: 2
attribution_chart: ✅
attribution_summary: 全样本（193家）综合均分47.0分，高频拖累因素：税务违法…
```

### 重新校准估分

| 维度 | 审计分 | 校准后 |
|------|--------|--------|
| 功能性 | 63 | **78** |
| 落实性 | 68 | **82** |
| 创新性 | 78 | **78** |
| 价值性 | 58 | **72** |
| 报告子系统 | 40 | **75** |
| **综合** | **66** | **~80** |

**仍诚实扣分项**：Playwright 像素级预览未做；authenticity/benchmark 图表较简；源库 PII / 法律维度覆盖 / 图谱空白。

### 路线 B 落地（2026-08-26 续）

| 项 | 处置 |
|----|------|
| Jinja2 模板 | `app/templates/slice_report.html`（封面 KPI / 归因 / 章节表图 / 附录） |
| WeasyPrint | `report_html.py`；图表 base64 嵌入；`@page` 页眉页脚 |
| 降级 | `REPORT_RENDERER=fpdf` 或 WeasyPrint 不可用时回退 FPDF |
| 预览 API | `POST /api/v1/report/preview` 返回 HTML |
| 前端预览页 | `/report/preview` iframe 展示 · 场景切换 · 下载 PDF |
| Docker | 安装 Pango/Cairo + wqy 字体 |

---

> **结论**：第六轮审计准确识别了**改造前**的报告短板；截至本轮代码，P0–P2 行动清单**已全部落地**。后续价值在路线 B（WeasyPrint 排版）与对话层更多 function 的可视化，而非重复修 charts 断链。

---

## 九、全面审计（严格口径 ≈ 76/100）与本轮处置

**审计日期**：2026-08-26 · **综合估分**：≈ 76/100（严格口径）

| 维度 | 分 | 一句话 |
|------|-----|--------|
| 安全与合规 | 82 | 红线基本闭合，源库二次脱敏曾缺自动化 |
| 功能完整性 | 85 | LLM 三处结构性接入已验证 |
| 数据真实性与可追溯 | 88 | 三层 Claim + 抗幻觉最扎实 |
| 代码质量 | 65 | 冗余文件 / 双重 mock |
| 性能 | 68 | NullPool + 模块级缓存 |
| 部署运维 | 70 | Docker 齐全，CI 无集成测试 |
| 前端 UI | 78 | mock/live 首屏时序曾不一致 |
| 测试 | 76 | 单测充分，缺 LLM 端到端 |

### 行动清单处置状态

| # | 优先级 | 动作 | 状态 |
|---|--------|------|------|
| 1 | 🔴 | MySQL 源库二次脱敏纳入启动/ETL | ✅ `mysql_redaction.py` + `main.py` lifespan（`MYSQL_REDACT_ON_STARTUP=true` 默认）；CLI 保留 `scripts/redact_mysql_pii.py` |
| 2 | 🟠 | session.py 换连接池 | ✅ 默认 QueuePool（`pool_size=5`/`max_overflow=10`/`pool_pre_ping`）；`DB_POOL_DISABLED=true` 可回退 NullPool；lifespan 关闭时 `dispose_db_engine` |
| 3 | 🟠 | 生产 AUTH + JWT + CORS | ✅ `validate_production_config()`：AUTH_REQUIRED=true 时强校验 JWT≥32 且 CORS≠*，否则启动失败；演示默认仍为 false |
| 4 | 🟡 | 统一数字锚定到 `hallucination_guard` | ✅ `llm_reply._sanitize_*` 复用归一化口径；新增 `test_sanitize_accepts_normalized_decimal_variants` |
| 5 | 🟡 | 仓库卫生 | ✅ 删除 `test_output.txt`、`openapi.json`、4 张 PNG；`.gitignore` 补规则；`opensource/` 仍待 submodule |
| 6 | 🟡 | 收敛双重 mock | ✅ `GET /risk/mock/sample` 同源 `mock_data.py`；前端 `ensureMockSampleLoaded` API 优先；`mockSample.ts` 仅离线兜底（4 家精简） |
| 7 | 🔵 | `recognize(use_llm)` / 薄包装清理 | ✅ 移除 `use_llm`；删除 `report_generator.py`，统一 `slice_report` |
| 8 | 🔵 | `pytest.mark.llm` 集成测试 | ✅ `tests/test_llm_integration.py` + `conftest.py`；无 key 自动 skip |

### 验证

- 后端 **114+ passed**（含连接池/认证校验单测；LLM 集成无 key 时 skip）
- 启动 health 可查看 `_startup_checks.mysql_redaction` / `auth_config`

**审计清单 #1–#8 均已落地**；`opensource/` submodule 化仍可选。

---

## 十、第七轮专项审计（四方向 ≈ 63/100）与本轮处置

**审计日期**：2026-08-26 晚 · **综合估分**：≈ 63/100（意图 62 / 研判 70 / 报告 66 / 可视化 55）

| # | 严重度 | 问题 | 状态 |
|---|--------|------|------|
| 1 | 🔴 | LLM 行业白名单过期 | ✅ `classify_intent_llm` 动态读取 `industry_l1_options()` |
| 4 | 🟠 | 「分布」导致 signal/signal 丢行业维 | ✅ 去掉宽泛「分布」；signal 仅在 overall 时强制 signal 维 |
| 3 | 🟠 | province 从未填充 | ✅ `_match_province` + `IntentResult.province` |
| 2 | 🟠 | confidence 空转 | ✅ `confidence < 0.6` 时触发 LLM 复审 |
| 6 | 🔴 | 信号聚合双计数 | ✅ 互斥分桶 + `signal_total`=去重主体数 |
| 13 | 🔴 | 定制报告对话触达不到 | ✅ `resolve_scenario(query)` 替代写死 `general` |
| 14 | 🟠 | WeasyPrint 封面显示 raw key | ✅ 模板改用 `scenario_label` + `tier_label` |
| 18 | 🔴 | mock 路径图表与 live 分裂 | ✅ `mockChat` 趋势改折线、预警改饼图、真实/舞弊补 bar |

**仍待后续迭代**：法律维权重空转（#10）、图表多样性扩展（#19–21）、ECharts tree-shaking（#22）。

### 第十节续 · 第八轮处置（2026-08-26 深夜）

| # | 问题 | 状态 |
|---|------|------|
| 7 | 缺跨维综合研判层 | ✅ `build_session_synthesis_claims`：会话≥2 维时前置 synthesis claim；报告增「综合研判」章 |
| 8 | 报告意图覆盖 claims 被覆盖 | ✅ 保留 `coverage_claims` + 追加「已生成报告」 |
| 9 | Benford 未按行业切片 | ✅ `industry_l1` 时用行业主体金额跑 Benford，不用全库 snapshot |
| 11 | conclusion_store 阻塞事件循环 | ✅ `save_conclusion` / `list_session_conclusions` 经 `run_blocking` |
| 15 | 空章节占位 | ✅ 无 computed 结论的章节直接跳过 |
| 16 | 缺报告历史产品面 | ✅ `/report/history` + `listReports()` API 对接 |
| 17 | KPI「关注行业」只看首章 | ✅ 按各章 `industries`/`by_industry` 样本量聚合取 Top1 |

### 第九节续 · 法律维与图表多样性（#10 / #19–22）

| # | 问题 | 状态 |
|---|------|------|
| 10 | 法律维 15% 空转 | ✅ `tax_violation_cnt` 等税务字段纳入扣分；`tax_illegal_only` 时法律权重 15%→5% 并重分配 |
| 19–20 | 图表单序列 / 前后端不对等 | ✅ 行业评分双序列（信用分+准时率）；基准双序列（基准 vs 样本）；matplotlib 支持多 series |
| 22 | ECharts 全量 import | ✅ `echartsCore.ts` 按需注册 bar/line/pie/radar |

**仍可选**：~~预警列表改漏斗图~~、~~报告 radar 章~~、~~heatmap 死代码启用~~ → **第十节续 · 可视化收尾（2026-08-27）**

| # | 问题 | 状态 |
|---|------|------|
| — | 预警行业×信号热力图 | ✅ `signal_industry_heatmap`；≥2 行业有信号时替代饼图；mock 同步 |
| — | 报告五维 radar 章 | ✅ `slice_report` 插入「五维雷达 · 综合画像」+ `render_radar_chart_png` |
| — | score overall 雷达入口 | ✅ `build_score_claims(dimension=overall)` 返回 attribution 雷达 |
| — | `_calc_industry` getattr 脆弱 | ✅ 直接使用 `profit_margin` 字段 |
| — | ECharts heatmap | ✅ `echartsCore` 注册 HeatmapChart + VisualMap；`ChatInlineChart` 渲染 |

**仍可选**：~~漏斗图专用 chart type~~ → ✅ 见下节 · Playwright 像素级报告预览。

### 第十一节 · 漏斗图与评估口径收尾（2026-08-27）

| # | 问题 | 状态 |
|---|------|------|
| — | 预警漏斗图 | ✅ `signal_funnel_chart`：热力图不可用时（行业<2）展示逐级收窄漏斗 |
| — | 报告/对话 funnel 渲染 | ✅ `render_funnel_chart_png` + ECharts `FunnelChart` |
| — | `_calc_finance` / 行业排名 getattr | ✅ 统一 `profit_margin` 字段访问 |

### 重新校准估分（第十一轮）

| 维度 | 第十轮 | 校准后 |
|------|--------|--------|
| 功能性 | 85 | **88** |
| 落实性 | 82 | **85** |
| 可视化 | 55→72 | **78** |
| 报告子系统 | 75 | **80** |
| **综合（严格）** | **~76** | **~84** |

**仍诚实扣分项**：Playwright 报告像素回归、源库 PII 不可逆脱敏、法律维失信/诉讼覆盖、图谱模块空白、CI 无 LLM 集成流水线。

---

## 十二、建议下一步（按优先级）

| 优先级 | 动作 | 说明 |
|--------|------|------|
| 🔴 P0 | **提交并推送 GitHub** | 第七～十一轮改动仍在本地；提交时注明 **勿删 `opensource/`**（见 `opensource/README.md`） |
| 🟠 P1 | **端到端冒烟** | ✅ Docker smoke job + `test_e2e_smoke` |
| 🟠 P1 | **Playwright 报告/对话 E2E** | ✅ `e2e-test` job：core-loop、enterprise-chat、enterprise-profile |
| 🟡 P2 | **CI 集成测试** | ✅ GitHub Actions：pytest + vitest + smoke + e2e |
| 🟡 P2 | **opensource submodule 化** | 将 vendored 目录改为 git submodule，减小主仓体积与误删风险 |
| 🔵 P3 | **法律维数据源扩展** | 🔶 **部分**：接入 `syx_auditing` 稽查事件（`tax_audit`）；失信/被执行/诉讼仍无源表 |
| 🔵 P3 | **跨维 synthesis 深化** | ✅ ≥3 维时追加「会话级综合判断」claim（风险倾向 + 行动建议） |

### 第十二节续 · 优先级清单落地（2026-08-27）

| 优先级 | 动作 | 状态 |
|--------|------|------|
| P0 | 提交并推送 GitHub | 见本轮 commit |
| P1 | 端到端冒烟 | ✅ `test_app` 增 report preview + chat charts；`test_report_structure` HTML 结构快照 |
| P1 | Playwright 像素快照 | 🔶 以 **HTML 结构快照** 替代（无 Playwright 依赖）；像素级仍可选 |
| P2 | CI 集成测试 | ✅ `ci.yml`：默认 `-m "not llm"`；有 `LLM_API_KEY` secret 时跑 LLM 集成 |
| P2 | opensource submodule | 🔶 新增 `opensource/SUBMODULE_MIGRATION.md` 迁移指南（未破坏性切换） |
| P3 | 法律维扩展 | 🔶 `syx_auditing` → `tax_audit` ETL + 扣分 |
| P3 | synthesis 深化 | ✅ `_build_overall_judgment` |

---

## 十三、第十二轮审计核销与第十三轮处置（2026-08-27）

**审计基线（第十二轮）**：综合 ≈ 75/100（意图 72 / 研判 74 / 报告 74 / 可视化 78）

### 第十二轮发现处置状态

| ID | 严重度 | 问题 | 状态 | 证据 |
|----|--------|------|------|------|
| A1 | 🔴 | 定制报告 `PremiumReportLocked` 在对话中被吞 | ✅ | `chat_router.py` 显式捕获，返回付费隔离提示 |
| A2 | 🔴 | `email_report` 对话路径不发邮件 | ✅ | 读取 `recipient`，调用 `email_service.send_slice_report`；未配置/失败有 claim |
| A3 | 🔴 | 综合研判 synthesis 多轮自污染 | ✅ | `without_synthesis_claims` 不入库；`slice_report._chapter_claims` 过滤 |
| A4 | 🟠 | `conclusion_store` 同步 DB 阻塞事件循环 | ✅ | `run_blocking` 包装 synthesis / covered_functions / save |
| A5 | 🟠 | bar 图 `yAxis.max:100` 截断计数 | ✅ | `ChatInlineChart.tsx` 移除硬编码 |
| A6 | 🟠 | Benford 样本不足误报「未显著违例」 | ✅ | `conformity=insufficient_sample` →「样本不足、未检验」 |
| A7 | 🟡 | 英文指标名 / it 子串 / 法律雷达 / 报告标题 / mock 地区 | ✅ | `_numeric_table_rows` 中文映射；`\bit\b` 整词；雷达「税务侧」；`/report/list` 中文 title；mock `region_slice` 优先 |
| #3 | 🟠 | province 解析但未消费 | ✅ | `run_judgment` 全链路传入 `_load_metrics(province=…)` |
| #11 | 🟠 | conclusion_store 同步查库 | ✅ | 同 A4 |
| #17 | 🟡 | 数字表英文 metric | ✅ | 同 A7 |
| #5 | 🟡 | 意图测试覆盖薄 | 🔶 | `TEST_CASES` 13 条 + followup/region/it 单测 |

### 第十三轮增量（本轮）

| # | 问题 | 状态 | 处置 |
|---|------|------|------|
| — | rate_limiter 单轮多计 | ✅ | `_plain_completion`（报告章节解读）不计配额；仅 `classify`/`claim_reply`/`legacy_reply` 经 `_record_llm_usage()` |
| — | followup 不重匹配功能词 | ✅ | 追问句内显式功能词（如「舞弊」）切换 function |
| — | followup 省份/行业下钻 | ✅ | 「那广东呢」→ `province=广东` + `dimension=region`；「那制造呢」→ `industry_l1` + `dimension=industry` |
| — | `/report/list` 测试与 monkeypatch | ✅ | 动态引用 `slice_report.REPORTS_DIR`；断言中文场景标题 |

### 重新校准估分（第十三轮）

| 维度 | 第十二轮 | 校准后 |
|------|----------|--------|
| 意图识别 | 72 | **78** |
| 研判系统 | 74 | **80** |
| 报告中心 | 74 | **82** |
| 可视化 | 78 | **80** |
| **综合** | **~75** | **~82** |

**仍诚实扣分项**：Playwright 像素级报告回归；源库 PII 不可逆脱敏；法律维失信/诉讼无源表；图谱空白；报告章节 narration 是否单独计配额（当前不计入每日上限）。

### 建议下一步（第十三轮）

| 优先级 | 动作 | 说明 |
|--------|------|------|
| 🟠 P1 | **端到端冒烟** | Docker 全栈 → 对话（趋势/预警/评分/报告/邮件）→ 报告中心中文标题 |
| 🟡 P2 | **Playwright 像素快照** | 锁定 WeasyPrint 排版回归 |
| 🟡 P2 | **opensource submodule 化** | 见 `opensource/SUBMODULE_MIGRATION.md` |
| 🔵 P3 | **法律维完整覆盖** | 失信/被执行/诉讼需新源表 |
| 🔵 P3 | **意图 evaluate 会话用例** | `evaluate()` 仍无 session_context，followup 靠独立单测覆盖 |

---

## 十四、严格口径终审与第十四轮处置（2026-08-27）

**评分准则**：按「缺陷是否真实存在、是否会在上线出问题、测试是否兜住」判罚（非功能有无）。

### 严格审计缺陷核销表

| ID | 类型 | 问题 | 终审状态 | 处置 / 测试 |
|----|------|------|----------|-------------|
| C1 | 正确性 | synthesis 多轮自污染 | ✅ | `without_synthesis_claims` 不入库；`test_strict_audit_guards::test_synthesis_roundtrip_headline_not_polluted` |
| C2 | 正确性 | 舞弊预计算缺失误报 0/0 | ✅ | `coverage=precompute_missing` + 明确 claim；`test_fraud_precompute.py` |
| C3 | 正确性 | Benford 样本不足措辞 | ✅ | 「样本不足、未检验」；`test_strict_audit_guards::test_benford_insufficient_sample_wording` |
| C4 | 正确性 | it 子串误匹配 | ✅ | `\bit\b` / `it软件` 整词；`test_intent_engine::test_it_substring_*` |
| C5 | 正确性 | pyod 异常分方向 | ✅ | 修正 `decision_function` 映射（越低越异常）；`test_fraud_pyod.py` 证实 |
| R1 | 可靠性 | 付费锁定吞错 | ✅ | `PremiumReportLocked` 显式捕获；`test_strict_audit_guards::test_chat_premium_locked_*` |
| R2 | 可靠性 | email_report 不发邮件 | ✅ | `email_service.send_slice_report`；`test_strict_audit_guards::test_chat_email_report_*` |
| R3 | 可靠性 | 热路径同步 DB | ✅ | synthesis/covered/save 均 `run_blocking` |
| R4 | 可靠性 | `_to_float(None)` 崩溃 | ✅ | 返回 `0.0` |
| T1 | 可信度 | live 失败静默回落 mock | ✅ | `sendChatMessage` live/mock_with_llm 抛错；`dataSource.test.ts` |
| T2 | 可信度 | 法律维雷达误导 | 🔶 | 雷达轴标「低覆盖」+ `caveats` 文案；`ChatInlineChart` 展示脚注 |
| G1 | 完整性 | province 未消费 | ✅ | `run_judgment` 全链路 province 过滤 |
| G2 | 完整性 | 报告指标英文名 | ✅ | `_numeric_table_rows` 中文映射 |
| G3 | 完整性 | 历史标题裸文件名 | ✅ | `/report/list` 解析场景中文名 |
| G4 | 完整性 | followup 不重识别 | ✅ | 显式功能词/省份/行业下钻 |
| G5 | 完整性 | mock 地区意图死代码 | ✅ | `region_slice` 优先于 `risk_warning` |
| V1 | 可视化 | bar max:100 | ✅ | 已移除硬编码 |
| V2 | 可视化 | authenticity/fraud 仍柱状 | 🔶 | authenticity→pie；fraud 多信号→funnel |

### 严格口径重新估分（修复后）

| 方向 | 严格审计分 | 修复后估分 |
|------|------------|------------|
| 意图识别 | 68 | **76** |
| 研判系统 | 66 | **74** |
| 报告中心 | 62 | **78** |
| 可视化多样性 | 70 | **76** |
| **综合** | **66** | **~76** |

**仍扣分**：法律维数据源不完整（失信/诉讼无表）；图谱空白；Playwright 像素回归；`evaluate()` 无 session 上下文。

### 测试补强（针对「绿但坏」盲区）

| 新增文件 | 覆盖 |
|----------|------|
| `test_strict_audit_guards.py` | C1 / C3 / R1 / R2 |
| `test_fraud_precompute.py` | C2 |
| `test_fraud_pyod.py` | C5 |
| `dataSource.test.ts`（扩展） | T1 live 不回退 mock |

**验证**：`pytest -m "not llm"` **152**；vitest **37**。

---

## 十五、全系统严格终审（2026-08-27）

**方法**：通读反欺诈引擎、特征快照、前端数据源切换、39 个后端测试文件；按「缺陷是否真实、是否会在线上出问题、测试是否兜住」评分。

### 评分准则（与审计方一致）

| 扣分项 | 判罚 | 说明 |
|--------|------|------|
| 正确性缺陷 | −10~15/个 | 结论错、方向错、范围错 |
| 可靠性缺陷 | −7~10/个 | 静默降级、吞错、阻塞 |
| 可信度缺陷 | −8/个 | 演示数据冒充真实 |
| 完整性缺口 | −4/个 | 有入口无落地 |
| 测试盲区 | −3/个 | 缺陷在、测试绿 |

### 七维加权评分（100 分制）

| 维度 | 权重 | 得分 | 说明 |
|------|------|------|------|
| ① 架构与产品定位 | 20% | **78** | 匿名切片 + Claim/trace 骨架清晰；多 worker 会话/结论 PG 同步仍弱 |
| ② 正确性与数据链路 | 25% | **74** | ETL→core_metrics→引擎预计算链路完整；舞弊依赖 `engine_features` ETL |
| ③ 脱敏与合规 | 15% | **72** | API 无 PII；源库脱敏靠运维；`AUTH_REQUIRED` 默认 false |
| ④ 性能与可扩展 | 15% | **68** | 异步 PG + Redis 限流；SMTP/同步 PG 仍有阻塞点 |
| ⑤ 代码卫生 | 10% | **76** | 模块边界清楚；部分 API 宽 catch |
| ⑥ 可运维性 | 10% | **70** | Docker + health + init 脚本；无 compose 级 E2E CI |
| ⑦ 测试与验证 | 5% | **80** | 152 pytest + 38 vitest；缺全链路 `route_chat` 集成 |
| **加权合计** | | **~74** | 骨架与红线强；扣分在集成边界与生产信任线 |

### 四方向专项分（严格口径）

| 方向 | 分 | 一句话 |
|------|-----|--------|
| 意图识别 | **76** | 规则+LLM 复审、followup 功能/省/行业下钻已通；`evaluate()` 无 session |
| 研判系统 | **74** | 确定性引擎扎实；舞弊预计算缺失已显式报错；synthesis 污染已修 |
| 报告中心 | **78** | 切片 PDF/预览/邮件/历史齐全；章节可能复用陈旧 session 结论 |
| 可视化 | **76** | 6 类图型 + tree-shaking；法律维雷达有低覆盖脚注 |
| **综合** | **~76** | 新功能集成边界已收窄；生产信任线本轮再加固 |

### 系统优势（实打实）

1. **产品红线清楚**：匿名脱敏、不解析具名企业、Claim+trace 三层溯源、报告抗幻觉锚点
2. **研判不走 LLM 算数**：趋势/评分/舞弊/真实性/信号均为确定性引擎 + 预计算
3. **报告链路完整**：WeasyPrint/FPDF 双轨、场景模板、综合研判章、图表 PNG、历史中心
4. **测试体量真实**：39 个后端测试文件、11 个前端测试文件，覆盖意图/引擎/报告/严格审计回归
5. **运维可启动**：`docker-compose` 全栈、`init_all.ps1`、health 自检 MySQL 编码与 `engine_features` 计数

### 仍存缺陷（按严重度）

#### 已在本轮继续修复

| ID | 问题 | 处置 |
|----|------|------|
| F1 | live 仪表盘/预警静默回落 mock | ✅ `getDashboardSummary`/`fetchRiskWarnings` 失败抛错 |
| B1 | `chat.py` 异常返回 200 + `mock_fallback` | ✅ 改 503，不再伪造成功响应 |
| B2 | 会话 `province` 未持久化 | ✅ `ChatSessionRecord.province` + `store_session` |
| B3 | 报告邮件 SMTP 阻塞事件循环 | ✅ `run_blocking` 包装 |

#### 第十五轮「仍待迭代」处置跟踪

| ID | 严重度 | 问题 | 本轮状态 |
|----|--------|------|----------|
| D1 | 🟠 | `risk.py` summary/warnings 失败回落 mock | ✅ 改 **503**，不伪造 mock |
| D2 | 🟠 | PG 会话/结论写入失败静默 | 🔶 `session_store` 已 `warning`；多 worker 仍弱 |
| D3 | 🟠 | `engine_features` ETL 读空 | 🔶 pipeline 不再 DROP 业务表；engine 表仍同事务 DELETE+INSERT |
| D4 | 🟡 | LLM 双计数 | ✅ 报告 narration 不计；语义解析+回复路径已收敛 |
| D5 | 🟡 | ChatPanel 预警数据源不一致 | ✅ 统一 `fetchRiskWarnings` |
| D6 | 🟡 | `query_type`/样本量未在 UI 展示 | ✅ 第十九轮：`ChatPanel` + `QUERY_TYPE_LABELS` + `extractSampleN` |
| D7 | 🟡 | 法律维数据源不完整 | 🔶 脚注 + caveats；失信/诉讼仍无表 |
| D8 | 🔵 | 图谱无数据 | ✅ 个体图谱路径移除（隐私红线） |
| D9 | 🔵 | CI 无 compose / E2E | ✅ `smoke-test` + `e2e-test`（Playwright 3 spec） |

### 测试覆盖矩阵（摘要，第十七轮更新）

| 层 | 文件数 | 通过数 | 强项 | 盲区 |
|----|--------|--------|------|------|
| 后端 | 45 | **226** | 意图、语义层、配额降级、对比无样本 | 真 DB 全链路 `route_chat`、PG 持久化失败 |
| 前端 | 12 | **50** | dataSource 信任线、ingest、routes、Dashboard | ChatPanel 下载失败、query_type 未展示 |
| E2E | 3 spec | CI | core-loop、enterprise-chat、enterprise-profile | 像素级报告回归 |
| CI | 1 workflow | 4 jobs | pytest + vitest + smoke + e2e | design lint、LLM 仅 secret 时跑 |

### 与历史评分对照（完整）

| 轮次 | 综合（严格） | 要点 |
|------|--------------|------|
| 基线（改造前） | ~48 | 数据链路、报告断链 |
| 第五～六轮 | ~72～80 | 报告 KPI/归因、WeasyPrint |
| 第九轮 | ~76 | LLM、连接池、mock 收敛 |
| 第十一轮 | ~84（宽松）/ ~76（严格） | 可视化、CI |
| 第十二轮严格 | ~66 | 新集成层带病 |
| 第十三轮修复后 | ~82（四方向） | C1–C5/R1–R4 |
| 第十四轮严格 | ~76 | T1 信任线 |
| 第十五轮终审 | ~74（七维）/ ~76（四方向） | F1/B1 闭合 |
| 第十六轮（语义层初评） | ~79 | SemanticQuery；P0 未全闭 |
| 第十七轮 | ~82 | FAQ/对比/分段修复；225 pytest |
| **第十九轮（本轮）** | **~83** | 展示层 + 对比无样本 + 配额降级；226 pytest |

### 上线前检查清单

1. `python -m app.etl.pipeline` + `python -m app.etl.engine_features`（舞弊/真实性依赖）
2. 已有 PG 库：`ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS province VARCHAR(32);`（及 semantic 相关列若迁移）
3. 生产设 `AUTH_REQUIRED=true`、`JWT_SECRET`≥32、`CORS` 白名单
4. 确认 `LLM_DAILY_LIMIT` 与 Redis `REDIS_URL`（**注意**：`docker-compose.yml` 默认 1000，单测期望 100，本地 Docker pytest 需 `-e LLM_DAILY_LIMIT=100` 或统一默认值）
5. Docker 全栈冒烟：对话（FAQ/对比/分段/报告）+ 报告中心 + 个体画像
6. 配 `LLM_API_KEY` 时验证语义解析路径；无 key 时验证规则 FAQ/对比降级

### 结论（第十五轮，历史保留）

这是一套**骨架与红线明显强于平均演示项目**的风险研判系统。第十五轮时短板在 mock 回落与 compose E2E；**截至第十七轮，D1/D5/D8/D9 已闭合，对话层经语义升级后再提升约 +6 分**。详见第十六～十八节。

---

## 十六、人工对话 UX 弱点诊断（改造前基线，2026-08-27）

> 来源：严格人工多轮对话复测 + 代码走读（语义层改造**之前**）。用于对照第十七轮是否闭合。

### 五大弱点对照表

| # | 用户感知 | 根因（旧系统） |
|---|----------|----------------|
| 1 | 自然问法不工作 | `general` → 趋势 +「未命中维度」hint；无 FAQ/对比/列表意图 |
| 2 | 全是模板、无 LLM | `llm_configured: false` → `reply_source: template`；意图 LLM 仅在低置信度 |
| 3 | 冗长、无焦点 | 每轮 synthesis 前置 + `_template_from_claims` 倾倒全部 claims |
| 4 | 上下文只能靠 chip | chip = 完整新查询；真追问仅短句（「那方面呢」「那江苏呢」） |
| 5 | 引导层过多 | 底部 chip + followups + hint claims + 报告横幅叠层 |

### 典型失败问法（改造前）

| 问法 | 旧行为 |
|------|--------|
| 这个系统能做什么 | 信用分聚合或 general hint，非产品说明 |
| 江西和湖南制造业对比 | `general_overall` → 聚合，非 comparison |
| 列出各地区制造业 | 按行业列表，非按省份 |
| 报告怎么生成 | **`report` 意图** → 直接生成 PDF |
| 真实性从何而来 | `authenticity` 算法结论，非口径 FAQ |

### 设计层问题摘要

- 对话路由 = **功能×维度矩阵**（score/trend/report… × industry/region…），NL 必须先映射到矩阵槽位。
- `run_judgment` 的 `general` 分支硬编码 `Q_general_hint`，形成「死胡同」体验。
- LLM 仅负责**措辞**，不负责**问法理解**（无 SemanticQuery IR）。
- 会话上下文 = `function/dimension/industry/province`，无结构化查询对象继承。

---

## 十七、新一代语义层升级审计（第十六轮，2026-08-27）

**审计日期**：2026-08-27 · **综合估分**：≈ **79/100**（有 LLM）/ **~65**（无 LLM）

### 架构增量

| 模块 | 路径 | 职责 |
|------|------|------|
| SemanticQuery IR | `backend/app/schemas/semantic_query.py` | `lookup/aggregation/comparison/trend/ranking/distribution/segmentation/correlation/faq/methodology` |
| LLM 结构化解析 | `backend/app/services/llm_semantic_parser.py` | instructor/litellm → `SemanticQuery` |
| 规则校正与降级 | `backend/app/services/semantic_query.py` | `correct_semantic_query`、`intent_to_semantic_query`、`merge_followup` |
| FAQ 静态 KB | `backend/app/services/faq_kb.py` | 产品说明/导入/报告/隐私；`value=None` 防数字锚定 |
| 指标语义层 | `backend/app/services/metric_registry.py` | 口径字典、LLM dictionary |
| 执行分派 | `judgment_service.run_semantic_query` | `build_comparison_claims` 等 + `SEMANTIC_FOLLOWUPS` |
| 路由重写 | `chat_router.route_chat` | LLM 优先解析 → 语义执行；报告/邮件仍 `run_judgment` |
| 数据接入 | `ingest.py` + 前端 ingest UI | Excel/字段映射 → 指标层 |
| 个体画像 | `EnterpriseProfile.tsx` + `build_enterprise_claims` | 匿名个体下钻 + 个体 PDF |
| 会话持久化 | `session_store` | `last_semantic_query` JSON |

### 对话主路径（非 report/email）

```
recognize → [LLM parse | rule intent_to_semantic_query]
         → merge_followup（若追问）
         → run_semantic_query
         → generate_claim_reply（LLM 组织语言 / template）
         → persist_claims（without_synthesis_claims）
```

### 第十六轮七维评分

| 维度 | 得分 | 说明 |
|------|------|------|
| 数据可信 | 82 | 前后端 live 失败抛错 |
| 研判引擎 | 85 | 多 query_type + metric registry |
| 对话 UX | 72（有 LLM）/ 58（无 LLM） | 语义层上线；P0 缺陷未修 |
| 报告 | 84 | 切片 + 个体 |
| 安全 | 80 | 脱敏红线 |
| 测试 CI | 83 | 215 pytest + E2E |
| 架构运维 | 75 | ingest；PG 多 worker 弱 |
| **加权** | **~79** | |

### 第十六轮发现的 P0/P1 缺陷（改造前语义层）

| ID | 严重度 | 问题 |
|----|--------|------|
| S1 | P0 | 「报告怎么生成」被 `report` 关键词劫持，真出 PDF |
| S2 | P0 | `build_comparison_claims` 跨省对比未应用 `filters.industry_l1` |
| S3 | P1 | `segmentation` + `credit_score` 硬编码 `dimension=industry`，「各地区」答错维 |
| S4 | P1 | 无 LLM 时 FAQ 仅当 `query_type=faq`（LLM 产出），规则层未前置 `match_faq` |
| S5 | P2 | 分析类当轮仍前置 synthesis 展示 |
| S6 | P2 | UI 未展示 `query_type` / 样本量 |
| S7 | P2 | 对比缺样本省份静默 skip，无「无样本」claim |

### 第十六轮测试体量

- 后端 **215 passed**（`not llm`）
- 新增：`test_semantic_query.py`、`test_semantic_judgment.py`、`test_faq_kb.py`、`test_llm_semantic_parser.py`、`test_chat_semantic_router.py`、`test_enterprise_*`

---

## 十八、第十七轮严格终审（P0/P1 修复后，2026-08-27）

**审计日期**：2026-08-27 · **方法**：代码走读 + **225** pytest + **50** vitest + 活 API 六类问法复测

### P0/P1 修复核销

| ID | 修复 | 状态 | 证据 |
|----|------|------|------|
| S1 | `detect_faq_or_methodology` + `chat_router` FAQ 前置；问句/祈使分离 | ✅ | 活 API：`报告怎么生成` → `faq`，无 PDF；`test_route_chat_report_question_routes_to_faq_not_report` |
| S2 | 对比循环使用 `_sq_industry(sq)` | ✅ | 活 API：江西+湖南双省+spread；`test_comparison_province_applies_industry_filter` |
| S3 | `build_segmentation_claims` 用 `_sq_dimension(sq)` | ✅ | 活 API：按省份输出；`test_segmentation_credit_score_region_dimension` |
| S4 | `detect_rule_comparison` + FAQ 规则前置 | ✅ | `test_detect_rule_comparison_two_provinces_*`；`test_route_chat_no_llm_comparison` |
| S5 | — | 🔶 | synthesis 仍当轮展示；入库已过滤 |
| S6 | — | 🔶 | API 有 `query_type`；UI 未展示 |
| S7 | — | 🔶 | 缺样本省份仍 silent skip |

### 活 API 复测矩阵（Docker live + LLM）

| 问法 | query_type | function | 报告 | 判定 |
|------|------------|----------|------|------|
| 这个系统能做什么 | faq | general | 否 | ✅ |
| 报告怎么生成 | faq | general | 否 | ✅ |
| 江西和湖南制造业信用分对比 | comparison | benchmark | 否 | ✅ 双省+差值 |
| 列出各地区制造业 | segmentation | score | 否 | ✅ 按地区 |
| 生成报告 | — | report | 是 | ✅ 正常出切片报告 |
| 真实性得分怎么算的 | methodology | — | 否 | ✅ registry 口径 |

### 五大弱点再对照（第十七轮）

| # | 弱点 | 本轮结论 |
|---|------|----------|
| 1 | 自然问法 | **基本闭合**（LLM + 规则 FAQ/对比）；「各地区信用分对比」仍非双值 comparison（设计：需 ≥2 明确实体） |
| 2 | 全模板 | **有 LLM 时闭合**；无 key 仍有规则 FAQ/对比降级 |
| 3 | 冗长 | **FAQ/口径简洁**；分析类多 claim + synthesis 展示仍偏长 |
| 4 | 上下文 | **部分闭合**（`merge_followup` + `last_semantic_query`）；追问句式仍偏窄 |
| 5 | 引导过多 | **部分闭合**（`SEMANTIC_FOLLOWUPS`）；chip + 徽章仍叠层 |

### 第十七轮七维加权评分

| 维度 | 权重 | 得分 | 较第十五轮 |
|------|------|------|------------|
| ① 架构与产品定位 | 20% | **80** | +2（语义 IR、ingest、个体画像） |
| ② 正确性与数据链路 | 25% | **78** | +4（对比 filter、分段维度、risk 503） |
| ③ 脱敏与合规 | 15% | **72** | 持平 |
| ④ 性能与可扩展 | 15% | **68** | 持平 |
| ⑤ 代码卫生 | 10% | **78** | +2（语义模块边界清晰） |
| ⑥ 可运维性 | 10% | **77** | +7（smoke + E2E CI） |
| ⑦ 测试与验证 | 5% | **85** | +5（225 pytest、语义单测） |
| **加权合计** | | **~78** | +4 |

### 第十七轮四方向专项分

| 方向 | 分 | 一句话 |
|------|-----|--------|
| 产品对话体验 | **82** | P0 闭合；展示层与追问广度仍弱 |
| 工程可信 | **81** | 503 信任线、Claim 红线、FAQ 无数字 |
| 研判深度 | **86** | 8+2 query_type、个体、ingest、metric registry |
| 交付运维 | **78** | CI 四 job；Docker LLM limit 与单测不一致 |
| **综合** | **~82** | 较第十五轮 +6；较第十六轮 +3 |

### 仍存缺陷（第十七轮诚实保留）

| 优先级 | 问题 | 说明 |
|--------|------|------|
| P1 | `LLM_DAILY_LIMIT` 环境不一致 | compose 默认 1000，`test_rate_limiter` 期望 100；Docker 内 pytest 可能 1 failed |
| P1 | 对比缺样本无显式 claim | `avg is None` 省份静默跳过 |
| P2 | ChatPanel 未展示 query_type/样本 n | API 已有字段 |
| P2 | 分析类 synthesis 当轮展示 | `persist_claims` 已去 synthesis |
| P2 | `is_followup_query` 句式窄 | 长自然追问不一定 merge |
| P3 | PG 会话多 worker | `session_store` warning 级；跨 worker 上下文仍可能丢 |
| P3 | `engine_features` DELETE+INSERT | 单事务；极端并发读可能见空窗 |
| P3 | 演示库 n=193 | 跨省对比样本极小（如湖南制造 n=1） |
| P3 | `AUTH_REQUIRED` 默认 false | 生产需显式配置 |

### 数据接入与指标语义层（本轮纳入审计范围）

| 能力 | 状态 | 说明 |
|------|------|------|
| Excel 上传 / 字段映射 | ✅ | `ingest.py` + 分层映射（精确/模糊/LLM） |
| `canonical_metrics` | ✅ | `metric_registry` + `/metrics` API |
| 前端 ingest UI | ✅ | vitest `ingest.test.ts` |
| ETL pipeline | ✅ | 不再 DROP 结论/会话表；`engine_features` 独立步骤 |

### 个体画像与 E2E 扩展

| 项 | 状态 |
|----|------|
| `EnterpriseProfile.tsx` | ✅ 路由 + 画像 claims |
| 个体深度报告 PDF | ✅ `generate_enterprise_report` |
| `e2e/tests/core-loop.spec.ts` | ✅ CI |
| `e2e/tests/enterprise-chat.spec.ts` | ✅ CI |
| `e2e/tests/enterprise-profile.spec.ts` | ✅ CI |

### 建议下一步（第十八节续）

| 优先级 | 动作 |
|--------|------|
| P1 | 统一 `LLM_DAILY_LIMIT`（compose 默认 100 或测试读 env） |
| P1 | 对比缺样本显式 claim（「某省无样本」） |
| P2 | ChatPanel 展示 `query_type` + 样本量脚注 |
| P2 | 可选：分析类当轮不前置 synthesis |
| P3 | 追问 merge 扩展或 LLM 槽位继承 |
| P3 | `opensource` submodule 化（见 `opensource/SUBMODULE_MIGRATION.md`） |

### 第十七轮结论

项目在**确定性研判 + Claim 溯源 + 报告抗幻觉**红线之上，完成了对话层从「意图矩阵」到 **SemanticQuery IR** 的升级，并在一轮聚焦修复中闭合了人工复测最伤体验的 **FAQ 劫持、对比 filter、分段维度** 三个代码级缺陷。按严格口径 **~82/100**；若完成展示层与 env 一致性，对话维可冲击 **~85**，综合 **~84**。

---

## 附录 A · 严格审计缺陷主索引（C/R/T/G/V + S + D）

| 类别 | ID 范围 | 代表项 | 总体状态 |
|------|---------|--------|----------|
| 正确性 C | C1–C5 | synthesis 污染、舞弊预计算、Benford 措辞、it 子串、pyod 方向 | ✅ 全闭合 |
| 可靠性 R | R1–R4 | 付费锁定、邮件报告、同步 DB、`_to_float` | ✅ 全闭合 |
| 可信度 T | T1–T2 | live mock 回落、法律雷达误导 | ✅ T1；🔶 T2 脚注 |
| 完整性 G | G1–G5 | province、中文表、followup | ✅ 全闭合 |
| 可视化 V | V1–V2 | bar max、图表类型 | ✅/🔶 |
| 架构债 D | D1–D9 | mock 回落、PG、ETL、CI | D1/D4/D5/D6/D8/D9 ✅；D2/D3/D7 🔶 |
| 语义层 S | S1–S7 | FAQ 劫持、对比 filter、分段维度 | S1–S4 ✅；S5 🔶；S6/S7 ✅（第十九轮） |
| 配额 Q | Q1 | LLM 日配额耗尽行为 | ✅ `llm_available()` 降级（第十九轮） |

## 附录 B · 关键验证命令

```powershell
# 后端（本地或 Docker，注意 LLM_DAILY_LIMIT）
cd backend
$env:PYTHONPATH="."
python -m pytest tests -m "not llm" -q

# Docker 后端（避免 rate_limiter 失败）
docker compose run --rm --no-deps -e LLM_DAILY_LIMIT=100 -v ${PWD}/backend:/app backend python -m pytest tests -m "not llm" -q

# 前端
cd frontend && npx vitest run && npx vite build

# 健康与活对话
curl http://127.0.0.1:8000/api/v1/health
# PowerShell UTF-8 对话示例
$body = '{"query":"报告怎么生成"}'
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/chat -Method POST `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) `
  -ContentType "application/json; charset=utf-8"

# E2E（需 backend compose 已启）
cd e2e && npx playwright test
```

## 附录 C · 入口与文档

| 页面 | URL |
|------|-----|
| 前端 | http://localhost:5173/ |
| 对话 | http://localhost:5173/chat |
| 个体画像 | http://localhost:5173/enterprise/:id |
| 报告预览 | http://localhost:5173/report/preview |
| API 文档 | http://localhost:8000/docs |
| 健康检查 | http://localhost:8000/api/v1/health |

---

---

## 十九、第十九轮严格复审（2026-08-27）

**审计日期**：2026-08-27 · **方法**：全量 pytest/vitest + Docker 活数据 health + **七类活 API** + 多轮追问 + 第十七轮遗留项逐项复验

### 与第十七轮增量（本轮新闭合）

| ID | 问题 | 状态 | 证据 |
|----|------|------|------|
| S7 | 对比缺样本静默 skip | ✅ | `build_comparison_claims` 产出「暂无样本数据」claim；`test_semantic_judgment` 断言「湖南暂无样本」 |
| D6 / S6 | UI 未展示 query_type / 样本量 | ✅ | `ChatPanel`：`QUERY_TYPE_LABELS` + `extractSampleN` 徽章；`labels.ts` |
| P1（部分） | `test_rate_limiter` 与 compose limit 硬编码冲突 | ✅ | 测试改读 `LLM_DAILY_LIMIT`；Docker 内 **226 passed** 无需 `-e` 覆盖 |
| Q1 | 配额耗尽硬失败 | ✅ | `llm_available()`：耗尽时降级规则/模板；`test_llm_available_respects_daily_quota` |

### 活 API 复测矩阵（`llm_configured: true`，193 企）

| 问法 | query_type | function | claims | 报告 | 判定 |
|------|------------|----------|--------|------|------|
| 报告怎么生成 | faq | general | 1 | 否 | ✅ 未劫持 |
| 江西和湖南制造业信用分对比 | comparison | benchmark | 3 | 否 | ✅ 双省+差值/无样本说明 |
| 列出各地区制造业 | segmentation | score | 9 | 否 | ✅ 按地区 |
| 生成报告 | — | report | 2 | 切片 | ✅ |
| 你好 | faq | general | 1 | 否 | 🔶 LLM 可能过度路由 FAQ（体验偏宽，非崩溃） |
| 分析制造业信用分 → 那江苏呢 | aggregation → aggregation | score | 9 → 1 | 否 | ✅ 追问聚焦 1 条 |

### 测试验证（本轮实测）

| 层 | 通过数 | 备注 |
|----|--------|------|
| 后端 `pytest -m "not llm"` | **226** | +1（`test_llm_available_respects_daily_quota`）；Docker 默认 env 全绿 |
| 前端 vitest | **50** | 12 文件 |
| 活 health | ok | `enterprise_count=193`，`engine_features_count=193`，Redis 连通 |

### 第十九轮七维加权评分

| 维度 | 权重 | 得分 | 较第十七轮 |
|------|------|------|------------|
| ① 架构与产品定位 | 20% | **81** | +1（语义 IR + ingest + 个体画像稳定） |
| ② 正确性与数据链路 | 25% | **80** | +2（对比无样本显式、risk 503 仍绿） |
| ③ 脱敏与合规 | 15% | **72** | 持平 |
| ④ 性能与可扩展 | 15% | **68** | 持平 |
| ⑤ 代码卫生 | 10% | **79** | +1（配额降级路径清晰） |
| ⑥ 可运维性 | 10% | **78** | +1（测试与 compose env 对齐） |
| ⑦ 测试与验证 | 5% | **86** | +1（226 + 配额单测） |
| **加权合计** | | **~79** | +1 |

### 第十九轮四方向专项分

| 方向 | 分 | 较第十七轮 | 一句话 |
|------|-----|------------|--------|
| 产品对话体验 | **84** | +2 | query_type/样本可见；FAQ/对比/分段仍稳 |
| 工程可信 | **82** | +1 | 配额耗尽软降级；Claim 红线未退步 |
| 研判深度 | **86** | 持平 | 语义执行层 + metric registry + ingest |
| 交付运维 | **79** | +1 | 226 pytest Docker 全绿 |
| **综合（四方向均值）** | **~83** | +1 | 展示与边界抛光轮 |

> 说明：七维加权（~79）与四方向综合（~83）口径不同——前者含性能/合规等「基建」拉低项；**对外汇报建议用四方向综合 ~83**，与演进表一致。

### 五大对话弱点（第十九轮）

| # | 结论 |
|---|------|
| 1 自然问法 | **基本闭合**；闲聊偶入 FAQ（🔶） |
| 2 全模板 | **有 LLM 闭合**；配额耗尽自动降级模板 |
| 3 冗长 | FAQ/口径简洁；分析首轮仍可能多 claim + synthesis 展示（🔶） |
| 4 上下文 | **部分闭合**；「那江苏呢」→ 1 条；长句追问仍窄 |
| 5 引导过多 | query_type/样本徽章减负；chip + followups 仍存 |

### 仍存缺陷（诚实保留）

| 优先级 | 问题 |
|--------|------|
| P2 | 分析类当轮仍可能前置 synthesis 展示（`persist_claims` 已过滤） |
| P2 | `is_followup_query` 句式窄；非短追问不一定 `merge_followup` |
| P2 | 闲聊/「你好」可能被 LLM 解析为 FAQ（过宽路由） |
| P3 | compose `LLM_DAILY_LIMIT` 默认 1000 vs 代码默认 100（测试已对齐 env，运维文档需注明） |
| P3 | PG 多 worker 会话；`engine_features` DELETE+INSERT；演示 n=193 |
| P3 | `AUTH_REQUIRED` 默认 false；失信/诉讼无法律源表 |

### 第十九轮结论

第十七轮之后的改动主要是 **体验抛光与边界硬化**：用户在气泡里能看见 **查询类型与样本量**；跨省对比不再 silently 丢省；LLM 日配额耗尽时 **整条链路软降级** 而非异常中断。无新的 P0 回归。严格口径 **~83/100**（四方向）；若收敛 synthesis 展示与追问广度，可冲击 **~85**。

---

*文档维护：每轮严格审计后更新「综合评分演进」表、对应章节处置状态与验证通过数。*



---

---

# 十九、v1.0 → v2.0（明鉴01）全量差异审计（2026-08-28）

> 本节省略号「v2.0」指他人优化版（压缩包 `明鉴01.zip`，现已解压至 `2.0/`）；「v1.0」指工作区原始版本（现位于 `1.0/`，含完整 git 历史）。

## 结论速览

**核心事实：所谓「优化版」在后端算法/研判引擎层面没有任何改动。** 对整个 `backend/` 目录逐文件 `diff --strip-trailing-cr`，全部 121 个源码文件**逻辑零差异**——30 个「字节不同」的文件，其差异全部只是行尾符 CRLF → LF（字节差恰等于各文件行数）。评分权重、真实性阈值、Benford/MAD 阈值、反欺诈信号、报告模板、抗幻觉锚点、结论持久化——均与原版逐字一致。

真正发生变化的只有四类：

| 维度 | v1.0 | v2.0 | 性质 |
|---|---|---|---|
| 前端 | `frontend/` 子目录，深色科技风 | 根目录 monorepo，暖色手绘/吉祥物风 | **完全重写** |
| 种子数据 | 陈旧 schema（`enterprise_name`/`public_revenue`/市值/估值） | 追平模型的 schema | **修正（老 seed 早已脱节）** |
| LLM 供应商 | DeepSeek | 被改为小米 MiMo（已改回 DeepSeek） | 配置切换（本任务已还原） |
| 行尾 | CRLF | LF | 格式化 |

---

## 一、数据核验（任务 1）

### 1.1 逐文件核验结果

| 文件 | 核验方式 | 结论 |
|---|---|---|
| `backend/seed_data.py` | sha256 | **完全一致**（`bb684649…d33d48`） |
| `backend/app/models/core_metrics.py` | diff | **完全一致** |
| `backend/app/**/*.py`（全部 121 个） | `diff --strip-trailing-cr` | **完全一致**（仅行尾差异） |
| `backend/seed_data.sql` | sha256 | **不同**：`65123e37…`(v1.0) → `faa2f114…`(v2.0)，但字节数相同（233953 B） |

### 1.2 seed_data.sql 的实质差异

- **企业主体不变**：`core_metrics` 均为 200 行，企业 ID `ENT001–ENT200` 集合**逐一对应、完全相同**；行业/地区/规模标签值不变。
- **schema 追平模型**：v2.0 的表结构与早已存在的 `core_metrics.py` 一致：
  - 新增：`display_label`（取代 `enterprise_name`）、`scale_label`、`loan_cnt`、`loan_amount`、`invoice_revenue`、`finance_revenue`（取代 `public_revenue`）、`invoice_cnt`、`red_invoice_cnt`、`social_months`、`profit_margin`、`cash_flow_net`、`cash_flow_level`
  - 删除：`market_cap`、`pe_ratio`、`roe`、`z_score`、`z_score_level`、`public_revenue`、`enterprise_name`
  - 类型变化：`credit_level CHAR(1)` → `VARCHAR(10)`；`revenue_deviation NUMERIC(5,4)` → `NUMERIC(8,4)`；`industry_l2 VARCHAR(50)` → `VARCHAR(80)`
- **INSERT 写法更稳**：v1.0 用位置式 `INSERT INTO core_metrics VALUES (...)`（易错位）；v2.0 用显式列名 `INSERT INTO core_metrics (col1,col2,…) VALUES (...)`。
- **指标值整体重生成**：`vat_revenue`/`revenue_yoy`/`profit_yoy`/`debt_ratio`/`credit_level` 等取值与 v1.0 不同（例如 ENT001 `vat_revenue` 3,589,558,315 → 2,348,292,475）。
- **legal_events 多 10 行**：307 → 317。

### 1.3 关键判定：v1.0 的 seed 才是「陈旧文件」

`core_metrics.py` 模型在两个版本中**完全相同**，且其列定义（`display_label`/`scale_label`/`loan_cnt`/`invoice_revenue`/`finance_revenue`/`cash_flow_net`…）**早已匹配 v2.0 的 schema**，并带向后兼容只读属性（`enterprise_name` → `display_label` 等）。`seed_data.py`（生成脚本）也早已产出这些新列。**即：v2.0 是把陈旧的 `seed_data.sql` 同步回与模型/ETL 管线一致的 schema，而非把数据改坏。** v1.0 的旧 seed 因缺列，会让 `authenticity_engine`/`fraud_engine` 里大量 `getattr(…, 默认值)` 静默回落 0/None，导致交叉口径与 Benford 样本不足。

### 1.4 缺失的原始数据

v1.0 的 `data/` 目录含：`数据.sql`（**1.95 GB** 原始 MySQL 全量数据）、`建表.sql`（建表 DDL）、`财税票数据字典-20250417.xlsx`（数据字典）、`mysql-init/`（MySQL 初始化脚本）。**v2.0 全部缺失**（且 `docker-compose.yml` 仍引用 `./data/mysql-init`，见 §5.1）。即 v2.0 丢失了真实业务源数据与数据字典，仅保留 200 家匿名模拟种子。

**核验结论：导入数据不完全一致。** 主体（200 家企业 ID）一致；schema 与指标值不同（v2.0 为追平模型的修正版）；v2.0 缺 `data/` 原始源库与数据字典。

---

## 二、LLM / API 变更（任务 2）

- v2.0 的 `backend/.env` 被改为**小米 MiMo**：`LLM_MODEL=xiaomi/mimo-v2.5-pro`、`LLM_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1`、另一枚真实 key。
- v2.0 的 `README.md` 却仍写「LiteLLM + DeepSeek」——**文档与配置自相矛盾**。
- **已按任务要求还原为 v1.0 的 DeepSeek**：
  ```
  LLM_API_KEY=sk-****（已脱敏，需轮换）
  LLM_MODEL=deepseek-v4-pro
  LLM_BASE_URL=https://api.deepseek.com
  LLM_FALLBACK_MODEL=deepseek-v4-flash
  ```
  全仓已无 `xiaomi/mimo` 残留。LLM 配置仅由环境变量驱动（`llm_reply.py` 默认值本就是 `deepseek-v4-pro`），故该改动即生效。
- ⚠️ **安全**：两个版本的 `.env` 均含**真实 API key 明文**（且已随 zip 分发），应尽快轮换，并确认 `.gitignore` 覆盖 `.env`。

---

## 三、后端代码：零逻辑变更

v1.0 与 v2.0 的 `backend/app/**` 逐文件一致。变更文件清单（30 个）仅行尾差异：`judgment_service.py`、`slice_report.py`、`etl/pipeline.py`、`fraud_engine.py`、`authenticity_engine.py`、`conclusion_store.py`、`report_templates.py`、`hallucination_guard.py`、`enterprise_id.py`、`engine_features_store.py`、`db/mysql.py`、`db/mysql_encoding.py`、`db/urls.py`、`pinyin_util.py`、`scripts/check_encoding.py`、`scripts/redact_mysql_pii.py`、`models/engine_store.py`、`schemas/claim.py`、若干测试等。

结论：**「优化」未触及任何分析算法**，MySQL 采集/ETL/脱敏/拼音/特征工程/研判评分逻辑全部原样保留。

---

## 四、前端：完全重写（v2.0 的核心增量）

| 方面 | v1.0 | v2.0 |
|---|---|---|
| 位置 | `frontend/` 子目录 | 仓库根 `src/`（monorepo 化） |
| 状态管理 | 组件内 `useState/useEffect` | Zustand（`authStore/chatStore/overviewStore/reportStore`） |
| API 层 | `src/lib/*`（api/apiClient/mockChat/mockSample/dataSource/ingest…） | `src/api/*` + `src/types/*` + `src/utils/*` |
| UI 组件 | shadcn 风格（badge/button/card… 小写） | 自研 UI kit（Badge/Button/Card/Chip + CuteEyeLogo/SketchIcons/ResearchAssistantCharacter/AnimatedCharacters/AnimatedNumber/InteractiveHoverButton） |
| 图表 | 手写 `echartsCore` 柱状图 | `echarts` 5.5 + `echarts-for-react`（Bar/Line/Pie/Radar/Heatmap + chartTheme） |
| 页面 | Dashboard/ChatPanel/EnterpriseProfile/DataIngest/Login/Register/ReportHistory/ReportPreview | OverviewPage/ResearchCenter/EnterprisePage/DataIngestPage/LoginPage/RegisterPage/ReportCenter/ReportPage + **新增 FraudPage、AuthenticityPage** |
| 导航 | 底部 Tab | 顶部 Header + AnimatePresence 转场 |
| 设计方向 | 深色科技风 | 暖色「手绘/几何吉祥物」风（framer-motion 全面动画） |
| 依赖栈 | React 19 / router v7 / echarts 6 / vite 6 | React 18 / router v6 / echarts 5.5 / vite 5（**降级**） |

新增能力：反欺诈独立页（进销错配/红字发票/集中度）、经营真实性独立页、报告中心（列表+内嵌预览+email 发送）、研究助手角色动画、登录页「偷看密码」动画。

---

## 五、部署与配置问题

### 5.1 docker-compose.yml 陈旧且失效（P0）
v2.0 的 `docker-compose.yml` 与 v1.0 **逐字节相同**，仍声明：
- `mysql` 服务挂载 `./data/mysql-init`（**v2.0 无此目录**）；
- `frontend` 服务 `build: ./frontend`（**v2.0 前端在根目录，且无 frontend Dockerfile**）。

即 v2.0 直接 `docker compose up` 会因缺少 `data/` 与 `frontend/` 而失败。v2.0 实际改用 `start.sh/bat` 走本机 Python + Node 启动。

### 5.2 start.sh prod 静态托管未接线
`start.sh prod` 把 `dist/` 拷到 `backend/static` 后，脚本自己打印警告「需要在后端 main.py 中添加静态文件托管路由」——生产模式静态托管实际未完成。

### 5.3 package.json 自引用依赖（P1）
`"tax-risk-analysis": "file:"` —— 指向自身的空引用，`npm install` 可能报错或行为异常，应删除。

### 5.4 vite.config.ts 硬编码代理
v2.0 `vite.config.ts` 硬编码 `proxy → http://localhost:8000`、端口 3000，无 `VITE_API_URL` 环境变量加载；v1.0 用 `loadEnv` + `.env.development`（`VITE_API_URL=http://127.0.0.1:8001`）。多环境（如 E2E 走 8001）适配能力退化。

### 5.5 其他
- `backend/Dockerfile` 内容与 v1.0 一致，仅 CRLF→LF。
- v2.0 打包时夹带了 `.node/`（70 MB node.exe）、`node_modules/`、`__pycache__/`（已按要求剔除）。

---

## 六、测试与质量回归

- **前端测试全删**：`vitest.config.ts`、`src/test-setup.ts`、`src/**/__tests__/*`（12 个测试文件，覆盖 ErrorBoundary/StateViews/api/constants/dataSource/ingest/labels/routes/utils/Dashboard/Login/ReportPreview）以及 `package.json` 的 `test`/`lint` 脚本、vitest/@testing-library/jsdom 依赖全部移除。
- **ESLint 与 design-doctor 全删**：`.eslintrc.json`、`scripts/lint-design.mjs`、`.design-doctor/` 移除。
- **E2E 目录整体丢失**：v1.0 的 `e2e/`（Playwright 4 spec）在 v2.0 中不存在。
- **后端测试保留**：`backend/tests/` 仍在（且与 v1.0 一致，仅行尾差异）。

---

## 七、遗留技术债（两版共有，v2.0 未清理）

1. `app/services/mock_data.py` 仍用旧字段名 `enterprise_name`/`public_revenue`/`market_cap`/`pe_ratio`/`roe`/`z_score`——mock 分支产出与真实 schema 不匹配。
2. 兼容层是只读 property + 大量 `getattr(m, "display_label") or getattr(m, "enterprise_name")` 兜底，字段迁移不彻底。
3. `LLM_DAILY_LIMIT=1000`（`.env.example`）与应用默认 100（`rate_limiter.py`）不一致，需确认是否有意放宽。
4. `authenticity_engine` 的行业 Benford 用「每企业单值样本」（finance OR vat OR invoice 取一），小样本行业恒 `insufficient_sample`，Benford 统计意义弱。

---

## 八、v2.0 改进点清单（按优先级）

**P0（阻塞上线）**
1. 修复 `docker-compose.yml`：改为前端根目录构建 + 移除/补齐 `data/mysql-init` 挂载，或明确弃用 Docker 仅走 `start.sh`。
2. 轮换并妥善保管 `.env` 里的真实 API key（两版均泄漏）。
3. 补齐 `start.sh prod` 的后端静态托管路由，或改用 nginx 分别托管。

**P1（质量/正确性）**
4. 恢复前端测试与 ESLint（或至少为新增的 Fraud/Authenticity/Research 页面补冒烟测试）。
5. 删除 `package.json` 自引用 `"tax-risk-analysis": "file:"`。
6. 恢复 vite 的环境变量加载（`VITE_API_URL`），消除硬编码 8000。
7. 清理 `mock_data.py` 旧字段名，统一到新 schema。

**P2（打磨）**
8. 收敛 `enterprise_name → display_label` 兼容层，确定单一字段来源。
9. 对齐 `LLM_DAILY_LIMIT` 文档值与应用默认值。
10. 若需真实数据，把 `data/`（源库 + 数据字典）回填至 v2.0，而非仅 200 家模拟种子。
11. 重新设计真实性 Benford 为「发票/明细金额序列」，提升统计意义。

---

## 九、整体评估

| 维度 | 评级 | 说明 |
|---|---|---|
| 前端体验/视觉 | ▲ 明显提升 | 全新 UI kit、动画吉祥物、ECharts 图表、新增反欺诈/真实性独立页 |
| 前端工程化 | ▼ 倒退 | Zustand 结构更清晰，但删光测试/ESLint、硬编码代理、依赖栈降级 |
| 后端算法 | ＝ 无变化 | 与 v1.0 逐字一致，未产生「优化」 |
| 数据 | ▲ 局部修正 | seed 追平模型（老 seed 本就脱节）；但丢失 1.95 GB 源库与数据字典 |
| 可部署性 | ▼ 倒退 | docker-compose 失效、prod 静态托管未接线 |
| 文档 | ▼ 倒退 | 仅剩 README，审计/指南/路线图全部丢失（本任务已回迁） |

**总评**：v2.0 的价值集中在**前端视觉与交互重构**，后端无实质「优化」。作为可交付版本，当前最大风险是**可部署性（docker-compose 失效）与测试/质量保障缺失**；作为复用型数据分析系统，报告系统（最大卖点）的前端体验确有提升，但需先补齐 P0/P1 项才具备上线条件。

---

*本节由 1.0↔2.0 全量审计自动生成（2026-08-28）。上一轮（v1.0）审计严格口径 ≈ 83/100；v2.0 未做逐项复测，故本节不给出综合评分，仅列差异与改进项。*

---

## 二十、2.0 严重缺陷修复轮（2026-08-28）

**审计触发**：全面审计 2.0 后按 T1→T2→C1→T3→S1→Q1 顺序落地修复。  
**验证**：前端 vitest **3 passed**；Docker 后端 `test_faq_kb` + `test_semantic_query` **20 passed**。

### 已闭合

| ID | 问题 | 处置 |
|----|------|------|
| **T1** | Fraud/Authenticity：对象当数组→空表；失败填 demoData | `normalizeFraudRows` / `normalizeAuthenticityRows`；页面错误态+重试；后端 `top_flags`/`top_suspicious` 补齐 `enterprise_id` 等字段 |
| **T2** | ReportCenter 空列表回落 `mockReports` | 删除伪造列表；`listError` + 空态/失败态 |
| **T3** | Overview 失败变全 0 | `OverviewUnavailableError` 上抛；store/页面展示错误 |
| **C1** | FAQ 裸词劫持研判 | `faq_kb` 关键词收紧；单测防「各地区数据怎么样」等 |
| **S1** | `enterprise_id` 未持久化 | `ChatSessionRecord.enterprise_id` + `_persist`/`_load`；启动 `ALTER TABLE … ADD COLUMN IF NOT EXISTS` |
| **A2（部分）** | 登录页硬编码密码 | 仅填充邮箱，密码不再写进前端 |
| **Q1（部分）** | 无前端测试/CI | `vitest` + `riskNormalize.test.ts`；`2.0/.github/workflows/ci.yml`；`Dockerfile.prod` + `nginx.conf` |

### 仍开（下一轮）

| ID | 严重度 | 说明 |
|----|--------|------|
| A1 | P0 | `AUTH_REQUIRED` 默认仍 false（演示可开，生产须显式 true） |
| D2 | P0 | compose 默认仍用 vite `Dockerfile`；生产请切 `Dockerfile.prod` |
| C2 | P1 | 真实性/舞弊 segmentation 地区粒度残留 |
| C3 | P1 | 对话 heatmap 等图表类型前端丢弃 |
| E1/S2 | P1 | engine_features DELETE+INSERT；Redis 静默内存降级 |

### 回归注意

- 已有 PG：启动时会尝试 `ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS enterprise_id`。
- 生产前端：`docker compose build --build-arg` 或将 `dockerfile` 改为 `Dockerfile.prod`（映射 80→3000 需同步改 ports）。
- 若 CI 仓库根在 `risk-assessment/`，请将 workflow 迁到仓库根 `.github/workflows/` 并设置 `working-directory: 2.0`。

---

*文档维护：每轮严格审计后更新「综合评分演进」表、对应章节处置状态与验证通过数。*
