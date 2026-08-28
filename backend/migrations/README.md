# 数据库迁移

真实数据接入时使用 Alembic 管理 schema 变更。

## 初始化

```bash
pip install alembic
alembic init migrations
# 编辑 alembic.ini: sqlalchemy.url = postgresql+asyncpg://...
# 编辑 migrations/env.py: target_metadata = CoreMetrics.metadata
alembic revision --autogenerate -m "init"
alembic upgrade head
```

## 核心表

```sql
-- 企业宽表 (对应 app/models/core_metrics.py)
CREATE TABLE core_metrics (
  enterprise_id    VARCHAR(64) PRIMARY KEY,
  enterprise_name  VARCHAR(200) NOT NULL,
  industry_l1      VARCHAR(50),
  industry_l2      VARCHAR(50),
  province         VARCHAR(50),
  city             VARCHAR(50),
  credit_level     CHAR(1),
  credit_score     NUMERIC(5,2),
  tax_on_time_rate NUMERIC(5,4),
  overall_score    NUMERIC(5,2),
  risk_level       VARCHAR(20),
  dimensions       JSONB,
  warning_signals  JSONB,
  updated_at       TIMESTAMPTZ DEFAULT now()
);

-- 法律事件明细
CREATE TABLE legal_events (
  id              SERIAL PRIMARY KEY,
  enterprise_id   VARCHAR(64) NOT NULL REFERENCES core_metrics(enterprise_id),
  event_type      VARCHAR(30) NOT NULL,
  severity        CHAR(1) NOT NULL,
  amount_involved NUMERIC(18,2),
  event_date      DATE,
  description     VARCHAR(200),
  source          VARCHAR(30),
  created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_core_credit ON core_metrics(credit_level);
CREATE INDEX idx_core_risk ON core_metrics(risk_level);
CREATE INDEX idx_legal_ent ON legal_events(enterprise_id);
```

## 种子数据

```bash
python seed_data.py  # 生成 200 家模拟企业
```
