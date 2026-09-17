# 阶段 18 混合 RAG 闭环报告

日期：2026-09-17

候选标签：`rag-v2-stage18-accepted-20260917`

## 一、结论

阶段 18 已完成可运行、可评测、可回滚的混合 RAG：

```text
PostgreSQL image=pgvector/pgvector:pg16
pgvector extension=0.8.4
validated tools=75
embedded tools=75
embedding model=BAAI/bge-small-zh-v1.5
embedding dimension=512
HNSW index=ix_semantic_embedding_hnsw
```

检索组合为：

```text
validated snapshot
-> pgvector dense cosine retrieval
-> BM25 lexical retrieval
-> title/alias/domain/exact rule ranking
-> reciprocal-rank fusion reranker
-> executable-only filter
```

pgvector 或 embedding 不可用时，只回退到确定性词法检索，不会放开 unsupported 工具。

## 二、数据库切换

PostgreSQL 已从 `postgres:16` 切到 `pgvector/pgvector:pg16`，沿用原数据卷。切换后核验：

```text
core_metrics=193
pgvector=0.8.4
semantic_embedding=75
数据未丢失
```

切换前备份：

```text
报告/阶段18-切换pgvector前-risk_db备份.sql
```

数据库 collation version 已执行 `ALTER DATABASE risk_db REFRESH COLLATION VERSION`，启动警告已消除。

## 三、Embedding 索引

新增表：

```text
semantic_embedding
```

每行包含：

```text
tool_id
content_hash
model_name
dimension
embedding vector(512)
metadata_json
updated_at
```

唯一约束：

```text
uq_semantic_embedding_tool_model
```

重建命令：

```text
python -m scripts.rebuild_tool_embeddings --force
```

结果：

```text
tools=75
dimension=512
removed=0
```

模型随后端镜像缓存到 `/app/.fastembed_cache`，运行时不依赖在线下载。构建和使用时使用 `hf-mirror.com`，并关闭 Xet。

## 四、检索评测

Golden set：77 条查询。

```text
Recall@1=0.922078
Recall@5=1.000000
Precision@5=0.200000
MRR=0.958874
dense_coverage=1.0
unsupported_leakage=[]
ok=true
```

检索耗时（模型预热后）：

```text
P50=9.515ms
P95=12.009ms
max=21.294ms
```

报告 Block 矩阵：

```text
31/31 passed
```

## 五、生产对话验证

实现 hybrid 后连续两轮 105 条对话矩阵：

```text
run A: 105/105, P50 1145.10ms, P95 5360.30ms
run B: 105/105, P50 1175.80ms, P95 3994.97ms
```

后端全量回归：

```text
828 passed, 8 skipped
```

8 个 skip 仍来自测试环境缺少指定样本，不是 hybrid RAG 失败。

前端构建：通过。

## 六、运行与回滚

生产开关：

```text
RAG_HYBRID_ENABLED=true
RAG_EMBEDDINGS_AUTO_SEED=true
RAG_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
RAG_EMBEDDING_DIM=512
```

回滚检索行为但保留数据：

```text
RAG_HYBRID_ENABLED=false
```

回滚后使用确定性词法检索，不删除 `semantic_embedding`、pgvector 扩展或 HNSW 索引。

## 七、边界说明

- 当前 reranker 是确定性的 RRF 融合，不依赖额外神经 cross-encoder。
- 更换 embedding 模型、维度或融合权重后，必须重建全量 embedding 并重新跑 Golden set。
- unsupported 指标仍不会生成 embedding，也不会进入检索。
- Sentry DSN 仍未配置；该外部监控项不属于 Stage 18 混合 RAG 闭环条件。
