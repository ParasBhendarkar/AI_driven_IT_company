from datetime import datetime
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.sql import func

from database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, default=generate_uuid)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(50), nullable=False, default="pending")
    priority = Column(String(20), nullable=False, default="Medium")
    repo = Column(String(255), nullable=False)
    branch = Column(String(255), nullable=False)
    acceptance_criteria = Column(JSON, nullable=False, default=list)
    context_refs = Column(JSON, nullable=False, default=list)
    current_agent = Column(String(50), nullable=False, default="Orchestrator")
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=5)
    progress = Column(Integer, nullable=False, default=0)
    pr_number = Column(Integer, nullable=True)
    commit_hash = Column(String(100), nullable=True)
    dev_output = Column(JSON, nullable=True)
    qa_result = Column(JSON, nullable=True)
    ciso_gate = Column(JSON, nullable=True)
    critic_output = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class AgentCall(Base):
    __tablename__ = "agent_calls"

    id = Column(String, primary_key=True, default=generate_uuid)
    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_role = Column(String(50), nullable=False)
    action = Column(String(100), nullable=False)
    input_payload = Column(JSON, nullable=True)
    output_payload = Column(JSON, nullable=True)
    status = Column(String(50), nullable=False, default="completed")
    tokens_used = Column(Integer, nullable=True)
    latency_seconds = Column(Float, nullable=True)
    cost_usd = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class QAResultRow(Base):
    __tablename__ = "qa_results"

    id = Column(String, primary_key=True, default=generate_uuid)
    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt = Column(Integer, nullable=False, default=1)
    status = Column(String(20), nullable=False)
    unit_pass = Column(Integer, nullable=False, default=0)
    unit_fail = Column(Integer, nullable=False, default=0)
    integration_pass = Column(Integer, nullable=False, default=0)
    integration_fail = Column(Integer, nullable=False, default=0)
    coverage = Column(Float, nullable=True)
    latency = Column(String(50), nullable=True)
    failures = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class EscalationRow(Base):
    __tablename__ = "escalations"

    id = Column(String, primary_key=True, default=generate_uuid)
    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    escalation_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=True)
    reason = Column(Text, nullable=False)
    recommendation = Column(Text, nullable=True)
    findings = Column(Text, nullable=True)
    resolved = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)


class MemoryEntryRow(Base):
    __tablename__ = "memory_entries"

    id = Column(String, primary_key=True, default=generate_uuid)
    content = Column(Text, nullable=False)
    tags = Column(JSON, nullable=False, default=list)
    source_task_id = Column(String, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    score = Column(Float, nullable=True)
    metadata_json = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
