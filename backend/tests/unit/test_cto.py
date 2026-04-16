from agent.cto import CTOAgent, _parse_cto_response
from models.schemas import CEOOutput, CTOOutput, Priority, TaskState


def test_parse_cto_valid_json():
    content = """
    {
      "architecture": "Deploy a FastAPI endpoint that reads anomaly scores from a Redis sorted set and returns the top N events.",
      "stack": ["Python", "FastAPI", "Redis", "pytest"],
      "components": ["src/api/anomaly.py", "src/services/anomaly_reader.py"],
      "risks": ["Redis key schema mismatch if producer uses a different TTL", "Missing index on score column causes full table scan"],
      "technical_notes": "Use redis.zrevrangebyscore with LIMIT to cap results. Handle empty sets with a 204 response.",
      "repo_structure": ["src/api/anomaly.py", "src/services/anomaly_reader.py", "tests/unit/test_anomaly.py"]
    }
    """

    result = _parse_cto_response(content)

    assert isinstance(result.architecture, str)
    assert len(result.architecture) > 0
    assert isinstance(result.stack, list)
    assert isinstance(result.components, list)


def test_parse_cto_invalid_json():
    result = _parse_cto_response("this is not json")

    assert isinstance(result, CTOOutput)
    assert len(result.architecture) > 0


def test_parse_cto_strips_fences():
    content = """```json
    {
      "architecture": "Use a background Celery worker to process queue items from SQS.",
      "stack": ["Python", "Celery", "AWS SQS"],
      "components": ["workers/sqs_consumer.py"],
      "risks": ["Message visibility timeout shorter than job duration causes duplicate processing"],
      "technical_notes": "Set visibility_timeout to 2x the expected job duration. Use idempotency keys.",
      "repo_structure": ["workers/sqs_consumer.py", "tests/unit/test_sqs_consumer.py"]
    }
    ```"""

    result = _parse_cto_response(content)

    assert "Celery" in result.stack
    assert result.architecture != ""


def test_build_prompt_includes_ceo_goals():
    cto = CTOAgent()
    state = TaskState(
        title="Reduce MTTR for production incidents",
        description="Build alerting pipeline that cuts mean time to resolution.",
        repo="owner/repo",
        branch="main",
        ceo_output=CEOOutput(
            goals=["reduce MTTR by 30%"],
            kpis={"latency": "200ms"},
            constraints={"platform": "AWS only"},
            priority=Priority.HIGH,
            approved=True,
            delegation_notes="Prioritise observability tooling.",
        ),
    )

    prompt = cto._build_prompt(state)

    assert "reduce MTTR by 30%" in prompt
    assert "200ms" in prompt


def test_build_prompt_without_ceo():
    cto = CTOAgent()
    state = TaskState(
        title="Add rate limiting to the public API",
        description="Protect endpoints from abuse with per-IP rate limiting.",
        repo="owner/repo",
        branch="main",
        ceo_output=None,
    )

    prompt = cto._build_prompt(state)

    assert "Add rate limiting to the public API" in prompt


def test_build_prompt_includes_memory():
    cto = CTOAgent()
    state = TaskState(
        title="Improve cache invalidation",
        description="Stale data is served after writes due to missing cache eviction.",
        repo="owner/repo",
        branch="main",
        memory_hits=[
            {"content": "use Redis TTL 60s", "score": 0.95},
            {"content": "apply write-through strategy for user sessions", "score": 0.88},
        ],
    )

    prompt = cto._build_prompt(state)

    assert "Redis TTL" in prompt
