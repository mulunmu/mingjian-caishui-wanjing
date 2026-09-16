"""Versioned semantic registry models for tools, rules, and topic memory."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ThresholdRule(Base):
    __tablename__ = "threshold_rule"

    rule_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    metric_key: Mapped[str] = mapped_column(String(64), index=True)
    scope_json: Mapped[str] = mapped_column(Text, default="{}")
    operator: Mapped[str] = mapped_column(String(20))
    threshold_json: Mapped[str] = mapped_column(Text, default="{}")
    severity: Mapped[str] = mapped_column(String(20), default="warn")
    action: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(120), default="baseline")
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ToolDefinition(Base):
    __tablename__ = "tool_definition"

    tool_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    input_schema_json: Mapped[str] = mapped_column(Text, default="{}")
    output_schema_json: Mapped[str] = mapped_column(Text, default="{}")
    required_params_json: Mapped[str] = mapped_column(Text, default="[]")
    dependencies_json: Mapped[str] = mapped_column(Text, default="[]")
    chapter_links_json: Mapped[str] = mapped_column(Text, default="[]")
    scenarios_json: Mapped[str] = mapped_column(Text, default="[]")
    shape: Mapped[str] = mapped_column(String(64), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ToolAlias(Base):
    __tablename__ = "tool_alias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tool_id: Mapped[str] = mapped_column(String(96), index=True)
    alias: Mapped[str] = mapped_column(String(255), index=True)
    alias_type: Mapped[str] = mapped_column(String(20), default="query")
    language: Mapped[str] = mapped_column(String(16), default="zh")
    weight: Mapped[int] = mapped_column(Integer, default=100)
    status: Mapped[str] = mapped_column(String(20), default="validated", index=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ToolDependency(Base):
    __tablename__ = "tool_dependency"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tool_id: Mapped[str] = mapped_column(String(96), index=True)
    depends_on_tool_id: Mapped[str] = mapped_column(String(96), index=True)
    relation: Mapped[str] = mapped_column(String(20), default="requires")
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ToolExample(Base):
    __tablename__ = "tool_example"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tool_id: Mapped[str] = mapped_column(String(96), index=True)
    query_text: Mapped[str] = mapped_column(Text)
    example_type: Mapped[str] = mapped_column(String(20), default="positive")
    language: Mapped[str] = mapped_column(String(16), default="zh")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), default="validated", index=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConversationTopic(Base):
    __tablename__ = "conversation_topic"

    topic_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    turn_index: Mapped[int] = mapped_column(Integer)
    parent_topic_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str] = mapped_column(Text)
    entities_json: Mapped[str] = mapped_column(Text, default="[]")
    filters_json: Mapped[str] = mapped_column(Text, default="{}")
    scenario: Mapped[str | None] = mapped_column(String(32), nullable=True)
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tool_plan_json: Mapped[str] = mapped_column(Text, default="[]")
    claim_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    report_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
