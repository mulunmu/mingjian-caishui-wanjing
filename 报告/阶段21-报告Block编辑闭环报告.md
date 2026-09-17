# 阶段 21 报告 Block 编辑闭环报告

日期：2026-09-17

候选标签：`rag-v2-stage21-accepted-20260917`

## 一、结论

阶段 21 已完成报告 Block 级编辑、版本历史、锁定、排序、软删除、恢复和重渲染闭环。报告继续遵循“章节 -> Block -> Claim”结构，不允许整篇 LLM 自由生成，也不允许 API 直接写入任意自由文本作为事实段落。

## 二、Block Tree v2

每个 Block 现在包含：

```text
block_id
version
content_hash
status
locked
source_claim_index
```

快照版本：

```text
block_tree_version=2
```

旧快照仍可读取，缺失字段会按规则补齐。

## 三、Block 编辑能力

新增：

```text
backend/app/services/report_block_editor.py
```

支持：

```text
lock / unlock
move / reorder
soft remove
regenerate from original Claim
restore historical version
```

编辑约束：

- 锁定 Block 不可重生成、移动或删除。
- 重生成只能使用原 `source_claim_index`，不能注入任意段落文字。
- 删除为软删除，保留版本历史和审计记录。
- 恢复只能选择已经登记的历史版本。

## 四、API

```text
GET   /api/v1/report/{report_id}/blocks
PATCH /api/v1/report/{report_id}/blocks/{block_id}
POST  /api/v1/report/{report_id}/blocks/{block_id}/regenerate
POST  /api/v1/report/{report_id}/blocks/{block_id}/restore
```

API、HTML 和 PDF 使用同一 `chapters[].blocks` 顺序。删除的 Block 保留在历史中，但不会进入 API 详情或 HTML/PDF 渲染。

## 五、图表重渲染

写快照时，图表 PNG 会转成 `data:image/png;base64,...` 保存，再移除不可复用的文件路径。这样 Block 编辑后的 PDF 重渲染仍能使用原图表，不会因临时文件清理而丢失。

## 六、验证

```text
Block/API focused tests: 10 passed
backend full regression: 847 passed, 8 skipped
report block matrix: 31/31
readiness: ok=true
strict coverage: passed
hybrid retrieval: Recall@5=1.0, MRR=0.958874
frontend build: passed
```

105 条对话矩阵：

```text
A: 105/105, P50 981.60ms, P95 5121.42ms
B: 105/105, P50 959.90ms, P95 4377.87ms
```

## 七、边界说明

- 本次没有开放任意文本覆盖 Block；这属于事实红线，不是缺少功能。
- 重生成不会重新计算指标；指标事实必须由工具执行器先更新 Claim，再重建 Block。
- 36 个 unsupported 指标仍不会进入报告组合。
- API 重渲染失败时会返回明确的 `render.ok=false`，不会谎称 PDF 已更新。
