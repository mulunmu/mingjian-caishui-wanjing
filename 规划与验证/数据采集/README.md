# 数据采集模块

数据采集是上市公司/行业风险方向能否落地的第一道门槛。本模块的目标不是写一个临时爬虫，而是建立可重复、可追溯、可增量的数据流水线。

## 一、模块目标

```text
官方公开源
-> 元数据发现
-> 原始文件下载
-> 结构化解析
-> 字段抽取
-> 事件抽取
-> 多层校验
-> 财务事实和证据存储
-> 增量调度
```

输出必须满足：

- 每个字段能追溯到来源 URL、文件哈希、页码和原文片段。
- 每个数字可执行会计恒等式和范围校验。
- 同一事实可由多个来源交叉验证。
- 失败任务可重试、可恢复、可审计。
- 原始文件、解析版本和抽取结果相互分离。

## 二、模块边界

本模块负责：

- 数据源注册和合规信息。
- 公告和报告的发现、下载、去重、缓存。
- PDF / HTML / XBRL 解析。
- 财务字段、披露事件和舆情候选抽取。
- 数据质量检查、版本管理和增量更新。
- 向下游输出标准化财务事实、事件 Claim 和证据。

本模块不负责：

- 直接生成风险结论。
- 直接生成投资建议。
- 直接决定报告章节。
- 绕过验证码、付费墙或访问控制。
- 用未授权来源替代官方披露。

## 三、数据源优先级

### 第一优先级：官方公开源

- 交易所和监管机构公开信息。
- 上市公司公告和定期报告。
- SEC EDGAR、官方 XBRL API。
- 公司官网投资者关系页面。

### 第二优先级：开放 API

- World Bank、FRED 等有明确公开接口的宏观数据。
- 其它授权明确、字段说明稳定的 API。

### 第三优先级：便利工具

- Tushare、AKShare、Stooq 等。

这些工具适合探索和辅助验证，正式产品必须复核授权、字段口径、更新频率和稳定性。

### 第四优先级：合法网页采集

仅采集公开允许访问的页面，并满足：

- 遵守 robots 和服务条款。
- 限制请求频率。
- 保存来源 URL 和采集时间。
- 做缓存、去重和增量更新。
- 不采集非公开、受控或需要绕过的数据。

## 四、核心流水线

### 1. Source Registry

每个来源登记：

```text
source_id
来源名称
授权和条款
入口 URL
更新频率
限速
支持格式
负责人
最近验证时间
```

### 2. Discovery

先抓元数据，不先下载全文：

```text
company_id
market
security_code
announcement_type
report_period
published_at
source_url
file_format
```

### 3. Download

- URL 去重。
- 文件哈希去重。
- 断点续传。
- 限速、重试和失败记录。
- 原始文件不可覆盖，只追加版本。

### 4. Parse

解析优先级：

```text
XBRL / 结构化 HTML
-> 原生 PDF 文本和表格
-> OCR
```

必须处理：

- 跨页表格。
- 页眉页脚和栏目说明。
- 万元、亿元、元等单位和币种。
- 括号负数、千分位和百分比。
- 会计政策和风险说明中的干扰文本。

### 5. Extract

所有抽取必须绑定 Schema：

```text
company_id
report_period
statement_type
metric_key
value
unit
currency
page_number
source_text
method
confidence
parser_version
```

LLM 只能作为规则和表格解析的补充，不得成为唯一事实来源。

### 6. Event Extraction

第一阶段事件标签：

```text
going_concern
impairment
related_party
guarantee
litigation
regulatory_penalty
debt_default
auditor_change
management_change
restatement
earnings_warning
```

关键词命中只表示候选，必须经过上下文分类和适用性复核。

### 7. Validation

至少执行：

1. 数值范围校验。
2. 会计恒等式校验。
3. 同比、环比和突变校验。
4. 多来源交叉校验。
5. 证据覆盖率校验。

### 8. Store

```text
Object Storage：原始 PDF / HTML / XBRL
PostgreSQL：来源、文件、任务、版本和事实元数据
Analytical Store：标准化财务事实
Vector Store：报告章节、事件和证据片段
```

### 9. Schedule

- 定期报告按公告周期增量更新。
- 重大事项公告高频轮询。
- 失败任务独立重试。
- 解析器和 Schema 升级后支持回放。

## 五、与现有系统的接入

数据采集模块不直接生成答案。标准出口是：

```text
财务事实 -> Claim
披露事件 -> Claim
行业基准 -> Tool Registry / RAG
证据片段 -> RAG
章节素材 -> Report Block
预测概率 -> 独立预测 Claim
```

这样上市公司 Domain Pack 可以复用当前对话、组合、报告和验证能力。

## 六、当前 PoC 结论

已完成贵州茅台 2024 年年报的真实链路验证：

- PDF 大小约 3.6 MB。
- 143 页。
- 识别 275 张表。
- 首次完整处理约 27 秒。
- 缓存后重复处理约 17 秒。
- 收入、净利润、现金流、资产和负债字段均带页码证据。
- 事件候选已召回，但尚未完成适用性判断。

PoC 证明“公开数据 -> 财报解析 -> 字段提取 -> 事件候选 -> 证据链”可行，但还没有证明跨公司模板和全市场规模稳定。

## 七、下一步

1. 完成 10 家公司 × 3 年采集试点。
2. 建立正式 Source Registry 和文件版本表。
3. 建立标准化财务事实 Schema。
4. 补齐跨页表格、单位换算和负数识别。
5. 完成事件适用性判断。
6. 通过验证矩阵后再扩大至 50 家和 500 家。

脚本入口：`backend/scripts/poc_public_financial_data.py`
