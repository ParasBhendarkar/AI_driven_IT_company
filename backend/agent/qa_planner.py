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
