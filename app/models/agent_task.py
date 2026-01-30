"""
Agent Task model for tracking AI agent executions.

Tracks goals, sub-tasks, and execution history for AI agents.
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Float, Enum as SQLEnum, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.property import Property, PropertyContact
    from app.models.user import User


class TaskStatus(str, Enum):
    """Agent task execution status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    WAITING = "waiting"  # Waiting for external event (call to end, etc.)
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(str, Enum):
    """Types of agent tasks."""
    CALL = "call"  # Make a phone call
    SMS = "sms"  # Send SMS
    EMAIL = "email"  # Send email (future)
    RESEARCH = "research"  # Research/gather information
    SCHEDULE = "schedule"  # Schedule something
    FOLLOW_UP = "follow_up"  # Follow up on previous interaction
    CUSTOM = "custom"  # Custom instruction


class AgentTask(Base):
    """
    Tracks agent task executions.

    An agent task represents a high-level goal given to the AI agent,
    which may involve multiple actions (calls, SMS, memory lookups, etc.).
    """
    __tablename__ = "agent_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Who initiated this task
    initiated_by_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))

    # Scope
    property_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=True, index=True
    )
    contact_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("property_contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Task definition
    task_type: Mapped[TaskType] = mapped_column(SQLEnum(TaskType), default=TaskType.CUSTOM)
    instruction: Mapped[str] = mapped_column(Text)  # Natural language instruction
    parsed_intent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # AI-parsed intent (JSON)

    # Execution status
    status: Mapped[TaskStatus] = mapped_column(SQLEnum(TaskStatus), default=TaskStatus.PENDING, index=True)
    status_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Context used
    context_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON of context at execution

    # Results
    result_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON of result data

    # Linked resources (IDs of created resources)
    call_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sms_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Execution tracking
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    execution_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Retry tracking
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    initiated_by: Mapped["User"] = relationship("User")
    property: Mapped[Optional["Property"]] = relationship("Property", backref="agent_tasks")
    contact: Mapped[Optional["PropertyContact"]] = relationship("PropertyContact", backref="agent_tasks")


class AgentTaskStep(Base):
    """
    Individual steps within an agent task.

    A task may have multiple steps (e.g., lookup context, make call, extract memories).
    """
    __tablename__ = "agent_task_steps"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("agent_tasks.id", ondelete="CASCADE"), index=True)

    # Step info
    step_number: Mapped[int] = mapped_column(Integer)
    step_type: Mapped[str] = mapped_column(String(50))  # "context_lookup", "call", "sms", "memory_extract", etc.
    description: Mapped[str] = mapped_column(String(500))

    # Status
    status: Mapped[TaskStatus] = mapped_column(SQLEnum(TaskStatus), default=TaskStatus.PENDING)

    # Input/Output
    input_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    output_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    task: Mapped["AgentTask"] = relationship("AgentTask", backref="steps")
