from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    RETRYING = "retrying"
    QA_REVIEW = "qa_review"
    SECURITY_REVIEW = "security_review"
    CRITIC_REVIEW = "critic_review"
    AWAITING_DEPLOY = "awaiting_deploy"
    DEPLOYED = "deployed"
    ESCALATED = "escalated"
    FAILED = "failed"
    BLOCKED = "blocked"


class Priority(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AgentRole(str, Enum):
    DEVELOPER = "Developer"
    QA = "QA"
    CISO = "CISO"
    CRITIC = "Critic"
    DEVOPS = "DevOps"
    CEO_MANAGER = "CEO/Manager"
    ORCHESTRATOR = "Orchestrator"


class OAuthCodeRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str = Field(min_length=1, description="The OAuth code from GitHub redirect")


class GitHubUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    login: str
    name: str | None = None
    avatar_url: str | None = None
    email: str | None = None


class OAuthTokenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    access_token: str
    user: GitHubUser


class VerifyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user: GitHubUser


class GitHubRepository(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    full_name: str
    private: bool
    default_branch: str
    html_url: str


class GitHubBranch(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    protected: bool


class ErrorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    detail: str


class TaskCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    repo: str = Field(min_length=1)
    branch: str = Field(min_length=1)
    priority: Priority = Priority.MEDIUM
    acceptance_criteria: list[str] = Field(default_factory=list)
    context_refs: list[str] = Field(default_factory=list)


class FileChange(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    file_path: str
    change_type: str
    summary: str
    patch: str | None = None


class DevOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    summary: str
    branch: str | None = None
    commit_hash: str | None = None
    pr_number: int | None = None
    files_changed: list[FileChange] = Field(default_factory=list)


class QAFailure(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    error: str
    severity: Severity
    location: str


class TestCounts(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    pass_count: int = Field(alias="pass", ge=0)
    fail: int = Field(ge=0)


class QAResult(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    attempt: int = Field(ge=1)
    status: str
    unit_tests: TestCounts = Field(alias="unitTests")
    integration_tests: TestCounts = Field(alias="integrationTests")
    coverage: float = Field(ge=0, le=100)
    latency: str
    failures: list[QAFailure] = Field(default_factory=list)
    acceptance_met: bool = Field(default=True, alias="acceptanceMet")


class CISOFinding(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    severity: Severity
    location: str
    description: str
    recommendation: str | None = None


class CISOGate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    summary: str
    findings: list[CISOFinding] = Field(default_factory=list)
    blocked: bool = False
    decision: str | None = None


class CriticOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    score: float = Field(ge=0, le=10)
    summary: str
    root_cause: str | None = None
    fix: str | None = None
    confidence: float | None = None
    recommendation: str | None = None
    approved: bool = False


class TaskState(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    task_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    priority: Priority = Priority.MEDIUM
    repo: str
    branch: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    context_refs: list[str] = Field(default_factory=list)
    current_agent: AgentRole | str = Field(default=AgentRole.ORCHESTRATOR, alias="currentAgent")
    retry_count: int = Field(default=0, alias="retryCount", ge=0)
    max_retries: int = Field(default=5, alias="maxRetries", ge=0)
    progress: int = Field(default=0, ge=0, le=100)
    created_at: datetime = Field(default_factory=datetime.utcnow, alias="createdAt")
    updated_at: datetime = Field(default_factory=datetime.utcnow, alias="updatedAt")
    started_at: datetime | None = Field(default=None, alias="startedAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    deployed_at: datetime | None = Field(default=None, alias="deployedAt")
    pr_number: int | None = Field(default=None, alias="prNumber")
    commit_hash: str | None = Field(default=None, alias="commitHash")
    memory_hits: list[dict] = Field(default_factory=list, alias="memoryHits")
    human_override: str | None = Field(default=None, alias="humanOverride")
    error_history: list[str] = Field(default_factory=list, alias="errorHistory")
    last_error: str | None = Field(default=None, alias="lastError")
    dev_output: DevOutput | None = Field(default=None, alias="devOutput")
    qa_result: QAResult | None = Field(default=None, alias="qaResult")
    ciso_gate: CISOGate | None = Field(default=None, alias="cisoGate")
    critic_output: CriticOutput | None = Field(default=None, alias="criticOutput")


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task: TaskState


class TaskListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    title: str
    status: TaskStatus
    priority: Priority
    repo: str
    branch: str
    current_agent: AgentRole | str = Field(alias="currentAgent")
    retry_count: int = Field(default=0, alias="retryCount")
    max_retries: int = Field(default=0, alias="maxRetries")
    progress: int = Field(ge=0, le=100)
    time_elapsed: str = Field(default="", alias="timeElapsed")
    pr_number: int | None = Field(default=None, alias="prNumber")
    created_at: datetime | None = Field(default=None, alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")


class OverrideRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    action: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    notes: str | None = None
    requested_by: str = Field(alias="requestedBy")


class MemoryEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    content: str
    tags: list[str] = Field(default_factory=list)
    source_task_id: str = Field(
        alias="sourceTaskId",
        validation_alias=AliasChoices("sourceTaskId", "source_task_id"),
    )
    agent: AgentRole | str | None = None
    date: datetime | str
    score: float | None = None


class MemoryCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    content: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    source_task_id: str = Field(
        alias="sourceTaskId",
        validation_alias=AliasChoices("sourceTaskId", "source_task_id"),
    )
