# 明鉴01 · 报告系统交接文档（Cursor 接手）

> 生成时间：2026-08-30（机制层方向补强同日）。这份文档是给下一个接手方（Cursor / 新 agent）的定向说明，不含规范细节，细节都在代码和 memory 里。原则仍是「边做边固化到仓库」——**代码即规则，不另起 PRD**。

---

## 〇、机制层北星（先读这一节，再动代码）

L0→L1 已干净（193 家 live、指标字典已建）。**痛点在 L2/L3/L4 生成机制**：本质是 NLG 经典架构错误——**内容决定（content determination）与表达实现（surface realization）没有走同一条管道**。业内叫法：Reiter & Dale 管道被拆坏。

> 规则引擎产出「带条件的 claim」→ 渲染层另起炉灶写死文案 → claim 的条件判定被绕过 → 文字与数据打架。

**这不是数据问题，也不是调 prompt 能根治的问题**——是架构边界没有强制：渲染层「能」绕过 claim。根治原则一句话：

**渲染层唯一输入是 document plan（claim / message 列表）；文本只能是 keyed-by-claim 的条件片段；没有 claim 就没有文本。**

### 强制三段式管道（不可越界）

```
L1 指标语义层（单一事实源：metric + 阈值 + 标签）
  → 文档规划器（规则引擎，确定性产出 claim 列表 + 顺序 + 结构）
  → 表达实现（条件片段模板；LLM 仅润色，理想态受约束解码）
  → 校验器（渲染前断言 + CI 门禁）
  → L4 版式
```

| 痛点 | 借鉴模块/思想 | 出处 | 本仓库落点 |
|---|---|---|---|
| 三张皮脱节 | Reiter & Dale：content determination → structuring → lexicalization → surface realization | *Building NLG Systems* (Cambridge) | claim = NLG **message**；规划器产 message 列表；realizer **只吃** message |
| 阈值散落 | MetricFlow / dbt Semantic Layer「define once, use everywhere」 | dbt MetricFlow / Semantic Layer | `metric_registry` + `financial_benchmarks` 收成单一事实源 |
| LLM 幻觉 | 约束解码（XGrammar / Outlines / Guidance / LMQL） | Awesome-LLM-Constrained-Decoding | LLM 只做 surface realization；数字/结论必须来自传入 claim（当前：sanitize + validate；下一步可加 schema 约束解码） |
| 人工通读 PDF | 渲染前钩子 + 渲染后 guardrail | 本仓 `validate_report_chapters` | 升级为 CI 门禁，取代抽样通读 |

### 重要警告（继承时别踩）

1. **不要整体采用 RosaeNLG**：官方 2026-03 弃档，且是 Node.js；借鉴「模板 NLG / message→片段」思想即可，不引依赖。
2. **论文侧强证据**（规划-再-生成是对的）：
   - Macro Planning（Puduppully & Lapata, 2021）：先确定性宏观规划，再生成 → 更 factual、更可控。本仓已有 `radar_dimensions_for_chapters` + `_build_context_from_spec`。
   - 多智能体分治（Osuji et al., INLG 2025）：Orchestrator 拆内容排序/结构/表面实现 + Guardrail —— 现代 LLM 版 Reiter&Dale。
   - Fact-Guided / 词级幻觉控制：对齐词 vs 未对齐词显式区分；与「数字必须有 claim 锚点」同构。
3. **与专利 6651219 同构**：decisional statements → logic path → 文本片段；即 message/document-plan 的正统实现。

### 接手铁律（机制约束）

- **禁止**在 `slice_report` / `report_templates` / HTML 模板新增「无 claim 条件」的整段风险话术。
- **禁止**把评分、阈值、风险等级判定交给 LLM；LLM 只润色已有 claim。
- **禁止**再写「先调 prompt 修一版报告」当主路径；缺口一律补管道（规划器 / 字典 / 校验器）。
- 五个闭环 = 在补这条管道；**后续工作按管道收敛，不是继续打补丁。**

---

## 一、产品一句话定位

**明鉴·财税票·万景（明鉴01）**：财税票风控**报告**产品。核心理念 **「不卖系统，卖报告」**。复用型数据分析系统，两级分析（「扫全部找异常」+「单企业深挖」），**报告系统是最大卖点**。

五层架构：

| 层 | 名称 | 落点 |
|---|---|---|
| L0 | 数据层 | ETL → PostgreSQL（project `20`），已跑通 live **193 家真实企业** |
| L1 | 指标语义层 | `metric_registry.py`（唯一指标字典）+ `financial_benchmarks.py`（财务比率）+ `assessment_weights.py`（6 维权重） |
| L2 | 语气层 | 业务语言铁律（禁统计词）、固定逻辑链路（指标波动→业务行为→涉税/经营风险） |
| L3 | 结构层 | `report_templates.py` 五场景 + 结论前置骨架；**目标：document plan = claim 列表** |
| L4 | 版式层 | HTML/PDF 渲染；**只消费 plan，不发明结论** |

**6 个雷达维度**（`assessment_weights.py` `DIMENSION_WEIGHTS`）：税务健康 / 经营真实性 / 发票健康 / 行业地位 / 法律合规 / 财务健康。

---

## 二、技术栈与关键约定

- **后端**：FastAPI + SQLAlchemy 2.x async + PostgreSQL；项目/库名 `20`。
- **前端**：React 18 + TypeScript + Vite + Zustand + Tailwind，目录 `src/`。
- **部署**：Docker Compose；后端 `build: ./backend`。
- **测试**：pytest + Playwright（E2E）。

### 铁律（必须守住）

1. **数字只来自 L0**，评级由 L1 统一（场景无关）。
2. **0 = 弃权，空数据不出现，不编造，弃权优先于编造**。
3. **不下「企业一定虚开发票」的定性结论**（用「需核查」等方向词）。
4. **业务语言**：❌ 严禁卡方值 / p 值 / 置信度 / 特征权重 / 模型风险得分等统计词。
5. **research-first 铁律**：任何方向/实现先联网搜论文/GitHub 借鉴成熟经验（Reiter&Dale NLG、dbt Semantic Layer、专利 6651219 是本轮参考）。
6. **claim 唯一契约**：无 claim → 无对外文本（见 §〇）。

---

## 三、当前状态（已落地）

- 2.0 已从 1.0 拆出并用真实数据（193 家）跑通 live；项目名 `"20"`。
- 1.0 源库在 `risk-assessment-mysql-1`（`host.docker.internal:3307`）。
- 企划书 10 个漏洞已修；审计收尾 + 初始 commit `d106a67`。
- **pytest 基线以仓库最新为准**（claim 唯一化五闭环后曾到 388；后续改动以挂载源码跑全量为准）。
- Playwright E2E 4 spec 全过（实际打到 `8001`，因 LLM 慢）。
- 报告系统已重塑为**结论前置骨架**：评级展望 + 优势/风险二栏 + 财务维度重排。
- 五场景重构：财务 / 税务 / 发票 / 尽调 / 画像；定制报告（AI）、企业画像研判、报告中心向导（含指定企业档）。
- 右栏底栏固定角色、上半截独立滚动（`ResearchCenter.tsx`）。

---

## 四、报告系统「claim 唯一化」——已完成的闭环

> 根因诊断（用户拍板）：报告「改一版又冒一堆问题」＝内容规划与表达实现脱节（见 §〇）。  
> 解法：**claim 唯一化** + **边做边固化到仓库**。五个闭环 = 管道补丁；方向是把管道立成显式架构。

| # | 闭环 | 文件位置 | 说明 |
|---|---|---|---|
| 1 | 达标↔无风险 advice | `slice_report.py::_dimension_analysis` | `advice` 仅当 `warn_items` 非空；覆盖 7 财务维 |
| 2 | LLM 解读结论方向 | `llm_reply.py::_sanitize_narration` + `hallucination_guard` 方向判定 | 数字锚点 + 全达标章禁风险词 |
| 3 | 雷达 ⊆ 章节 | `radar_dimensions_for_chapters` + `attribution_radar_chart(dims=)` | 只画有正文解析的维度 |
| 4 | 阈值收编 | `REVENUE_DEVIATION_WARN=0.30`；`CROSS_AVG/MAX_DEVIATION_WARN` | 营收偏差 + 多源交叉偏差均进字典 |
| 5 | 生成前校验钩子 | `validate_report_chapters` + `enforce_chapter_integrity` + `enforce_cross_surface`；个体 `_validate_enterprise_context`；`_assert_report_renderable` | 先剥离再校验；empty → 拒 PDF |

**关键设计取舍**（继承时别推翻）：
- 风险方向/数字锚点校验**只针对 narration（LLM 生成）**，不针对 claim 本体（builder 条件产出）——否则 Benford 缺样中文说明会被误判。
- 营收偏差统一 **30%**（结论层本就 0.3）；多源交叉偏差是**另一口径**（25%/40%），已单独收编为 `CROSS_*`，勿与 `REVENUE_DEVIATION_WARN` 混用。
- 「阈值只来自字典」靠 **code-review + 单测锁定**；长期目标可再加运行时断言。

---

## 五、困境 / 未闭环项（阻塞点）

1. **story/purpose 条件拼装（部分落地）**：封面 `story` / 章 `purpose` 已由 `compose_*` 按 claim 拼装；完整 KPI fragment map 仍待深化。
2. **校验硬门禁（已验收）**：章内剥离 + 跨面 enforce；empty 拒 PDF；生成响应与 GET 详情回传 validation；ReportCenter 展示明细；CI `test_a2_gate_contract`。
3. **跨面数字机检（已验收，切片）**：`enforce_cross_surface` + `validate_cross_surface`；CI `test_a3_cross_surface_contract`；个体路径尚未挂跨面（已知缺口，非本项失败）。
4. **LLM 约束（A.4 已验收，应用层）**：`NarrationPlan`/`SummaryPlan` + `json_object`/`instructor` + `materialize_plan_sentences`；发明数字/风险矛盾句仍由 sanitize 剥离。DeepSeek 托管 API **无** token 级 JSON Schema，故不引入 Outlines/XGrammar（需自托管）；若日后自托管再评估。
5. **向导预校验（已验收）**：`POST /report/validate-wizard` + `validate_wizard_report`；确认步拦截无样本/无可用章；CI `test_wizard_precheck`。
6. **P0-4（1.0 历史清洗）**：待用户吊销旧 key + 授权，非代码问题。
7. **LLM 慢**：E2E 打 `8001`；chat 超时已放宽；`LLM_DAILY_LIMIT` 是应用配额（Redis 日切注意 UTC）。
8. **个体路径跨面机检（已验收）**：`build_enterprise_report_context` 已挂 `enforce_cross_surface` / `validate_cross_surface`，与切片同口径。

---

## 六、未来规划（按管道收敛，禁止散打补丁）

### 执行纪律（2026-08-30 起强制）

1. **只按 A.1→A.2→A.3→A.4 顺序推进**；不做清单外补丁。
2. **每完成一项必须验收**：单测 +（可时）真实库/API 冒烟；对照「预期效果」写过/不过。
3. **不过不进入下一项**；过了才改 HANDOFF「已落地」状态。

### A. 管道收敛（优先）

| 项 | 预期效果 | 状态 |
|---|---|---|
| A.1 Document plan 唯一输入 | 封面 story / 章 purpose 只能来自 claim（无 claim → 弃权）；切片/个体/定制同口径 | **已验收通过**（2026-08-30） |
| A.2 校验升门禁 | 章内剥离 + empty 拒 PDF；API/前端暴露 validation（含 details）；详情回读同源；CI fixture | **已验收通过**（2026-08-30） |
| A.3 跨面数字机检 | KPI/story/摘要数字 ⊆ claim∪溯源 KPI；不对齐则弃权/剥句；CI `test_a3_cross_surface_contract` | **已验收通过**（2026-08-30，切片路径） |
| A.4 约束解码（可选） | 报告解读/摘要走 JSON schema 句列表 + 本地 sanitize；失败弃权；**不引 Outlines**（DeepSeek Chat 无 token 级 grammar） | **已验收通过**（2026-08-30，应用层约束） |

### B. 产品 polish（多数已落地，勿重复造）

- 全中文净化（`zh_*` / 信号标签；Benford 缺样已中文化）——**2026-08-30 复扫**：7 份报告用户面无英文漏网；修复 R-03 叠加项露出 `T-01/A-02` rule_id。
- **规范书 V1.1 机器验收（2026-08-30）**：`FORBIDDEN_MARKERS`/`scan_forbidden_in_text` 收敛到 `report_templates.py`；`validate_surface_lexicon` 挂切片/个体管道；聚合封面/KPI/结论统一「群体风险判断」；去掉用户面「综合评分」；CI `test_spec_lexicon_contract`；脚本 `scripts/_spec_audit_reports.py` **2 轮 ×8 = 16/16 PASS**。
- **上线闸门复验（同日）**：3 轮 ×（6 场景 + overview + 3 行业 + 2 省域 + 3 定制 + 3 个体 + 向导）= **54/54 PASS**；报告相关单测 74+70 通过；鉴权 API 冒烟通过。
- **人工两份 PDF 复审后的 P0 机制补齐（同日晚）**：雷达维度 ⊆ 六维正文章节（`six_dimensions` + `validate_radar_subset_of_chapters`）；`zh_metric_label` 拦截 `financial_coverage/current_ratio/...` 英文透出；三表空章保留序号不跳号；结论段去表格复读；计数出整数；单期 `scrub_temporal_words`；摘要去掉「健康状况」。CI `test_p0_report_mechanisms`；审计脚本 1 轮 **20/20 PASS**；backend 已 rebuild。
- **多报告综合复审 P0（同日夜）机制补齐**：
  1. **切片联动**：`build_signal_claims(..., industry_l1=)` + `validate_scope_sample_alignment` 渲染前校验；子集 N 与 signal/tax 等章不一致 → `validation.ok=False` 且 PDF 硬拒。
  2. **账务异常**：`assess_financial_ratio` 对负负债率等返回「账务异常」；`is_anomalous_amount` 标记负负债合计；正文不走普通达标。
  3. **排版**：个体 HTML 章节用 `chapter-section` + `page-break-before`（禁止标题后 `page-break-after` 留白）；有同比字段时六维趋势不再写「无法同比」。
  4. **小样本**：`N<30` 章节 `sample_note` + 封面提示「统计结果仅供参考」。
- **发票/税务复审后的公共化（同日夜续）**：
  1. **`scope_contract.py`**：切片过滤/校验/小样本文案抽成公共组件；`hallucination_guard` 再导出；税务/财务/发票同一套 `validate_scope_sample_alignment`。
  2. **会话缓存旁路修复**：有 `industry_l1`/`province`/`enterprise_ids` 时 `_chapter_claims` **禁止**复用会话结论缓存（根因：全集对话缓存被切片报告吃进 → 「发票修好、税务复现」）。
  3. **同业对标**：账务异常指标不参与柱状图；解读注明「已排除」。
  4. **六维趋势去重**：同比/单年提示只挂首个六维子章。
- **企业19 复审 P0（同日 21:0x）**：
  1. **单位篡改**：`Evidence.render` 空 unit + (0,1) 启发式把流动比率 0.88 打成 88%；改为按 `FINANCIAL_RATIOS`/字段白名单格式化。
  2. **权益为负 ROE**：`is_equity_based_ratio_invalid` → 评级「计算失效」，禁止进优势/对标。
  3. **评级摘要表头**：KPI 表补 `<thead>`，key 色改为 `--brand-ink` 提高对比。
  4. **六维时序**：章首统一 `six_dim_temporal_note`，子章不再重复。
- **批次 21_14–21_16 P0（同日 21:1x）**：
  1. **拖累因素双计**：`get_slice_attribution` 按主体去重（税务健康+法律各挂「税务违法」不再 13×2=26）；`validate_firm_counts_within_scope` + PDF 硬拒；摘要计数带「/ 样本 N 家」。
  2. **首页摘要裁切**：个体/聚合摘要改 `summary-panels` 全宽堆叠，雷达另起页；禁止 `text[:N]` 截断摘要条。
  3. **聚合禁「据推断」**：`chapter_conclusion_lines` 去掉 inferred 前缀。
- **四层防护闭环（同日 21:4x）**：
  1. **`report_preflight.py`**：预校验硬门禁（计数/范围/雷达/时序/权益优势/摘要空条/据推断/小样本）+ HTML 后置禁词校验；`.validation.json` 留痕。
  2. **`_assert_report_renderable` → `assert_renderable_or_raise`**；后置失败不降级 FPDF 绕过。
  3. **手册**：`企划书/业务规则手册-报告校验.md`；用例 `tests/test_report_guardrails_closed_loop.py`。
  4. 章节数字锚定等暂为 soft_flags，逐步收紧。
- **防护收紧续（同日 21:5x）**：
  1. 个体维度规则解读升格为 claim、`narration=""`，消除误报的 `number_unanchored` / `risk_contradictions` soft。
  2. 税务/舞弊/信号/真实性摘要统一 `_fmt_firm_count` 附带样本基数。
  3. 摘要列表改 `bullet-line` 段落，避免 WeasyPrint `ul/li` 断页空 `•`。
- **对照遗留清单补齐（同日 22:2x）**：
  1. FPDF 降级路径补 `run_postflight_context` 硬拦，禁止跳过后置。
  2. 同比不进主要优势；净利润同比纳入预警口径（<-20%）。
  3. 结论去表数字复述 + 子章 narration 去重样本/同比提示。
  4. 关键数字/指标表列宽与 nowrap，ROE 失效数值格改「—」。
  5. 小样本 banner 已生产启用（N<30），手册同步澄清。
- `display_name` / 企业N、向导指定企业、下载中文名——已基本落地；改前先 `grep` 现状。

---

## 七、运行 / 测试 Gotcha 速查

- **Docker stale image**：后端/前端改代码后必须 `--build`，或测试用挂载 `-v "$(pwd -W)/backend:/app"` 避免旧镜像。
- **后端单测**：`docker compose run --rm --no-deps -v "$(pwd -W)/backend:/app" -e AUTH_REQUIRED=false backend pytest -q`
  - 必须 `-e AUTH_REQUIRED=false`，否则旧测试 401/403；仓库 `conftest` 也会 `setdefault` 关鉴权。
- **前端构建**：根目录 `npm run build`（源码在 `src/`）。
- **LLM 冒烟**：仓库根 `.env` + compose 注入；`POST /api/v1/chat` 看 `reply_source=llm`。
- **定制报告 report_id 前缀**：必须 `slice_` / `ent_`，否则被 cleanup 删除。
- **重跑 ETL**：连 1.0 源库 `risk-assessment-mysql-1`（`host.docker.internal:3307`）而非 `20-mysql`。

---

## 八、关键文件地图

| 文件 | 职责 |
|---|---|
| `backend/app/services/report_preflight.py` | 四层防护 L2/L4：预校验硬门禁 + HTML 后置 + validation.json |
| `企划书/业务规则手册-报告校验.md` | 边界 case 唯一依据（改口径先改手册） |
| `backend/app/services/report_templates.py` | 五场景 SCENARIOS、`FORBIDDEN_MARKERS`、章节→雷达维映射（规划器侧） |
| `backend/scripts/_spec_audit_reports.py` | 规范书多轮生成 + 禁词/字段隔离/跨面机器验收 |
| `backend/app/services/judgment_service.py` | claim builder（content determination） |
| `backend/app/services/slice_report.py` | 组装 context；个体 `_validate_enterprise_context`；禁无 claim 外写死风险 advice |
| `backend/app/services/llm_reply.py` | surface realization（润色）+ sanitize |
| `backend/app/services/metric_registry.py` | 字典 + `REVENUE_DEVIATION_WARN` + `CROSS_*_DEVIATION_WARN` |
| `backend/app/services/financial_benchmarks.py` | 财务比率唯一源 |
| `backend/app/services/assessment_weights.py` | 6 维权重 |
| `backend/app/services/assessment.py` | 评级 + 预警 |
| `backend/app/services/chart_payloads.py` | 图表；雷达裁剪 |
| `backend/app/services/insight_engine.py` | 洞察规则 |
| `backend/app/services/authenticity_engine.py` | 真实性；交叉偏差阈值读 `CROSS_*` |
| `backend/app/api/v1/report.py` | `/generate`、`/enterprise`、下载名 |
| `src/components/report/ReportWizard.tsx` | 报告向导 |
| `src/stores/reportStore.ts` | 下载名等 |
| `HANDOFF-CURSOR.md` | 本文：机制北星 + 接手约束 |

---

## 九、memory 索引（补充上下文）

长期记忆：`C:\Users\85765\.claude\projects\D--projects-risk-assessment\memory\`。关键：`report-claim-unification`（含机制层处方同步）、`report-business-language-rule`、`report-reshaping-industry`、`custom-report-feature`、`custom-report-blocked-guidance`、`phase23-profile-etl`、`etl-run-20`、`pytest-auth-gotcha`、`e2e-proxy-and-chat-timeout`、`llm-daily-quota`。
