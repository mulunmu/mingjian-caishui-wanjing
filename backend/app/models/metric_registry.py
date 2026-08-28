"""指标语义层：口径字典 + 字段映射（阶段二）

设计对齐 dbt MetricFlow 的指标定义模型（type/formula/unit/grain/dimensions/filters），
落地为 SQLAlchemy 表。JSON 字段沿用 engine_store 约定（Text 存 JSON，服务层 json.dumps/loads）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class MetricDefinition(Base):
    """规范口径字典：一个指标一行。

    metric_type 取 MetricFlow 子集：
    - simple   —— 直接来自源字段（如 credit_score）
    - ratio    —— 多源字段比值/离散度（如 revenue_deviation）
    - derived  —— 由其它指标加权组合（如 overall_score）
    - computed —— 由算法函数计算（如 tax_health_score，公式为文字说明）
    """

    __tablename__ = "metric_definition"

    metric_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))  # 中文显示名
    description: Mapped[str] = mapped_column(Text)  # 口径定义（一句话）
    metric_type: Mapped[str] = mapped_column(String(20), default="computed")
    formula: Mapped[str | None] = mapped_column(Text, nullable=True)  # 口径公式/文字说明
    unit: Mapped[str] = mapped_column(String(20), default="")
    grain: Mapped[str] = mapped_column(String(30), default="enterprise")  # 粒度
    source_fields_json: Mapped[str] = mapped_column(Text, default="[]")  # 依赖源字段
    dimensions_json: Mapped[str] = mapped_column(Text, default="[]")  # 可切维度
    default_filters_json: Mapped[str] = mapped_column(Text, default="{}")  # 默认过滤
    edge_cases: Mapped[str | None] = mapped_column(Text, nullable=True)  # 边缘情况说明
    is_canonical: Mapped[bool] = mapped_column(Boolean, default=False)  # 系统内建口径
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FieldMapping(Base):
    """已保存的字段映射（Granit 四层的第一层 saved）。

    用户上传列名（source_alias）→ 目标源字段（target_field），命中即免 LLM。
    """

    __tablename__ = "field_mapping"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_alias: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    target_field: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    confidence: Mapped[int] = mapped_column(Integer, default=100)  # 0-100
    origin: Mapped[str] = mapped_column(String(30), default="saved")  # saved/manual/llm
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
