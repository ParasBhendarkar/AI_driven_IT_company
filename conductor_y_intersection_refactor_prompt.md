# Conductor — Y-Intersection Dual-Path Architecture Refactor
## Autonomous Coding Agent Instruction Prompt

---

## CONTEXT & RULES FOR THIS AGENT

You are refactoring the **Conductor** backend and frontend codebase.
The goal is to introduce a **Y-Intersection routing pattern** that splits
incoming work into two distinct execution paths based on a `request_type` field:

- **`"module"`** — High-level business requests. Runs the full C-suite chain
  (CEO → CTO → Manager), then fans out to **parallel Developer agents** via
  LangGraph's `Send` API, each working on an isolated `feature/<slug>` branch.
  Parallel PRs are merged by a new `tech_lead_merge` node before QA.
- **`"task"`** — Low-level bug fixes or single-file edits. Bypasses all
  C-suite agents and routes directly to **QA Planner → Developer → QA Runner**
  in a strict TDD sequential loop.

**Hard rules for this agent:**
1. Do NOT rewrite any file wholesale unless explicitly told to. Perform surgical,
   targeted edits using the exact method (insert after line X, replace function Y,
   add field Z) described in each step.
2. Every new Python type, field, or class must be imported wherever it is used.
3. All new LangGraph nodes must be registered with `_builder.add_node(...)` and
   wired with edges/conditional_edges before `_builder.compile()` is called.
4. Maintain full backward compatibility: all existing `"task"` API calls that
   omit `request_type` must default to `"task"` path behaviour.
5. Do not touch `backend/agent/ceo.py`, `backend/agent/cto.py`,
   `backend/agent/ciso.py`, `backend/agent/devops.py`, or
   `backend/agent/critic.py` unless a step explicitly says to.
6. Run `mypy --strict` mentally on every new Python type annotation before
   writing it. Use `Annotated[list[X], operator.add]` correctly.
7. The `GraphState` TypedDict in `backend/core/graph.py` is the LangGraph
   **state schema** — parallel-safe fields must use `Annotated` with a reducer
   function here, not in `TaskState`.

---

## STEP 1 — Backend schemas: `backend/models/schemas.py`

### 1.1 — Add `RequestType` enum

Insert this new enum **after the `Priority` enum** (after line `CRITICAL = "Critical"`):

```python
class RequestType(str, Enum):
    TASK = "task"
    MODULE = "module"
```

### 1.2 — Add `SubTask` model

Insert this new Pydantic model **after the `FileChange` model**:

```python
class SubTask(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    description: str
    file_targets: list[str] = Field(default_factory=list)
    branch: str  # feature/<slug> assigned by Manager
    acceptance_criteria: list[str] = Field(default_factory=list)
    pr_number: int | None = None
    commit_hash: str | None = None
    status: str = "pending"  # pending | running | done | failed
```

### 1.3 — Add `PullRequestSummary` model

Insert **after `SubTask`**:

```python
class PullRequestSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pr_number: int
    branch: str
    title: str
    status: str = "open"  # open | merged | failed
    sub_task_id: str | None = None
```

### 1.4 — Extend `TaskCreate`

In the `TaskCreate` model, add one new field **after `context_refs`**:

```python
    request_type: RequestType = RequestType.TASK
```

### 1.5 — Extend `ManagerOutput`

In `ManagerOutput`, add one new field **after `coordination_notes`**:

```python
    sub_tasks: list["SubTask"] = Field(default_factory=list)
```

Since `SubTask` is defined before `ManagerOutput` in this file, no
forward reference is needed. Remove the quotes from `SubTask` if
`SubTask` is already defined above.

### 1.6 — Extend `TaskState`

In `TaskState`, add the following four new fields **after the `ceo_approved`
field** (the last field in the model):

```python
    request_type: RequestType = Field(default=RequestType.TASK)
    tasks_to_build: list[SubTask] = Field(default_factory=list)
    pull_requests: list[PullRequestSummary] = Field(default_factory=list)
    merge_commit_hash: str | None = Field(default=None)
```

### 1.7 — Extend `TaskStatus` enum

Add two new statuses **inside `TaskStatus`**:

```python
    PARALLEL_DEV = "parallel_dev"
    MERGING = "merging"
```

Also add these to the `_compute_progress` mapping in
`backend/services/task_service.py`:

```python
    TaskStatus.PARALLEL_DEV: 40,
    TaskStatus.MERGING: 75,
```

And in `backend/core/graph.py`'s `_compute_progress` function:

```python
    "parallel_dev": 40,
    "merging": 75,
```

---

## STEP 2 — Backend DB model: `backend/models/db.py`

In the `Task` SQLAlchemy model class, add these two new columns **after the
`commit_hash` column**:

```python
    request_type = Column(String(20), nullable=False, default="task")
    sub_tasks = Column(JSON, nullable=True)
    pull_requests = Column(JSON, nullable=True)
    merge_commit_hash = Column(String(100), nullable=True)
```

Then write and apply an Alembic migration **or** add the columns directly
in `backend/database.py` by calling `Base.metadata.create_all(bind=engine)`
if this project uses the `create_all` pattern (check `backend/database.py` —
if it uses `Base.metadata.create_all`, no migration file is needed; the new
columns will be created on next startup with `checkfirst=True`).

---

## STEP 3 — Backend API: `backend/api/tasks.py`

### 3.1 — Import new schemas

At the top of `backend/api/tasks.py`, update the import from `models.schemas`:

```python
from models.schemas import (
    TaskCreate,
    TaskState,
    TaskListItem,
    OverrideRequest,
    RequestType,
)
```

No other changes to this file are needed — the `TaskCreate` schema already
carries `request_type` through to the service layer after Step 1.

---

## STEP 4 — Backend service: `backend/services/task_service.py`

### 4.1 — Import new types

Add `RequestType, SubTask, PullRequestSummary` to the import from
`models.schemas`.

### 4.2 — Thread `request_type` through `create_task`

In the `create_task` function, in the `TaskState(...)` constructor call,
add:

```python
        request_type=data.request_type,
```

In the `TaskRow(...)` constructor call, add:

```python
        request_type=data.request_type.value,
```

### 4.3 — Thread `request_type` through `_rebuild_state_from_postgres`

In `_rebuild_state_from_postgres`, in the `TaskState(...)` constructor,
add:

```python
        request_type=RequestType(row.request_type) if row.request_type else RequestType.TASK,
```

### 4.4 — Update `task_worker.py` Postgres sync

In `backend/workers/task_worker.py`, in the final `session.execute(update(...))`
block inside `_run_task_async`, add `pull_requests` and `merge_commit_hash`
to the `.values(...)` dict:

```python
                    pull_requests=[pr.model_dump() for pr in final_task.pull_requests]
                    if final_task.pull_requests else None,
                    merge_commit_hash=final_task.merge_commit_hash,
```

---

## STEP 5 — LangGraph state: `backend/core/graph.py`

### 5.1 — New imports at the top of the file

Add these imports to the existing import block at the top of
`backend/core/graph.py`:

```python
import operator
from typing import Annotated
from langgraph.types import Send
from models.schemas import SubTask, PullRequestSummary, RequestType
```

### 5.2 — Extend `GraphState`

Replace the existing `GraphState` TypedDict definition with this:

```python
class GraphState(TypedDict):
    task: TaskState
    events: list[AgentEvent]
    # Parallel-safe: each parallel developer branch appends one entry.
    # `operator.add` is the LangGraph reducer for list fan-in.
    pull_requests: Annotated[list[PullRequestSummary], operator.add]
```

`pull_requests` uses `Annotated` with `operator.add` so that when multiple
parallel developer branches complete and return their `pull_requests` list,
LangGraph concatenates them rather than overwriting.

### 5.3 — Add new node: `node_route_request`

Insert this function **before** `node_load_memory`:

```python
async def node_route_request(state: GraphState) -> GraphState:
    """
    Entry router. Reads state['task'].request_type and emits a routing event.
    Does NOT change any agent state — routing is handled by the conditional
    edge `route_by_request_type` that follows this node.
    """
    logger.info("NODE ENTERED: route_request")
    task = state["task"]
    await _emit(
        state,
        f"Request type detected: {task.request_type.value} — routing accordingly",
        event_type="info",
        payload={"request_type": task.request_type.value},
    )
    return state
```

### 5.4 — Add new node: `node_qa_planner`

Insert after `node_route_request`:

```python
async def node_qa_planner(state: GraphState) -> GraphState:
    """
    Task path entry point. Runs before Developer on the sequential Task path.
    Reads the task description + acceptance criteria and emits a structured
    test plan into state so Developer knows what tests to make pass.
    Uses QAAgent in planning mode — no test runner, just LLM analysis.
    """
    logger.info("NODE ENTERED: qa_planner")
    from agent.qa_planner import QAPlannerAgent

    task = state["task"]
    await _set_status(state, TaskStatus.RUNNING, "QA Planner")
    updated_task = await QAPlannerAgent().run(task)
    state["task"] = updated_task
    return state
```

### 5.5 — Add new node: `node_assign_parallel_developers`

Insert after `node_qa_planner`:

```python
async def node_assign_parallel_developers(state: GraphState) -> list[Send]:
    """
    Fan-out node for the Module path.
    Reads state['task'].tasks_to_build (populated by Manager agent)
    and emits one `Send('parallel_developer', ...)` per sub-task.
    Each Send carries an isolated GraphState copy so developers don't share state.
    Returns a list of Send objects — LangGraph executes them in parallel.
    """
    logger.info("NODE ENTERED: assign_parallel_developers")
    task = state["task"]

    if not task.tasks_to_build:
        logger.warning("assign_parallel_developers: tasks_to_build is empty, skipping fan-out")
        # Return empty list — LangGraph will treat this as a no-op fan-out
        # and the fan-in node (tech_lead_merge) will receive an empty pull_requests list.
        return []

    sends: list[Send] = []
    for sub_task in task.tasks_to_build:
        # Build an isolated TaskState for this sub-task's developer branch.
        sub_state = task.model_copy(deep=True)
        sub_state.title = sub_task.title
        sub_state.description = sub_task.description
        sub_state.branch = sub_task.branch           # feature/<slug>
        sub_state.acceptance_criteria = sub_task.acceptance_criteria
        # Carry the sub_task id so the developer can tag its PR output.
        sub_state.current_sub_task_id = sub_task.id  # see Step 1 — add this field below

        sends.append(Send("parallel_developer", {"task": sub_state, "events": [], "pull_requests": []}))

    await _emit(
        state,
        f"Dispatching {len(sends)} parallel developer agents",
        event_type="info",
        payload={"sub_task_count": len(sends)},
    )
    return sends
```

> **Note:** `current_sub_task_id` is a transient field used only during
> parallel execution. Add it to `TaskState` in `backend/models/schemas.py`:
> ```python
>     current_sub_task_id: str | None = Field(default=None)
> ```

### 5.6 — Add new node: `node_parallel_developer`

Insert after `node_assign_parallel_developers`:

```python
async def node_parallel_developer(state: GraphState) -> GraphState:
    """
    Parallel developer node. Runs inside an isolated LangGraph branch.
    Identical to node_run_developer but appends PullRequestSummary to
    state['pull_requests'] instead of writing to state['task'].pr_number.
    """
    logger.info("NODE ENTERED: parallel_developer")
    from agent.developer import DeveloperAgent

    task = state["task"]
    await _set_status(state, TaskStatus.PARALLEL_DEV, "Developer")
    updated_task = await DeveloperAgent().run(task)
    state["task"] = updated_task

    if updated_task.dev_output and updated_task.dev_output.pr_number:
        pr_summary = PullRequestSummary(
            pr_number=updated_task.dev_output.pr_number,
            branch=updated_task.branch,
            title=updated_task.dev_output.summary[:120],
            status="open",
            sub_task_id=task.current_sub_task_id,
        )
        # Appending to state['pull_requests'] — reduced by operator.add at fan-in.
        state["pull_requests"] = [pr_summary]
    else:
        state["pull_requests"] = []

    return state
```

### 5.7 — Add new node: `node_tech_lead_merge`

Insert after `node_parallel_developer`:

```python
async def node_tech_lead_merge(state: GraphState) -> GraphState:
    """
    Fan-in node. Receives the merged state from all parallel_developer branches.
    state['pull_requests'] is the concatenated list of all PullRequestSummary
    objects (reduced by operator.add).
    Runs TechLeadMergeAgent to open merge PRs sequentially into the base branch.
    Writes merged pull_requests back to state['task'].pull_requests.
    """
    logger.info("NODE ENTERED: tech_lead_merge")
    from agent.tech_lead_merge import TechLeadMergeAgent

    task = state["task"]
    await _set_status(state, TaskStatus.MERGING, "Tech Lead")

    # Persist the collected PRs into the main task state before merging.
    task.pull_requests = state["pull_requests"]

    updated_task = await TechLeadMergeAgent().run(task)
    state["task"] = updated_task
    return state
```

### 5.8 — Add router functions

Add these three router functions to `backend/core/router.py`:

```python
def route_by_request_type(state) -> str:
    """
    Entry router: splits 'module' vs 'task' path.
    'module' → load_memory (then CEO chain)
    'task'   → qa_planner (bypasses C-suite)
    """
    from models.schemas import RequestType
    task = state["task"]
    rt = getattr(task, "request_type", None)
    if rt == RequestType.MODULE or rt == "module":
        logger.info("EDGE ROUTING from route_request: 'module' → load_memory")
        return "load_memory"
    logger.info("EDGE ROUTING from route_request: 'task' → qa_planner")
    return "qa_planner"


def route_after_tech_lead_merge(state) -> str:
    """
    After merge, always proceed to QA.
    If merge failed (no merge_commit_hash), escalate.
    """
    task = state["task"]
    if not task.merge_commit_hash:
        logger.info("EDGE ROUTING from tech_lead_merge: 'escalate_human' (merge failed)")
        return "escalate_human"
    logger.info("EDGE ROUTING from tech_lead_merge: 'qa'")
    return "qa"


def route_after_qa_planner(state) -> str:
    """QA planner always proceeds to developer on Task path."""
    logger.info("EDGE ROUTING from qa_planner: 'developer'")
    return "developer"
```

Import `route_by_request_type`, `route_after_tech_lead_merge`, and
`route_after_qa_planner` in `backend/core/graph.py`:

```python
from core.router import (
    route_after_qa,
    route_after_ciso,
    route_after_critic,
    route_after_ceo,
    route_after_tl_review,
    route_after_tl_final,
    route_by_request_type,       # NEW
    route_after_tech_lead_merge, # NEW
    route_after_qa_planner,      # NEW
)
```

### 5.9 — Rewire the graph

Replace the entire `_builder = StateGraph(GraphState)` block at the bottom
of `backend/core/graph.py` with the following. This is the complete new
wiring — read carefully and implement exactly as written:

```python
_builder = StateGraph(GraphState)

# ── Node registration ────────────────────────────────────────────────────────
_builder.add_node("route_request",              node_route_request)
_builder.add_node("load_memory",               node_load_memory)
_builder.add_node("qa_planner",                node_qa_planner)
_builder.add_node("ceo",                       node_run_ceo)
_builder.add_node("cto",                       node_run_cto)
_builder.add_node("manager",                   node_run_manager)
_builder.add_node("team_leader",               node_run_team_leader)
_builder.add_node("tl_review",                 node_run_tl_review)
_builder.add_node("tl_final",                  node_run_tl_final)
_builder.add_node("assign_parallel_developers", node_assign_parallel_developers)
_builder.add_node("parallel_developer",        node_parallel_developer)
_builder.add_node("tech_lead_merge",           node_tech_lead_merge)
_builder.add_node("developer",                 node_run_developer)
_builder.add_node("qa",                        node_run_qa)
_builder.add_node("ciso",                      node_run_ciso)
_builder.add_node("critic",                    node_run_critic)
_builder.add_node("escalate_human",            node_escalate_human)
_builder.add_node("deploy",                    node_deploy)
_builder.add_node("write_memory",              node_write_memory)

# ── Entry point ──────────────────────────────────────────────────────────────
_builder.set_entry_point("route_request")

# ── Y-Intersection split ─────────────────────────────────────────────────────
_builder.add_conditional_edges("route_request", route_by_request_type, {
    "load_memory": "load_memory",   # module path
    "qa_planner":  "qa_planner",    # task path
})

# ── MODULE path: C-suite chain ───────────────────────────────────────────────
_builder.add_edge("load_memory", "ceo")
_builder.add_conditional_edges("ceo", route_after_ceo, {
    "cto":            "cto",
    "escalate_human": "escalate_human",
})
_builder.add_edge("cto",     "manager")
# Manager populates tasks_to_build; then fan-out.
_builder.add_edge("manager", "assign_parallel_developers")

# ── MODULE path: parallel fan-out ────────────────────────────────────────────
# assign_parallel_developers returns list[Send] — LangGraph handles fan-out automatically.
# Each Send targets "parallel_developer". Fan-in happens at "tech_lead_merge".
_builder.add_edge("parallel_developer", "tech_lead_merge")

# ── MODULE path: merge + QA ──────────────────────────────────────────────────
_builder.add_conditional_edges("tech_lead_merge", route_after_tech_lead_merge, {
    "qa":             "qa",
    "escalate_human": "escalate_human",
})

# ── TASK path: sequential TDD loop ──────────────────────────────────────────
_builder.add_edge("qa_planner", "developer")
# After developer on TASK path → tl_review (same gate as module path)
_builder.add_edge("developer",  "tl_review")
_builder.add_conditional_edges("tl_review", route_after_tl_review, {
    "qa":             "qa",
    "developer":      "developer",
    "escalate_human": "escalate_human",
})

# ── Shared QA → CISO → Critic → Deploy path (both paths converge here) ───────
_builder.add_conditional_edges("qa", route_after_qa, {
    "ciso":           "ciso",
    "developer":      "developer",
    "critic":         "critic",
    "escalate_human": "escalate_human",
})
_builder.add_conditional_edges("ciso", route_after_ciso, {
    "deploy":         "deploy",
    "developer":      "developer",
    "escalate_human": "escalate_human",
})
_builder.add_conditional_edges("critic", route_after_critic, {
    "developer":      "developer",
    "deploy":         "deploy",
    "escalate_human": "escalate_human",
})

# ── Terminal edges ────────────────────────────────────────────────────────────
_builder.add_edge("escalate_human", END)
_builder.add_edge("deploy",         "tl_final")
_builder.add_conditional_edges("tl_final", route_after_tl_final, {
    "write_memory":   "write_memory",
    "developer":      "developer",
    "escalate_human": "escalate_human",
})
_builder.add_edge("write_memory", END)

graph = _builder.compile()
```

---

## STEP 6 — New agent: `backend/agent/qa_planner.py`

Create this new file at `backend/agent/qa_planner.py`:

```python
from __future__ import annotations

import json
import logging
import time

from agent.base import BaseAgent
from models.schemas import TaskState

logger = logging.getLogger(__name__)


class QAPlannerAgent(BaseAgent):
    """
    Task-path entry agent. Analyses the task description and acceptance
    criteria and writes a structured TDD test plan into state.
    The Developer agent reads this plan and writes code to make it pass.
    """
    role = "QA Planner"
    model = "ollama/qwen2.5-coder:3b"

    SYSTEM_PROMPT = """
You are a QA Planner agent in an autonomous AI development company.
You receive a task description and acceptance criteria.
Your job is to write a concrete TDD test plan that a Developer agent will implement.

Respond ONLY with valid JSON — no prose, no markdown:
{
  "test_plan": [
    {
      "test_name": "test_<specific_function_or_behaviour>",
      "test_file": "tests/test_<module>.py",
      "description": "one sentence: what this test verifies",
      "assertion": "exact assertion or behaviour to check"
    }
  ],
  "files_to_modify": ["exact/file/path.py"],
  "implementation_hint": "brief guidance on what the developer needs to implement"
}

Rules:
- Every test must be pytest-compatible.
- test_name must be a valid Python identifier starting with test_.
- files_to_modify must use real paths from the repo structure if known.
- If repo structure is unknown, use conventional paths (src/, tests/).
- implementation_hint must be specific — not "implement the feature".
"""

    async def run(self, state: TaskState) -> TaskState:
        logger.info("NODE ENTERED: qa_planner")
        start = time.time()

        try:
            await self._publish(state.task_id, "Generating TDD test plan...")

            prompt = self._build_prompt(state)
            messages = [{"role": "user", "content": prompt}]

            response = await self._call_llm(
                messages=messages,
                system=self.SYSTEM_PROMPT,
                temperature=0.1,
                max_tokens=1500,
            )

            if response is None:
                logger.warning("QAPlanner _call_llm returned None, using passthrough")
                return state

            content = response.choices[0].message.content or ""
            latency = time.time() - start
            tokens = response.usage.total_tokens if response.usage else 0

            plan = _parse_plan(content)

            # Inject the test plan into state.description so Developer reads it.
            if plan:
                enriched = (
                    f"{state.description}\n\n"
                    f"--- TDD TEST PLAN (implement code to satisfy these tests) ---\n"
                    f"Files to modify: {', '.join(plan.get('files_to_modify', []))}\n"
                    f"Implementation hint: {plan.get('implementation_hint', '')}\n\n"
                    f"Tests that must pass:\n"
                )
                for t in plan.get("test_plan", []):
                    enriched += (
                        f"  [{t['test_file']}::{t['test_name']}] "
                        f"{t['description']} — assert: {t['assertion']}\n"
                    )
                state.description = enriched

                # Inject file targets into team_leader_output.file_targets so
                # Developer._extract_paths picks them up correctly.
                if state.team_leader_output is None:
                    from models.schemas import TeamLeaderOutput
                    state.team_leader_output = TeamLeaderOutput(
                        tickets=["T1: Implement code to satisfy the TDD test plan"],
                        enriched_description=enriched,
                        enriched_acceptance_criteria=state.acceptance_criteria,
                        file_targets=plan.get("files_to_modify", []),
                    )
                else:
                    state.team_leader_output.file_targets = plan.get("files_to_modify", [])

            await self._publish(
                state.task_id,
                f"TDD test plan ready — {len(plan.get('test_plan', []))} tests planned",
                event_type="success",
            )
            await self._log_call(
                task_id=state.task_id,
                action="qa_planner_run",
                input_payload={"acceptance_criteria": state.acceptance_criteria},
                output_payload=plan,
                tokens_used=tokens,
                latency_seconds=latency,
            )
            return state

        except Exception as exc:
            logger.error(f"QAPlanner run() crashed: {exc}")
            return state

    def _build_prompt(self, state: TaskState) -> str:
        lines = [
            f"Task: {state.title}",
            f"Description: {state.description}",
            f"Repo: {state.repo}",
            "",
            "Acceptance criteria:",
        ]
        for c in state.acceptance_criteria:
            lines.append(f"  - {c}")
        lines.append("")
        lines.append("Write the TDD test plan.")
        return "\n".join(lines)


def _parse_plan(content: str) -> dict:
    clean = content.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]
        clean = clean.strip()
    start = clean.find("{")
    end = clean.rfind("}")
    if start != -1 and end != -1:
        clean = clean[start:end + 1]
    try:
        return json.loads(clean)
    except Exception as exc:
        logger.warning("QAPlanner JSON parse failed: %s", exc)
        return {}
```

---

## STEP 7 — New agent: `backend/agent/tech_lead_merge.py`

Create this new file at `backend/agent/tech_lead_merge.py`:

```python
from __future__ import annotations

import logging
import time

from agent.base import BaseAgent
from models.schemas import TaskState, PullRequestSummary

logger = logging.getLogger(__name__)


class TechLeadMergeAgent(BaseAgent):
    """
    Fan-in agent for the Module parallel path.
    Receives all open PRs from parallel Developer branches.
    Merges them sequentially into the base branch using GitHubTool.
    Sets state.merge_commit_hash on success.
    """
    role = "Tech Lead"
    model = "ollama/qwen2.5-coder:3b"

    async def run(self, state: TaskState) -> TaskState:
        logger.info("NODE ENTERED: tech_lead_merge")
        start = time.time()

        from tools.github_tool import GitHubTool
        from memory.short_term import get_task_token
        from config import settings

        try:
            await self._publish(
                state.task_id,
                f"Merging {len(state.pull_requests)} PRs into base branch...",
            )

            access_token = await get_task_token(state.task_id) or settings.GITHUB_TOKEN
            if not access_token:
                raise RuntimeError("Missing GitHub token for TechLeadMerge agent")

            gh = GitHubTool(
                repo=state.repo,
                branch=state.branch,  # base branch
                access_token=access_token,
            )

            merged_count = 0
            failed_prs: list[int] = []
            last_merge_sha: str | None = None

            for pr_summary in state.pull_requests:
                try:
                    result = await gh.merge_pull_request(
                        pr_number=pr_summary.pr_number,
                        commit_message=f"chore: merge feature branch {pr_summary.branch} [conductor]",
                    )
                    sha = result.get("sha") or result.get("merge_commit_sha")
                    if sha:
                        last_merge_sha = sha
                        pr_summary.status = "merged"
                        merged_count += 1
                        await self._publish(
                            state.task_id,
                            f"Merged PR #{pr_summary.pr_number} ({pr_summary.branch})",
                            event_type="success",
                            payload={"pr_number": pr_summary.pr_number, "sha": sha},
                        )
                    else:
                        pr_summary.status = "failed"
                        failed_prs.append(pr_summary.pr_number)
                except Exception as pr_exc:
                    logger.error("Failed to merge PR #%s: %s", pr_summary.pr_number, pr_exc)
                    pr_summary.status = "failed"
                    failed_prs.append(pr_summary.pr_number)

            state.merge_commit_hash = last_merge_sha

            if failed_prs:
                state.last_error = f"PRs failed to merge: {failed_prs}"
                await self._publish(
                    state.task_id,
                    f"Merge incomplete — {len(failed_prs)} PRs failed: {failed_prs}",
                    event_type="warning",
                )
            else:
                await self._publish(
                    state.task_id,
                    f"All {merged_count} PRs merged — SHA: {last_merge_sha}",
                    event_type="success",
                )

            latency = time.time() - start
            await self._log_call(
                task_id=state.task_id,
                action="tech_lead_merge",
                input_payload={"pr_count": len(state.pull_requests)},
                output_payload={
                    "merged": merged_count,
                    "failed": failed_prs,
                    "merge_sha": last_merge_sha,
                },
                latency_seconds=latency,
            )

            return state

        except Exception as exc:
            logger.error(f"TechLeadMerge run() crashed: {exc}")
            state.last_error = str(exc)
            return state
```

> **Dependency note:** `GitHubTool` in `backend/tools/github_tool.py` must
> have a `merge_pull_request(pr_number: int, commit_message: str) -> dict`
> method. If it does not exist, add it as follows in `backend/tools/github_tool.py`:
>
> ```python
> async def merge_pull_request(self, pr_number: int, commit_message: str) -> dict:
>     """Merge a PR by number using the GitHub API. Returns the merge result dict."""
>     import asyncio
>     def _do_merge():
>         pr = self.repo.get_pull(pr_number)
>         result = pr.merge(commit_message=commit_message, merge_method="squash")
>         return {"sha": result.sha, "merged": result.merged, "message": result.message}
>     return await asyncio.to_thread(_do_merge)
> ```

---

## STEP 8 — Manager agent: `backend/agent/manager.py`

### 8.1 — Update `SYSTEM_PROMPT`

In `ManagerAgent.SYSTEM_PROMPT`, replace the JSON schema block with this
extended version that adds `sub_tasks`:

```
Return exactly this shape:
{
  "work_packages": [
    "WP1: Create database schema for anomaly events",
    "WP2: Build anomaly detector model class"
  ],
  "execution_order": ["WP1", "WP2"],
  "file_assignments": [
    "WP1: src/db/migrations/001_anomaly_schema.py",
    "WP2: src/models/anomaly_detector.py"
  ],
  "acceptance_criteria": [
    "WP1: migration runs without error",
    "WP2: detector returns score 0.0-1.0"
  ],
  "risks": "WP2 depends on WP1 schema.",
  "coordination_notes": "Use async patterns throughout.",
  "sub_tasks": [
    {
      "title": "Create anomaly schema migration",
      "description": "Write and apply Alembic migration for anomaly_events table",
      "file_targets": ["src/db/migrations/001_anomaly_schema.py"],
      "branch": "feature/anomaly-schema-migration",
      "acceptance_criteria": ["migration runs without error, table has correct columns"]
    },
    {
      "title": "Build anomaly detector model",
      "description": "Implement AnomalyDetector class with predict() returning float 0.0-1.0",
      "file_targets": ["src/models/anomaly_detector.py"],
      "branch": "feature/anomaly-detector-model",
      "acceptance_criteria": ["predict() returns float in range [0, 1]"]
    }
  ]
}

Additional rules for sub_tasks:
- Every work package must have exactly one corresponding entry in sub_tasks.
- sub_tasks[n].branch must be in the format: feature/<kebab-case-title-slug>
  Use only lowercase letters, digits, and hyphens. Max 50 characters.
  Example: "feature/anomaly-schema-migration"
- sub_tasks[n].file_targets must be a list of real file paths from file_assignments.
- sub_tasks[n].acceptance_criteria must be the same criteria as the corresponding WP.
- sub_tasks[n].title must be short (< 60 chars) and describe the isolated deliverable.
```

### 8.2 — Update `_parse_manager_response`

Replace `_parse_manager_response` with this version that also parses `sub_tasks`:

```python
def _parse_manager_response(content: str) -> ManagerOutput:
    from models.schemas import SubTask
    import re

    clean = content.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]
        clean = clean.strip()

    start = clean.find("{")
    end = clean.rfind("}")
    if start != -1 and end != -1:
        clean = clean[start:end + 1]

    try:
        data = json.loads(clean)

        raw_sub_tasks = data.get("sub_tasks", [])
        parsed_sub_tasks: list[SubTask] = []
        for st in raw_sub_tasks:
            # Enforce branch naming convention
            branch = st.get("branch", "")
            if not branch.startswith("feature/"):
                slug = re.sub(r"[^\w\s-]", "", st.get("title", "task").lower())
                slug = re.sub(r"[\s_-]+", "-", slug).strip("-")[:42]
                branch = f"feature/{slug}"
            parsed_sub_tasks.append(SubTask(
                title=st.get("title", "Unnamed sub-task"),
                description=st.get("description", ""),
                file_targets=st.get("file_targets", []),
                branch=branch,
                acceptance_criteria=st.get("acceptance_criteria", []),
            ))

        return ManagerOutput(
            work_packages=data.get("work_packages", []),
            execution_order=data.get("execution_order", []),
            file_assignments=data.get("file_assignments", []),
            acceptance_criteria=data.get("acceptance_criteria", []),
            risks=data.get("risks", ""),
            coordination_notes=data.get("coordination_notes", ""),
            sub_tasks=parsed_sub_tasks,
        )
    except Exception as exc:
        logger.warning("Manager JSON parse failed: %s", exc)
        return ManagerOutput(
            work_packages=["WP1: Implement the requested feature"],
            execution_order=["WP1"],
            coordination_notes=content[:300] if content else "",
        )
```

### 8.3 — Thread `sub_tasks` into `TaskState` after manager runs

In `backend/core/graph.py`, update `node_run_manager` to propagate
`sub_tasks` from manager output into `task.tasks_to_build`:

```python
async def node_run_manager(state: GraphState) -> GraphState:
    logger.info("NODE ENTERED: manager")
    from agent.manager import ManagerAgent

    task = state["task"]
    await _set_status(state, TaskStatus.RUNNING, "CEO/Manager")
    updated = await ManagerAgent().run(task)

    # Propagate sub_tasks into tasks_to_build for fan-out node.
    if updated.manager_output and updated.manager_output.sub_tasks:
        updated.tasks_to_build = updated.manager_output.sub_tasks

    state["task"] = updated
    return state
```

---

## STEP 9 — Developer agent: `backend/agent/developer.py`

### 9.1 — Update `SYSTEM_PROMPT` branch instruction

In `DeveloperAgent.SYSTEM_PROMPT`, find the `Rules:` section and add this
as the **first rule**, before all existing rules:

```
- BRANCH ISOLATION: You are working on branch {branch}. This branch already
  exists — the orchestrator created it before calling you. Do NOT create new
  branches. All commits go to {branch} only.
- If you are given a TDD test plan (lines starting with "---  TDD TEST PLAN"),
  your primary goal is to write code that makes those specific tests pass.
  Write the test files first if they do not exist, then write the implementation.
```

> **Implementation note:** `{branch}` in the system prompt is a template
> placeholder. In `DeveloperAgent.run()`, replace this prompt string dynamically
> using Python's `str.replace` before passing it to `_call_llm`. Specifically,
> after constructing `messages`, do:
>
> ```python
> system_with_branch = self.SYSTEM_PROMPT.replace("{branch}", state.branch)
> response = await self._call_llm(
>     messages=messages,
>     system=system_with_branch,   # use interpolated version
>     temperature=0.1,
>     max_tokens=4096,
>     timeout_seconds=240,
>     json_mode=True,
> )
> ```

### 9.2 — Remove plain-text content fallback (Bug 4 fix from previous session)

In `_decode_content`, ensure that when `content_b64` is absent, it falls
back to the plain `"content"` key:

```python
def _decode_content(self, file_item: dict) -> str:
    content_b64 = file_item.get("content_b64")
    if isinstance(content_b64, str) and content_b64:
        try:
            return base64.b64decode(content_b64).decode("utf-8")
        except Exception:
            logger.warning("Invalid content_b64 for path %s", file_item.get("path"))
    # Fallback: plain UTF-8 content key (preferred for lightweight models)
    return str(file_item.get("content", ""))
```

---

## STEP 10 — Frontend types: `frontend/src/types/task.ts`

### 10.1 — Add `RequestType` and extend `Task`

In `frontend/src/types/task.ts`, add:

```typescript
export type RequestType = 'task' | 'module';

export interface SubTask {
  id: string;
  title: string;
  description: string;
  branch: string;
  status: 'pending' | 'running' | 'done' | 'failed';
  pr_number?: number;
}

export interface PullRequestSummary {
  pr_number: number;
  branch: string;
  title: string;
  status: 'open' | 'merged' | 'failed';
  sub_task_id?: string;
}
```

In the existing `Task` interface, add these fields:

```typescript
  requestType?: RequestType;
  tasksToBuild?: SubTask[];
  pullRequests?: PullRequestSummary[];
  mergeCommitHash?: string;
```

Also add these two new `TaskStatus` values to the union type:

```typescript
  | 'parallel_dev'
  | 'merging'
```

---

## STEP 11 — Frontend API client: `frontend/src/lib/backend.ts`

In the `toCamelTask` function, add these new field mappings inside the
returned object literal:

```typescript
  requestType: (task.requestType ?? task.request_type ?? 'task') as RequestType,
  tasksToBuild: task.tasksToBuild ?? task.tasks_to_build ?? [],
  pullRequests: task.pullRequests ?? task.pull_requests ?? [],
  mergeCommitHash: task.mergeCommitHash ?? task.merge_commit_hash ?? undefined,
```

Add the `RequestType` import at the top of the file:

```typescript
import type { AgentRole } from '../types/agent';
import type {
  Task,
  TaskEvent,
  QAResult,
  MemoryEntry,
  Escalation,
  Priority,
  RequestType,         // ADD THIS
} from '../types/task';
```

---

## STEP 12 — Frontend modal: `frontend/src/components/tasks/TaskCreateModal.tsx`

This is the most significant frontend change. Apply the following surgical
edits:

### 12.1 — Extend `TaskFormData` interface

Replace the existing `TaskFormData` interface with:

```typescript
export interface TaskFormData {
  title: string;
  description: string;
  repo: string;
  branch: string;
  priority: 'Low' | 'Medium' | 'High' | 'Critical';
  acceptance_criteria: string[];
  context_refs: string[];
  request_type: 'task' | 'module';
}
```

### 12.2 — Extend `INITIAL_FORM_DATA`

Replace `INITIAL_FORM_DATA` with:

```typescript
const INITIAL_FORM_DATA: TaskFormData = {
  title: '',
  description: '',
  repo: '',
  branch: '',
  priority: 'Medium',
  acceptance_criteria: [''],
  context_refs: [],
  request_type: 'task',
};
```

### 12.3 — Add toggle state

Inside the `TaskCreateModal` component function, after the existing
`useState` declarations, add:

```typescript
  const [requestType, setRequestType] = useState<'task' | 'module'>('task');
```

### 12.4 — Update `handleSubmit` to include `request_type`

In `handleSubmit`, in the `cleanedData` object, add:

```typescript
      request_type: requestType,
```

### 12.5 — Add the toggle UI

Inside the `<form>` element, as the **very first child** (before the
`githubError` block), insert this toggle:

```tsx
          {/* Request type toggle */}
          <div className="flex items-center gap-1 p-1 bg-[#0F0F0F] border border-[#2A2A2A] rounded-xl w-fit">
            <button
              type="button"
              onClick={() => {
                setRequestType('task');
                setFormData((prev) => ({ ...prev, request_type: 'task' }));
              }}
              className={cn(
                'px-5 py-2 rounded-lg text-sm font-medium transition-all',
                requestType === 'task'
                  ? 'bg-indigo-600 text-white shadow'
                  : 'text-[#A0A0A0] hover:text-[#F5F5F5]',
              )}
            >
              Create Task
            </button>
            <button
              type="button"
              onClick={() => {
                setRequestType('module');
                setFormData((prev) => ({ ...prev, request_type: 'module' }));
              }}
              className={cn(
                'px-5 py-2 rounded-lg text-sm font-medium transition-all',
                requestType === 'module'
                  ? 'bg-violet-600 text-white shadow'
                  : 'text-[#A0A0A0] hover:text-[#F5F5F5]',
              )}
            >
              Create Module
            </button>
          </div>

          {/* Contextual hint */}
          <p className="text-xs text-[#5A5A5A] -mt-2">
            {requestType === 'task'
              ? 'Task: single bug fix or file edit — goes straight to Developer in TDD loop.'
              : 'Module: high-level business feature — runs CEO → CTO → Manager → parallel Developers.'}
          </p>
```

### 12.6 — Update the modal header and submit button to reflect `requestType`

Replace the modal header `<h2>` text:

```tsx
          <h2 className="text-xl font-semibold text-[#F5F5F5]">
            {requestType === 'module' ? 'Create New Module' : 'Create New Task'}
          </h2>
```

Replace the submit button label:

```tsx
            {isSubmitting
              ? (requestType === 'module' ? 'Creating Module...' : 'Creating Task...')
              : (requestType === 'module' ? 'Create Module' : 'Create Task')}
```

### 12.7 — Conditionally hide `branch` field for modules

Modules create their own `feature/` branches automatically — the base branch
is still needed for the merge target but should be pre-set and not editable.

Wrap the Branch `<select>` block with a conditional:

```tsx
            {/* Show branch selector for both; for modules it becomes 'merge target base' */}
            <div className="space-y-2">
              <label className="text-sm font-medium text-[#F5F5F5] flex items-center gap-2">
                <GitBranch className="w-4 h-4" />
                {requestType === 'module' ? 'Merge target branch' : 'Branch'}
                <span className="text-red-400">*</span>
              </label>
              {/* ... existing branch select JSX unchanged ... */}
            </div>
```

Only the label text changes based on `requestType`; the select control itself
is unchanged.

---

## STEP 13 — Validation: things to verify after implementation

Run these checks in order. Do not proceed to the next check if the prior one fails.

1. **Schema check:** `python -c "from models.schemas import TaskState, SubTask, PullRequestSummary, RequestType; print('OK')"` — must print OK.

2. **Graph compile check:** `python -c "from core.graph import graph; print(graph.get_graph().nodes.keys())"` — output must include `route_request`, `qa_planner`, `assign_parallel_developers`, `parallel_developer`, `tech_lead_merge`.

3. **Router unit test:** Write and run a pytest test:
   ```python
   def test_route_by_request_type_task():
       from core.router import route_by_request_type
       from models.schemas import TaskState, RequestType
       state = {"task": TaskState(
           title="t", description="d", repo="r/r", branch="main",
           request_type=RequestType.TASK
       ), "events": [], "pull_requests": []}
       assert route_by_request_type(state) == "qa_planner"

   def test_route_by_request_type_module():
       from core.router import route_by_request_type
       from models.schemas import TaskState, RequestType
       state = {"task": TaskState(
           title="t", description="d", repo="r/r", branch="main",
           request_type=RequestType.MODULE
       ), "events": [], "pull_requests": []}
       assert route_by_request_type(state) == "load_memory"
   ```

4. **Frontend type check:** `cd frontend && npx tsc --noEmit` — must exit 0.

5. **API payload test:** POST to `/tasks` with `{"request_type": "module", ...}` — response must include `"request_type": "module"`. POST without `request_type` — must default to `"task"`.

6. **Modal smoke test:** Open the modal in browser. Confirm the Task/Module toggle renders, label changes on switch, submit button label updates.

---

## STEP 14 — Migration note

If the project uses SQLAlchemy `create_all` (check `backend/database.py` for
`Base.metadata.create_all(...)`), the new columns added in Step 2 will be
created automatically on next startup — no Alembic migration needed.

If the project uses Alembic, generate a migration:
```
alembic revision --autogenerate -m "add_request_type_and_parallel_fields"
alembic upgrade head
```

The new columns are all nullable or have defaults, so this migration is
non-destructive and zero-downtime safe.

---

## SUMMARY OF FILES CHANGED

| File | Change type |
|------|-------------|
| `backend/models/schemas.py` | Add `RequestType`, `SubTask`, `PullRequestSummary`; extend `TaskCreate`, `ManagerOutput`, `TaskState`, `TaskStatus` |
| `backend/models/db.py` | Add `request_type`, `sub_tasks`, `pull_requests`, `merge_commit_hash` columns to `Task` |
| `backend/core/graph.py` | Add `GraphState.pull_requests` with `Annotated[..., operator.add]`; add 5 new nodes; rewire entire graph |
| `backend/core/router.py` | Add `route_by_request_type`, `route_after_tech_lead_merge`, `route_after_qa_planner` |
| `backend/agent/qa_planner.py` | **New file** — TDD test plan generator |
| `backend/agent/tech_lead_merge.py` | **New file** — PR fan-in merge agent |
| `backend/agent/manager.py` | Extend system prompt + parser to produce `sub_tasks` |
| `backend/agent/developer.py` | Branch instruction in system prompt; plain-content fallback in `_decode_content` |
| `backend/services/task_service.py` | Thread `request_type` through `create_task` and `_rebuild_state_from_postgres` |
| `backend/workers/task_worker.py` | Sync `pull_requests` and `merge_commit_hash` to Postgres on completion |
| `backend/api/tasks.py` | Import `RequestType` (no logic changes needed) |
| `backend/tools/github_tool.py` | Add `merge_pull_request` method if missing |
| `frontend/src/types/task.ts` | Add `RequestType`, `SubTask`, `PullRequestSummary`; extend `Task`, `TaskStatus` |
| `frontend/src/lib/backend.ts` | Add new field mappings in `toCamelTask` |
| `frontend/src/components/tasks/TaskCreateModal.tsx` | Add toggle, conditional labels, extended `TaskFormData` |
