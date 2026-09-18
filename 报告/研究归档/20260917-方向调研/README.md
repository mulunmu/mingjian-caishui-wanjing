# 2026-09-17 方向调研封存

## 封存范围

本目录封存本轮对以下问题的调研、可行性判断与 PoC 证据：

- 对话分析能力、长记忆与竞品交互方式
- 组合模块的可复用性与横向迁移价值
- 金融预测方向及公开数据可行性
- 上市公司财报、舆情事件与爬取方案
- 系统定位、商业化意义与后续优化路线
- 意图路由分层、上下文优先级与真实 HTTP 实测（见 2026-09-18 补充调研）

## 已确认结论

1. 当前项目先完成金融财税票领域的闭环，不同时接入第二领域数据。
2. LangGraph 已进入生产外层状态机，承担记忆、规划、执行、校验、中断与检查点。
3. LangChain 不作为第二套 Planner；仅保留其底层依赖。业务适配点在工具、Claim、RAG、报告 Block 与 Case，不重写现有确定性引擎。
4. 金融语义模型必须作为可替换的语义/解释层，不得生成事实数字。未配置金融模型时，系统继续使用规则语义路径并明确退化。
5. 公开上市公司财报方向可行，但财报字段必须结构化、可溯源；舆情必须事件优先、情绪后置。
6. 通用化方向是 Domain Pack + Tool Registry + Claim Layer + Report Block Layer，而不是把这套代码绑定到某一批企业数据。

## 本轮落地映射

- 分析模式：`backend/app/services/analysis_patterns.py`
- 行业焦点：`backend/app/services/scope_state.py`
- 动态组合：`backend/app/services/composition_planner.py`
- 并行执行与多图：`backend/app/services/composition_execution_bridge.py`
- 长记忆：`backend/app/services/topic_memory.py`
- 定制报告工作台：`src/pages/CustomReportPage.tsx`
- 报告块去重：`backend/app/services/report_blocks.py`
- 真实审计：`backend/scripts/audit_integration_truth.py`
- 公开数据 PoC：`backend/scripts/poc_public_financial_data.py`

## 未在下一领域前执行的项

- 语音链路和手机系统接入
- 第二领域正式 ETL
- 依赖付费商业数据 API 的能力
- 未经验证的因果推断和预测结论
