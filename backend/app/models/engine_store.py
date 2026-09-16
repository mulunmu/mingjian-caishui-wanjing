"""引擎预计算特征 + 风控结论持久化"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class EnterpriseEngineFeatures(Base):
    """ETL 预聚合：反欺诈 + 真实性（运行时优先读 PG，避免同步 MySQL）"""

    __tablename__ = "enterprise_engine_features"

    enterprise_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    fraud_composite_score: Mapped[float] = mapped_column(Numeric(6, 2), default=0)
    fraud_risk_level: Mapped[str] = mapped_column(String(20), default="低风险")
    fraud_signals: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    scbm_mismatch_score: Mapped[float] = mapped_column(Numeric(6, 2), default=0)
    red_invoice_score: Mapped[float] = mapped_column(Numeric(6, 2), default=0)
    concentration_score: Mapped[float] = mapped_column(Numeric(6, 2), default=0)
    sequence_gap_ratio: Mapped[float] = mapped_column(Numeric(8, 4), default=0)
    pyod_score: Mapped[float] = mapped_column(Numeric(6, 2), default=0)
    authenticity_score: Mapped[float] = mapped_column(Numeric(6, 2), default=0)
    cross_avg_deviation: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    cross_suspicious: Mapped[bool] = mapped_column(Boolean, default=False)
    invoice_cnt: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EngineSnapshot(Base):
    """全局/行业级引擎快照（如 Benford）"""

    __tablename__ = "engine_snapshots"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConclusionRecord(Base):
    """风控结论持久化（报告覆盖度 / 三级溯源）"""

    __tablename__ = "conclusion_store"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    function: Mapped[str] = mapped_column(String(32))
    dimension: Mapped[str] = mapped_column(String(32))
    claims_json: Mapped[str] = mapped_column(Text, default="[]")
    followups_json: Mapped[str] = mapped_column(Text, default="[]")
    evidence_hidden: Mapped[bool] = mapped_column(Boolean, default=True)
    meta_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ChatSessionRecord(Base):
    """会话上下文持久化"""

    __tablename__ = "chat_sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    last_intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_function: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_dimension: Mapped[str | None] = mapped_column(String(32), nullable=True)
    industry_l1: Mapped[str | None] = mapped_column(String(50), nullable=True)
    province: Mapped[str | None] = mapped_column(String(32), nullable=True)
    enterprise_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    covered_functions_json: Mapped[str] = mapped_column(Text, default="[]")
    history_json: Mapped[str] = mapped_column(Text, default="[]")
    custom_state_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    focus_history_json: Mapped[str] = mapped_column(Text, default="[]")  # M2 焦点栈
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AppUser(Base):
    """认证用户（替代内存 _users，多 worker 可共享）"""

    __tablename__ = "app_users"

    email: Mapped[str] = mapped_column(String(255), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="user")
    plan: Mapped[str] = mapped_column(String(32), default="free")
    # 密码版本：改密时 +1；JWT 携带签发时的值，鉴权时比对，用于「改密后旧 token 立即失效」
    pwd_ver: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
