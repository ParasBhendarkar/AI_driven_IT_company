from unittest.mock import AsyncMock

import pytest

from agent.developer import DeveloperAgent
from models.schemas import TaskState


@pytest.mark.anyio
async def test_parse_plan_with_repair_accepts_plain_content_without_repair():
    agent = DeveloperAgent()
    state = TaskState(
        title="Add hello",
        description="Add hello() function to utils.py",
        repo="owner/repo",
        branch="main",
    )
    messages = [{"role": "user", "content": "task prompt"}]
    raw = """
{
  "commit_message": "feat: add hello helper",
  "pr_title": "Add hello helper",
  "pr_body": "Implements hello helper in utils.py",
  "files": [
    {
      "path": "utils.py",
      "summary": "Add hello helper",
      "content": "def hello():\\n    return 'hello'\\n"
    }
  ]
}
"""

    agent._publish = AsyncMock()
    agent._call_llm = AsyncMock()

    plan = await agent._parse_plan_with_repair(raw=raw, messages=messages, state=state)

    assert plan["files"][0]["path"] == "utils.py"
    assert "content" in plan["files"][0]
    assert agent._call_llm.await_count == 0


@pytest.mark.anyio
async def test_deterministic_fallback_plan_is_generic():
    agent = DeveloperAgent()
    state = TaskState(
        title="Add export endpoint",
        description="Implement export endpoint and wire it into API layer",
        repo="owner/repo",
        branch="main",
        context_refs=["api/export.ts"],
    )

    class _FakeGH:
        async def read_file(self, path: str):
            return ""

    plan = await agent._build_deterministic_fallback_plan(state, _FakeGH(), [])

    assert plan["files"]
    assert any("Add export endpoint" in f["content"] for f in plan["files"])
