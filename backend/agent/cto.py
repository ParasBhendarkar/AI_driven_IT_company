from __future__ import annotations

import json
import logging
import time

from agent.base import BaseAgent
from models.schemas import CTOOutput, TaskState

logger = logging.getLogger(__name__)


class CTOAgent(BaseAgent):
    role = "CEO/Manager"
    model = "ollama/qwen2.5-coder:3b"

    SYSTEM_PROMPT = """
You are the CTO planning agent inside an autonomous AI software company.

Respond with JSON only. Do not include prose, markdown, or code fences.
Return exactly this shape:
{
  "architecture": "one clear paragraph — the specific technical approach for THIS task",
  "stack": ["only the technologies this specific task actually needs"],
  "components": ["actual filenames or service names to build, e.g. src/api/anomaly.py"],
  "risks": ["concrete, specific technical risks for this task, not vague statements like it might fail"],
  "technical_notes": "precise implementation guidance written directly for the Developer agent",
  "repo_structure": ["file paths relative to repo root that the Developer should create or modify"]
}

Rules:
- architecture must describe the specific approach for THIS task, not generic design patterns.
- components must be actual filenames or service names, for example "src/api/anomaly.py", not categories.
- repo_structure must include file paths relative to the repo root, for example "src/api/anomaly.py".
- risks must be concrete and task-specific, for example "Redis TTL mismatch will cause stale reads under high write load".
- technical_notes is read directly by the Developer agent — be precise, include library names, function signatures, and edge cases.
"""

    async def run(self, state: TaskState) -> TaskState:
        logger.info("NODE ENTERED: cto")
        start = time.time()

        try:
            await self._publish(
                state.task_id,
                "Defining technical architecture and stack...",
            )

            prompt = self._build_prompt(state)
            messages = [{"role": "user", "content": prompt}]

            response = await self._call_llm(
                messages=messages,
                system=self.SYSTEM_PROMPT,
                temperature=0.2,
                max_tokens=1500,
            )

            if response is None:
                logger.warning("CTO _call_llm returned None, using fallback output")
                state.cto_output = CTOOutput(
                    architecture="Implement the requested feature directly in the repo",
                    technical_notes="LLM unavailable — implement based on task description",
                )
                return state

            tokens = response.usage.total_tokens if response.usage else 0
            content = response.choices[0].message.content or ""
            latency = time.time() - start

            cto_output = _parse_cto_response(content)
            state.cto_output = cto_output

            await self._publish(
                state.task_id,
                f"Technical charter ready — "
                f"{len(cto_output.components)} components, "
                f"stack: {', '.join(cto_output.stack[:3])}",
                event_type="success",
                payload=cto_output.model_dump(),
            )

            await self._log_call(
                task_id=state.task_id,
                action="cto_charter",
                input_payload={
                    "goals": state.ceo_output.goals if state.ceo_output is not None else [],
                    "kpis":  state.ceo_output.kpis  if state.ceo_output is not None else {},
                },
                output_payload=cto_output.model_dump(),
                tokens_used=tokens,
                latency_seconds=latency,
            )

            return state

        except Exception as exc:
            logger.error(f"CTO run() crashed: {exc}")
            if state.cto_output is None:
                state.cto_output = CTOOutput(
                    architecture="Implement the requested feature directly in the repo",
                    technical_notes=f"Agent error: {str(exc)}",
                )
            return state

    def _build_prompt(self, state: TaskState) -> str:
        lines = [
            f"Task title: {state.title}",
            f"Task description: {state.description}",
            f"Repo: {state.repo}",
            f"Branch: {state.branch}",
        ]

        if state.ceo_output is not None:
            lines.append("")
            lines.append("Business goals:")
            for goal in state.ceo_output.goals:
                lines.append(f"- {goal}")

            lines.append("")
            lines.append("KPIs to hit:")
            for metric, target in state.ceo_output.kpis.items():
                lines.append(f"- {metric}: {target}")

            lines.append("")
            lines.append("Constraints:")
            for name, value in state.ceo_output.constraints.items():
                lines.append(f"- {name}: {value}")

            if state.ceo_output.delegation_notes:
                lines.append("")
                lines.append(f"Delegation notes: {state.ceo_output.delegation_notes}")

        if state.acceptance_criteria:
            lines.append("")
            lines.append("Founder acceptance criteria:")
            for criterion in state.acceptance_criteria:
                lines.append(f"- {criterion}")

        if state.memory_hits:
            lines.append("")
            lines.append("Relevant past architecture patterns:")
            for hit in state.memory_hits[:2]:
                lines.append(f"- {hit.get('content', '')}")

        lines.append("")
        lines.append(
            "Produce the technical charter. "
            "Be specific about files and components to build."
        )

        return "\n".join(lines)


def _parse_cto_response(content: str) -> CTOOutput:
    clean = content.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]
        clean = clean.strip()

    try:
        data = json.loads(clean)
        return CTOOutput(
            architecture=data.get("architecture", ""),
            stack=data.get("stack", []),
            components=data.get("components", []),
            risks=data.get("risks", []),
            technical_notes=data.get("technical_notes", ""),
            repo_structure=data.get("repo_structure", []),
        )
    except Exception as exc:
        logger.warning("CTO JSON parse failed: %s", exc)
        return CTOOutput(
            architecture="Implement the requested feature directly in the repo",
            technical_notes=content[:300] if content else "",
        )
