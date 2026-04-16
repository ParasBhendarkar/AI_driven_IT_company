from agent.ceo import CEOAgent, _parse_ceo_response
from models.schemas import CEOOutput, Priority, TaskState


def test_parse_ceo_valid_json():
    content = """
    {
      "goals": ["Reduce build time by 20%", "Ship feature this sprint"],
      "kpis": {"build_time_minutes": "8", "delivery_date": "this sprint"},
      "constraints": {"budget": "existing team only"},
      "priority": "High",
      "approved": true,
      "delegation_notes": "Coordinate implementation and validation."
    }
    """

    result = _parse_ceo_response(content)

    assert result.goals
    assert result.priority == Priority.HIGH
    assert result.approved is True


def test_parse_ceo_invalid_json():
    result = _parse_ceo_response("not json at all")

    assert isinstance(result, CEOOutput)
    assert result.approved is True


def test_parse_ceo_strips_fences():
    content = """```json
    {
      "goals": ["Improve reliability"],
      "kpis": {"incident_count": "0"},
      "constraints": {"timeline": "2 weeks"},
      "priority": "Medium",
      "approved": true,
      "delegation_notes": "Keep the scope tight."
    }
    ```"""

    result = _parse_ceo_response(content)

    assert result.goals == ["Improve reliability"]
    assert result.priority == Priority.MEDIUM


def test_build_prompt_includes_memory():
    ceo = CEOAgent()
    state = TaskState(
        title="Improve dashboard performance",
        description="Speed up slow pages.",
        repo="owner/repo",
        branch="main",
        memory_hits=[
            {"content": "Past context item one", "score": 0.9},
            {"content": "Past context item two", "score": 0.8},
        ],
    )

    prompt = ceo._build_prompt(state)

    assert "Past context:" in prompt
    assert "Past context item one" in prompt
    assert "Past context item two" in prompt


def test_build_prompt_includes_override():
    ceo = CEOAgent()
    state = TaskState(
        title="Tune preprocessing",
        description="Improve model stability.",
        repo="owner/repo",
        branch="main",
        human_override="use RobustScaler",
    )

    prompt = ceo._build_prompt(state)

    assert "use RobustScaler" in prompt
