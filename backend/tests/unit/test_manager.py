from agent.manager import ManagerAgent, _parse_manager_response
from models.schemas import CEOOutput, CTOOutput, ManagerOutput, Priority, TaskState


def test_parse_manager_valid_json():
    content = """
    {
      "work_packages": [
        "WP1: Create database schema for anomaly events",
        "WP2: Build anomaly detector model class",
        "WP3: Build REST API endpoint for anomaly detection"
      ],
      "execution_order": ["WP1", "WP2", "WP3"],
      "file_assignments": [
        "WP1: src/db/migrations/001_anomaly_schema.py",
        "WP2: src/models/anomaly_detector.py",
        "WP3: src/api/anomaly.py"
      ],
      "acceptance_criteria": [
        "WP1: migration runs without error, table has correct columns",
        "WP2: detector accepts raw input, returns score 0.0-1.0",
        "WP3: endpoint returns 200 with valid payload, 422 on bad input"
      ],
      "risks": "WP2 depends on WP1 schema — blocked if migration fails.",
      "coordination_notes": "WP3 must import from WP2. Use async patterns."
    }
    """

    result = _parse_manager_response(content)

    assert isinstance(result.work_packages, list)
    assert len(result.work_packages) >= 1
    assert isinstance(result.execution_order, list)
    assert isinstance(result.file_assignments, list)
    assert isinstance(result.risks, str)


def test_parse_manager_invalid_json():
    result = _parse_manager_response("this is not json")

    assert isinstance(result, ManagerOutput)
    assert len(result.work_packages) > 0


def test_parse_manager_strips_fences():
    content = """```json
    {
      "work_packages": ["WP1: Add rate limiting middleware"],
      "execution_order": ["WP1"],
      "file_assignments": ["WP1: src/middleware/rate_limit.py"],
      "acceptance_criteria": ["WP1: returns 429 after limit exceeded within window"],
      "risks": "Redis unavailability disables rate limiting entirely — fallback needed.",
      "coordination_notes": "Use slowapi library. Configure per-route limits in main.py."
    }
    ```"""

    result = _parse_manager_response(content)

    assert len(result.work_packages) == 1
    assert "WP1" in result.execution_order
    assert isinstance(result.risks, str)


def test_build_prompt_includes_cto_components():
    manager = ManagerAgent()
    state = TaskState(
        title="Build anomaly detection service",
        description="Detect anomalies in real-time event streams.",
        repo="owner/repo",
        branch="main",
        cto_output=CTOOutput(
            architecture="Microservice with async detector",
            stack=["Python", "FastAPI", "Redis"],
            components=["src/api/anomaly.py", "src/models/detector.py"],
            risks=["Redis TTL mismatch causes stale reads"],
            technical_notes="Use asyncio. Return scores as float 0.0-1.0.",
            repo_structure=["src/api/anomaly.py", "src/models/detector.py"],
        ),
    )

    prompt = manager._build_prompt(state)

    assert "src/api/anomaly.py" in prompt
    assert "Microservice with async detector" in prompt


def test_build_prompt_without_cto():
    manager = ManagerAgent()
    state = TaskState(
        title="Refactor authentication module",
        description="Extract JWT handling into a standalone service.",
        repo="owner/repo",
        branch="main",
        cto_output=None,
    )

    prompt = manager._build_prompt(state)

    assert "Refactor authentication module" in prompt


def test_build_prompt_includes_ceo_goals():
    manager = ManagerAgent()
    state = TaskState(
        title="Improve incident response time",
        description="Build an alerting pipeline to reduce MTTR.",
        repo="owner/repo",
        branch="main",
        ceo_output=CEOOutput(
            goals=["reduce MTTR by 30%"],
            kpis={"alert_latency_ms": "500"},
            constraints={"platform": "AWS only"},
            priority=Priority.HIGH,
            approved=True,
            delegation_notes="Focus on alerting pipeline first.",
        ),
        cto_output=CTOOutput(
            architecture="Lambda-based alerting with SNS fanout",
            stack=["Python", "AWS Lambda", "SNS"],
            components=["src/api/health.py"],
            risks=["Lambda cold start adds latency spike"],
            technical_notes="Use SNS FIFO for ordering.",
            repo_structure=["src/api/health.py"],
        ),
    )

    prompt = manager._build_prompt(state)

    assert "reduce MTTR by 30%" in prompt
    assert "src/api/health.py" in prompt


def test_build_prompt_includes_memory():
    manager = ManagerAgent()
    state = TaskState(
        title="Add database migration support",
        description="Integrate Alembic for schema version control.",
        repo="owner/repo",
        branch="main",
        memory_hits=[
            {"content": "always run migrations first", "score": 0.92},
            {"content": "use alembic upgrade head in CI", "score": 0.85},
        ],
    )

    prompt = manager._build_prompt(state)

    assert "migrations first" in prompt
