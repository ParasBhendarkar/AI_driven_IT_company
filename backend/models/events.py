import json
from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from models.schemas import AgentRole, TaskStatus


class AgentEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str
    agent: str
    description: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().strftime("%H:%M:%S"))
    type: str = "info"
    payload: dict | None = None

    def to_sse(self) -> str:
        return f"data: {self.model_dump_json()}\n\n"


class TaskStatusEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    task_id: str
    status: str
    current_agent: str | None = None
    retry_count: int = 0
    progress: int = 0
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_sse(self) -> str:
        return f"event: status\ndata: {self.model_dump_json()}\n\n"
