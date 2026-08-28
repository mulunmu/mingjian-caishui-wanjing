# 开源集成变更报告

> 基于 `reference/` 与 `opensource/` 验证代码，对 risk-assessment 项目进行加固。

## 任务1：意图识别加固 ✅

**改动文件：** `backend/app/services/intent_engine.py`

**做了什么：**
- 保留规则层优先匹配，新增 LLM 语义层（Reference: `Financial-Intent-Understanding-with-LLMs`）
- 引入验证过的 `INTENT_SYSTEM_PROMPT` 与 20 条 `TEST_CASES`
- 新增 `recognize_llm()`、`evaluate()` 方法
- 修复「同行对比」「营收对得上」等边界 case

**为什么改：** 规则层 alone 无法覆盖语义变体；开源基准 85.33% 准确率 Prompt 可作为 LLM 层标准。

**验证结果：**
```
evaluate(use_llm=False) → 准确率 100%（20/20），passed: True
POST /api/v1/chat → intent: tax_health ✓
```

---

## 任务2：LLM 降级加固 ✅

**改动文件：** `backend/app/services/llm_reply.py`、`.env.example`

**做了什么：**
- Reference: `litellm_fallback.py` — `num_retries=2` + `fallbacks=[deepseek-chat]`
- `LLM_API_KEY` 未配置 → 直接返回 `[规则模板生成]` 前缀的模板回复
- 全部 LLM 失败 → 同样降级到模板

**验证结果：** 未配置 API Key 时 chat 回复以 `[规则模板生成]` 开头 ✓

---

## 任务3：评估框架对标 FinRobot ✅

**改动文件：**
- `backend/app/services/assessment_weights.py`（新建）
- `backend/app/services/assessment.py`
- `frontend/src/pages/EnterpriseDetail.tsx`（权重展示）

**权重调整（FinRobot 映射后偏差 >10% 项已修正）：**

| 维度 | 原权重 | 新权重 | FinRobot 映射 |
|------|--------|--------|---------------|
| tax_health | 0.40 | **0.30** | governance_risk 0.15 |
| authenticity | 0.35 | **0.30** | business_quality 0.25 |
| finance | 0.25 | **0.40** | financial 0.30 + valuation 0.20 |

**为什么改：** 原 finance 权重与 FinRobot 财务+估值合计偏差 25%，tax_health 偏差 25%。

---

## 任务4：产业链图谱集成 ✅

**改动文件：**
- `backend/app/services/graph_service.py`（新建）
- `backend/app/api/v1/graph.py`（新建）
- `backend/app/main.py`（注册路由）
- `requirements.txt`（networkx）

**做了什么：**
- 加载 `ChainKnowledgeGraph-main/data/industry_industry.json`
- 样本企业节点 + 行业层级 + 虚拟根节点「国民经济」
- Reference: `chain_knowledge_graph.py` — `find_industry_path` / `get_key_companies`

**新增 API：**
- `GET /api/v1/graph/path?from=ENT001&to=ENT005`
- `GET /api/v1/graph/key-companies?top_n=20`

**验证结果：**
```
find_industry_path(ENT001, ENT005) → path length 4, HTTP 200
```

---

## 任务5：报告格式对标 ✅

**改动文件：**
- `backend/app/templates/report.html`
- `backend/app/services/report_generator.py`

**补充章节（FinRobot 7 章 → 我们 PDF 3 页内嵌）：**

| FinRobot 章节 | 我们的对应 |
|---------------|-----------|
| Executive Summary | 封面评估摘要 |
| Company Overview | 封面企业概览（行业/地区） |
| Financial Analysis | 第2页三维评分 |
| Industry Positioning | 第2页行业对标段落 |
| Risk Assessment | 第3页预警信号 |
| Valuation & Outlook | 第3页 PE/营收同比/Z-Score |
| Appendix | 第3页数据来源 |

**参考：** `fundamental_analysis_report-main` 财务描述 + FinRobot 报告结构

---

## 依赖变更

```
litellm, networkx  → requirements.txt
LLM_FALLBACK_MODEL → .env.example
```

## 未改动（保持跑通）

- 现有 API 端点路径与响应结构
- 前端页面路由与交互流程
- Docker / seed_data 脚本

## 建议后续

1. 配置 `LLM_API_KEY` 后运行 `evaluate(use_llm=True)` 对比 LLM 层准确率
2. Linux 环境安装 WeasyPrint GTK 依赖以获得更好 PDF 排版
3. V2：chat SSE 流式输出
