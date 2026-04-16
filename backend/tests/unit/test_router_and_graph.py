import importlib

import pytest

core_graph = importlib.import_module("core.graph")
from core.router import route_after_critic
from models.schemas import (
    CEOOutput,
    CISOGate,
    CTOOutput,
    CriticOutput,
    DevOutput,
    ManagerOutput,
    QAResult,
    TaskState,
    TeamLeaderOutput,
    TestCounts,
)


def test_route_after_critic_returns_deploy_when_approved():
    state = {
        "task": TaskState(
            title="Task",
            description="Desc",
            repo="owner/repo",
            branch="main",
            retry_count=0,
            critic_output=CriticOutput(
                score=9.0,
                summary="Looks good",
                confidence=0.95,
                approved=True,
            ),
        )
    }

    assert route_after_critic(state) == "deploy"


@pytest.mark.anyio
async def test_full_pipeline_reaches_write_memory_without_escalation(monkeypatch):
    async def _noop(*args, **kwargs):
        return None

    async def _no_memory(*args, **kwargs):
        return []

    monkeypatch.setattr(core_graph, "save_state", _noop)
    monkeypatch.setattr(core_graph, "publish_event", _noop)
    monkeypatch.setattr(core_graph, "retrieve_memory", _no_memory)

    from agent.ceo import CEOAgent
    from agent.ciso import CISOAgent
    from agent.cto import CTOAgent
    from agent.developer import DeveloperAgent
    from agent.devops import DevOpsAgent
    from agent.manager import ManagerAgent
    from agent.qa import QAAgent
    from agent.team_leader import TeamLeaderAgent

    async def _run_ceo(self, state):
        state.ceo_output = CEOOutput(goals=["ship"], approved=True)
        state.ceo_approved = True
        return state

    async def _run_cto(self, state):
        state.cto_output = CTOOutput(architecture="simple")
        return state

    async def _run_manager(self, state):
        state.manager_output = ManagerOutput(
            work_packages=["wp1"],
            execution_order=["wp1"],
            file_assignments=["utils.py"],
            acceptance_criteria=["hello function added"],
        )
        return state

    async def _run_tl(self, state):
        state.team_leader_output = TeamLeaderOutput(
            tickets=["T1: Add utils.py hello"],
            file_targets=["utils.py"],
        )
        return state

    async def _run_dev(self, state):
        state.dev_output = DevOutput(summary="done", branch=state.branch)
        state.reviewed_file_contents = {"utils.py": "def hello():\n    return 'hi'\n"}
        return state

    async def _run_tl_review(self, state):
        if state.team_leader_output is None:
            state.team_leader_output = TeamLeaderOutput()
        state.team_leader_output.review_approved = True
        return state

    async def _run_qa(self, state):
        state.qa_result = QAResult(
            attempt=1,
            status="pass",
            unitTests=TestCounts(pass_count=1, fail=0),
            integrationTests=TestCounts(pass_count=0, fail=0),
            coverage=90,
            latency="1s",
            failures=[],
            acceptanceMet=True,
        )
        return state

    async def _run_ciso(self, state):
        state.ciso_gate = CISOGate(status="approved", summary="ok", blocked=False)
        return state

    async def _run_devops(self, state):
        return state

    async def _run_tl_final(self, state):
        if state.team_leader_output is None:
            state.team_leader_output = TeamLeaderOutput()
        state.team_leader_output.final_approved = True
        return state

    monkeypatch.setattr(CEOAgent, "run", _run_ceo)
    monkeypatch.setattr(CTOAgent, "run", _run_cto)
    monkeypatch.setattr(ManagerAgent, "run", _run_manager)
    monkeypatch.setattr(TeamLeaderAgent, "run", _run_tl)
    monkeypatch.setattr(DeveloperAgent, "run", _run_dev)
    monkeypatch.setattr(TeamLeaderAgent, "run_review", _run_tl_review)
    monkeypatch.setattr(QAAgent, "run", _run_qa)
    monkeypatch.setattr(CISOAgent, "run", _run_ciso)
    monkeypatch.setattr(DevOpsAgent, "run", _run_devops)
    monkeypatch.setattr(TeamLeaderAgent, "run_final", _run_tl_final)

    state = TaskState(
        title="Add hello function",
        description="Add hello() to utils.py",
        repo="owner/repo",
        branch="main",
    )

    result = await core_graph.graph.ainvoke({"task": state, "events": []})
    final_task = result["task"]

    assert any("Writing lessons to long-term memory" in e.description for e in result["events"])
    assert final_task.status != "escalated"
    assert not any(e.description.startswith("Escalated to human") for e in result["events"])
