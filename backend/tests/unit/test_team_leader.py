from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.team_leader import TeamLeaderAgent, _parse_team_leader_response
from models.schemas import (
    CEOOutput,
    CTOOutput,
    ManagerOutput,
    Priority,
    TaskState,
    TeamLeaderOutput,
)


# ---------------------------------------------------------------------------
# _parse_team_leader_response — unit tests (no I/O, no mocking required)
# ---------------------------------------------------------------------------


def test_parse_team_leader_valid_json():
    content = """
    {
      "tickets": [
        "T1: Create src/db/schema.py — add anomaly table with id, timestamp, score columns",
        "T2: Build src/models/detector.py — IsolationForest class with fit and predict methods"
      ],
      "enriched_description": "Build an anomaly detection service backed by IsolationForest. Create the DB schema first, then the model class.",
      "enriched_acceptance_criteria": [
        "test_schema: anomaly table exists with id, timestamp, score columns after migration",
        "test_detector: predict() returns float in range 0.0-1.0 for valid input"
      ],
      "file_targets": ["src/db/schema.py", "src/models/detector.py"],
      "implementation_notes": "Create schema first (T1), then detector (T2) — detector imports schema constants.",
      "unblocking_notes": "If T1 is blocked, stub the schema with an in-memory dict so T2 can proceed independently."
    }
    """

    result = _parse_team_leader_response(content)

    assert isinstance(result.tickets, list)
    assert len(result.tickets) >= 1
    assert isinstance(result.enriched_description, str)
    assert result.enriched_description != ""
    assert isinstance(result.file_targets, list)


def test_parse_team_leader_invalid_json():
    result = _parse_team_leader_response("this is not json")

    assert isinstance(result, TeamLeaderOutput)
    assert len(result.tickets) >= 1  # fallback always has at least 1 ticket


def test_parse_team_leader_strips_fences():
    content = """```json
    {
      "tickets": [
        "T1: Create src/api/anomaly.py — POST /detect endpoint returning anomaly score"
      ],
      "enriched_description": "Build a REST endpoint that wraps the IsolationForest detector.",
      "enriched_acceptance_criteria": [
        "test_endpoint: POST /detect returns 200 with score field for valid payload",
        "test_endpoint: POST /detect returns 422 for missing required fields"
      ],
      "file_targets": ["src/api/anomaly.py"],
      "implementation_notes": "Implement route, then wire detector import.",
      "unblocking_notes": "If detector is unavailable, return a stub score of 0.0."
    }
    ```"""

    result = _parse_team_leader_response(content)

    assert isinstance(result.tickets, list)
    assert len(result.tickets) == 1
    assert "src/api/anomaly.py" in result.file_targets


# ---------------------------------------------------------------------------
# _build_prompt — unit tests
# ---------------------------------------------------------------------------


def test_build_prompt_includes_manager_work_packages():
    team_leader = TeamLeaderAgent()
    state = TaskState(
        title="Build anomaly detection service",
        description="Detect anomalies in real-time event streams.",
        repo="owner/repo",
        branch="main",
        manager_output=ManagerOutput(
            work_packages=["WP1: Create DB schema", "WP2: Build detector"],
            execution_order=["WP1", "WP2"],
            file_assignments=["WP1: src/db/schema.py", "WP2: src/models/detector.py"],
            acceptance_criteria=["WP1: table exists with correct columns"],
            risks="WP2 blocked if WP1 fails",
            coordination_notes="detector imports schema",
        ),
    )

    prompt = team_leader._build_prompt(state)

    assert "WP1" in prompt
    assert "src/db/schema.py" in prompt


def test_build_prompt_without_manager():
    team_leader = TeamLeaderAgent()
    state = TaskState(
        title="Refactor authentication module",
        description="Extract JWT handling into a standalone service.",
        repo="owner/repo",
        branch="main",
        manager_output=None,
    )

    # Must not raise even when manager_output is absent
    prompt = team_leader._build_prompt(state)

    assert "Refactor authentication module" in prompt


def test_build_prompt_includes_cto_guidance():
    team_leader = TeamLeaderAgent()
    state = TaskState(
        title="Add async support",
        description="Convert all I/O-bound operations to async.",
        repo="owner/repo",
        branch="main",
        cto_output=CTOOutput(
            architecture="Async FastAPI service",
            stack=["Python", "FastAPI"],
            components=["src/api/main.py"],
            risks=[],
            technical_notes="Use asyncio throughout",
            repo_structure=["src/api/main.py"],
        ),
    )

    prompt = team_leader._build_prompt(state)

    assert "asyncio" in prompt


# ---------------------------------------------------------------------------
# run() — async integration test (LLM mocked, no real API calls)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_run_enriches_state_description():
    team_leader = TeamLeaderAgent()

    state = TaskState(
        title="Build anomaly detection service",
        description="Original raw founder description.",
        repo="owner/repo",
        branch="main",
        manager_output=ManagerOutput(
            work_packages=["WP1: Create DB schema", "WP2: Build API"],
            execution_order=["WP1", "WP2"],
            file_assignments=["WP1: src/db/schema.py", "WP2: src/api/anomaly.py"],
            acceptance_criteria=["WP1: table exists"],
            risks="WP2 blocked if WP1 fails",
            coordination_notes="API imports schema",
        ),
    )

    llm_json = """{
  "tickets": [
    "T1: Create src/api/anomaly.py — POST /detect endpoint returning anomaly score"
  ],
  "enriched_description": "Full developer brief here",
  "enriched_acceptance_criteria": ["endpoint returns 200"],
  "file_targets": ["src/api/anomaly.py"],
  "implementation_notes": "Create schema first, then API.",
  "unblocking_notes": "Stub detector if schema is missing."
}"""

    mock_usage = MagicMock()
    mock_usage.total_tokens = 42

    mock_message = MagicMock()
    mock_message.content = llm_json

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.usage = mock_usage
    mock_response.choices = [mock_choice]

    team_leader._call_llm = AsyncMock(return_value=mock_response)
    team_leader._publish = AsyncMock()
    team_leader._log_call = AsyncMock()

    result = await team_leader.run(state)

    assert result.description == "Full developer brief here"
    assert result.acceptance_criteria == ["endpoint returns 200"]
    assert result.team_leader_output is not None
    assert len(result.team_leader_output.tickets) == 1


def test_build_review_prompt_includes_actual_file_content():
    team_leader = TeamLeaderAgent()
    state = TaskState(
        title="Add hello helper",
        description="Add hello() to utils.py",
        repo="owner/repo",
        branch="main",
        team_leader_output=TeamLeaderOutput(
            tickets=["T1: Add hello function"],
            file_targets=["utils.py"],
        ),
        reviewed_file_contents={"utils.py": "def hello():\n    return 'hi'\n"},
    )

    prompt = team_leader._build_review_prompt(state)

    assert "Actual code written by Developer:" in prompt
    assert "FILE: utils.py" in prompt
    assert "def hello()" in prompt


@pytest.mark.anyio
async def test_run_review_uses_review_model_and_restores():
    team_leader = TeamLeaderAgent()
    original_model = team_leader.model
    model_seen: dict[str, str] = {}

    state = TaskState(
        title="Task",
        description="Desc",
        repo="owner/repo",
        branch="main",
        team_leader_output=TeamLeaderOutput(),
    )

    async def _fake_call_llm(**kwargs):
        model_seen["value"] = team_leader.model
        mock_usage = MagicMock()
        mock_usage.total_tokens = 1
        mock_message = MagicMock()
        mock_message.content = '{"approved": true, "feedback": "", "issues": []}'
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.usage = mock_usage
        mock_response.choices = [mock_choice]
        return mock_response

    team_leader._call_llm = _fake_call_llm
    team_leader._publish = AsyncMock()
    team_leader._log_call = AsyncMock()

    await team_leader.run_review(state)

    assert model_seen["value"] == team_leader.review_model
    assert team_leader.model == original_model
