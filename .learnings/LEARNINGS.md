# Learnings

---


## LEARNxxxx
- **Date**: 2026-08-30
- **Category**: correction
- **Source**: user-audit-two-pdfs
- **Summary**: 人工抽两份 PDF 暴露：雷达维度超出正文、英文字段透出、章节跳号、时序词单期误用、结论复读表格、计数小数、摘要冗余「健康状况」。样本变好 ≠ 机制修好；必须雷达⊆章节机检 + 中文指标过滤器 + 时序/渲染前置校验，不能只修两份样例。
- **Action**: 已落地 six_dimensions 与雷达同源裁剪、zh_metric_label 拦截 snake_case、statements 空表保留序号、结论去复读、scrub_temporal_words、去掉健康状况；CI test_p0_report_mechanisms + 审计脚本硬检。

## LEARN-2026-08-30-scope-fragmentation
- **Date**: 2026-08-30
- **Category**: correction
- **Source**: user-audit-invoice-vs-tax
- **Summary**: 用户指出「发票切片已修好、税务仍像有旧 bug」本质是校验碎片化：同一套过滤未公共化；另有会话结论缓存在有 industry 筛选时仍可能喂全集 claim。现场机检显示 tax/fraud 在 live builder 层已对齐 59，但架构上必须抽 scope_contract + 禁缓存旁路，否则会再分裂。
- **Action**: 新增 scope_contract.py；切片筛选时 _chapter_claims 禁用 session cache；同业对标排除账务异常；六维趋势只写一次。

## LEARN-2026-08-30-unit-and-roe
- **Date**: 2026-08-30
- **Category**: correction
- **Source**: user-audit-enterprise-19
- **Summary**: Evidence.render 对空 unit 且 |v|<1 一律 ×100 加 %，把流动比率 0.88 篡改成 88%；权益为负时 ROE 虚高仍进「主要优势」。
- **Action**: render 按 FINANCIAL_RATIOS/字段白名单格式化；is_equity_based_ratio_invalid → 计算失效，禁优势/对标；KPI 表补 thead。

## LEARN-2026-08-30-drag-double-count
- **Date**: 2026-08-30
- **Category**: correction
- **Source**: user-audit-batch-21_14-21_16
- **Summary**: 建筑切片 N=19 却写「税务违法（26 家）」：同一主体在 tax_health 与 legal 各挂一次「税务违法」，get_slice_attribution 按维度出现次数累加而非主体去重（13×2=26）。摘要「截断」主因是 twocol `table-layout:fixed` + 与雷达同页挤压，WeasyPrint 裁切观感，非 LLM。
- **Action**: 拖累因素按主体去重计数并 cap≤N；`validate_firm_counts_within_scope` 硬门禁；摘要改全宽 summary-panels；聚合去掉「据推断」；计数标注「/ 样本 N 家」。

## LEARN-2026-08-30-guardrail-closed-loop
- **Date**: 2026-08-30
- **Category**: best_practice
- **Source**: user-audit-four-layer-defense
- **Pattern-Key**: machine-guard-before-pdf
- **Summary**: 样本好看 ≠ 机制锁死。必须把校验前移到 PDF 前，并写 validation.json；不能把 validate_report_chapters 的数字锚定软问题一刀切硬拒（会误杀正常个体报告）。硬门禁只拦 P0 业务规则。
- **Action**: 落地 report_preflight + 业务规则手册 + test_report_guardrails_closed_loop；HTML 数字孤儿暂 warning。

## LEARN-2026-08-31-custom-fraud-surface
- **Date**: 2026-08-31
- **Category**: correction
- **Source**: user-audit-发票舞弊风险报告
- **Summary**: 定制单章舞弊报告退回通用 KPI 卡「高风险/标记·项」，把 62 家主体读成 62 项信号；LLM 解读带出内部词「预警积木」；轻量 4 页报告执行摘要/正文/结论三处大段复制。
- **Action**: _build_summary_kpis 与定制 fraud KPI 用「舞弊预警主体数·家」；sanitize_surface_industry_terms 替换积木→类型；正文 _compact_chapter_narrations + 结论禁整段 narration 复读；narration prompt 禁止信号家数清单。

## LEARN-2026-08-31-wizard-lexicon-contradiction
- **Date**: 2026-08-31
- **Category**: correction
- **Source**: user-screenshot-报告生成向导
- **Summary**: 向导 validate-wizard 只查样本/章节可用性，显示「预校验通过」；生成时 preflight lexicon 硬拒。根因是画像副标题「均值分位」命中 FORBIDDEN「分位」。
- **Action**: 副标题改为「均值分布」；sanitize 清洗分位残留；向导增加场景文案禁词预检，避免通过/拒绝矛盾。

## LEARN-2026-08-31-wizard-preflight-parity
- **Date**: 2026-08-31
- **Category**: correction
- **Source**: user-screenshot-制造画像-scope_alignment + 全系统扫描
- **Summary**: 向导只查样本/章节可用性，PDF 硬门禁另检 scope_alignment/lexicon，造成「通过+拒绝」矛盾。制造画像：score overall 有行业筛选仍回落全库 193；IT软件预警：claim 残留禁词 IT软件。
- **Action**: build_score_claims overall 同源筛选；组装出口 _sanitize_slice_context_surfaces；向导干跑 scope+lexicon；scripts/_smoke_wizard_preflight 覆盖 portrait/alert×全行业，contradictions=0。
