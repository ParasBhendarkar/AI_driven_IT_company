from __future__ import annotations
 
import json
import logging
import time
 
from agent.base import BaseAgent
from models.schemas import ManagerOutput, TaskState
 
logger = logging.getLogger(__name__)
 
 
class ManagerAgent(BaseAgent):
    role = "CEO/Manager"
    model = "ollama/qwen2.5-coder:3b"
 
    SYSTEM_PROMPT = """
You are the AI Manager — the operational execution layer inside an autonomous AI software company.
 
You receive the CTO's technical charter and break it into ordered work packages for the Team Leader to execute.
 
Respond with JSON only. Do not include prose, markdown, or code fences.
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
 
Rules:
- Every work package must have exactly one corresponding entry in sub_tasks.
- sub_tasks[n].branch must be in the format: feature/<kebab-case-title-slug>
  Use only lowercase letters, digits, and hyphens. Max 50 characters.
  Example: "feature/anomaly-schema-migration"
- sub_tasks[n].file_targets must be a list of real file paths from file_assignments.
- sub_tasks[n].acceptance_criteria must be the same criteria as the corresponding WP.
- sub_tasks[n].title must be short (< 60 chars) and describe the isolated deliverable.
"""
 
    async def run(self, state: TaskState) -> TaskState:
        logger.info("NODE ENTERED: manager")
        start = time.time()
 
        try:
            await self._publish(
                state.task_id,
                "Breaking technical charter into work packages...",
            )
 
            prompt = self._build_prompt(state)
            messages = [{"role": "user", "content": prompt}]
 
            response = await self._call_llm(
                messages=messages,
                system=self.SYSTEM_PROMPT,
                temperature=0.2,
                max_tokens=2000,
            )
 
            if response is None:
                logger.warning("Manager _call_llm returned None, using fallback output")
                state.manager_output = ManagerOutput(
                    work_packages=["WP1: Implement the requested feature"],
                    execution_order=["WP1"],
                    file_assignments=["WP1: implement as described in task"],
                    acceptance_criteria=list(state.acceptance_criteria),
                )
                return state
 
            tokens = response.usage.total_tokens if response.usage else 0
            content = response.choices[0].message.content or ""
            latency = time.time() - start
 
            manager_output = _parse_manager_response(content)
            state.manager_output = manager_output
 
            await self._publish(
                state.task_id,
                f"Execution plan ready — "
                f"{len(manager_output.work_packages)} work packages, "
                f"{len(manager_output.file_assignments)} file assignments",
                event_type="success",
                payload=manager_output.model_dump(),
            )
 
            await self._log_call(
                task_id=state.task_id,
                action="manager_execution_plan",
                input_payload={
                    "components": state.cto_output.components if state.cto_output is not None else [],
                    "architecture": state.cto_output.architecture if state.cto_output is not None else "",
                },
                output_payload=manager_output.model_dump(),
                tokens_used=tokens,
                latency_seconds=latency,
            )
 
            return state
 
        except Exception as exc:
            logger.error(f"Manager run() crashed: {exc}")
            if state.manager_output is None:
                state.manager_output = ManagerOutput(
                    work_packages=["WP1: Implement the requested feature"],
                    execution_order=["WP1"],
                    file_assignments=["WP1: implement as described in task"],
                    acceptance_criteria=list(state.acceptance_criteria),
                )
            return state
 
    def _build_prompt(self, state: TaskState) -> str:
        lines = [
            f"Task title: {state.title}",
            f"Task description: {state.description}",
            f"Repo: {state.repo}",
            f"Branch: {state.branch}",
        ]
 
        if state.cto_output is not None:
            lines.append("")
            lines.append(f"Technical architecture: {state.cto_output.architecture}")
 
            lines.append("")
            lines.append(f"Tech stack: {', '.join(state.cto_output.stack)}")
 
            lines.append("")
            lines.append("Components to build:")
            lines.append("\n".join(state.cto_output.components))
 
            lines.append("")
            lines.append("Repo structure from CTO:")
            lines.append("\n".join(state.cto_output.repo_structure))
 
            lines.append("")
            lines.append(f"CTO implementation guidance: {state.cto_output.technical_notes}")
 
            lines.append("")
            lines.append(f"CTO-identified risks: {', '.join(state.cto_output.risks)}")
 
        if state.ceo_output is not None:
            lines.append("")
            lines.append("Business goals:")
            lines.append("\n".join(state.ceo_output.goals))
 
            lines.append("")
            lines.append("KPIs to hit:")
            for metric, target in state.ceo_output.kpis.items():
                lines.append(f"- {metric}: {target}")
 
            lines.append("")
            lines.append("Constraints:")
            for name, value in state.ceo_output.constraints.items():
                lines.append(f"- {name}: {value}")
 
        if state.acceptance_criteria:
            lines.append("")
            lines.append("Founder acceptance criteria:")
            for criterion in state.acceptance_criteria:
                lines.append(f"- {criterion}")
 
        if state.memory_hits:
            lines.append("")
            lines.append("Relevant past execution patterns:")
            for hit in state.memory_hits[:2]:
                lines.append(f"- {hit.get('content', '')}")
 
        lines.append("")
        lines.append(
            "Produce the execution plan with work packages. "
            "Every component from the CTO must appear in a file assignment. "
            "Respect the CTO's repo_structure for file paths."
        )
 
        return "\n".join(lines)
 
 
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
        clean = clean[start : end + 1]
 
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
 
            parsed_sub_tasks.append(
                SubTask(
                    title=st.get("title", "Unnamed sub-task"),
                    description=st.get("description", ""),
                    file_targets=st.get("file_targets", []),
                    branch=branch,
                    acceptance_criteria=st.get("acceptance_criteria", []),
                )
            )
 
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
