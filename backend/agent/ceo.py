from __future__ import annotations

import json
import logging
import time

from agent.base import BaseAgent
from models.schemas import CEOOutput, Priority, TaskState

logger = logging.getLogger(__name__)


class CEOAgent(BaseAgent):
    role = "CEO/Manager"
    model = "ollama/qwen2.5-coder:3b"

    SYSTEM_PROMPT = """
You are the CEO planning agent inside an autonomous AI software company.

Respond with JSON only. Do not include prose, markdown, or code fences.
Return exactly this shape:
{
  "goals": ["2-4 measurable business outcomes"],
  "kpis": {"metric": "target"},
  "constraints": {"name": "value"},
  "priority": "Low|Medium|High|Critical",
  "approved": true,
  "delegation_notes": "context for CTO and Manager"
}

Rules:
- approved=false only if the request is harmful or impossible.
- goals must be measurable, specific outcomes, not vague intentions.
- kpis must be quantified, for example "p95_latency_ms": "200".
- constraints should capture deadlines, budget, risk, platform, or compliance limits when present.
"""

    async def run(self, state: TaskState) -> TaskState:
        logger.info("NODE ENTERED: ceo")
        start = time.time()

        try:
            await self._publish(
                state.task_id,
                "Analysing request and setting business objectives...",
            )

            prompt = self._build_prompt(state)
            messages = [{"role": "user", "content": prompt}]

            response = await self._call_llm(
                messages=messages,
                system=self.SYSTEM_PROMPT,
                temperature=0.2,
                max_tokens=1024,
            )

            if response is None:
                logger.warning("CEO _call_llm returned None, using fallback output")
                state.ceo_output = CEOOutput(goals=["Complete the requested task"], approved=True)
                return state

            tokens = response.usage.total_tokens if response.usage else 0
            content = response.choices[0].message.content or ""
            latency = time.time() - start

            ceo_output = _parse_ceo_response(content)
            state.ceo_output = ceo_output
            state.priority = ceo_output.priority

            await self._publish(
                state.task_id,
                f"Business mandate - {len(ceo_output.goals)} goals, priority {ceo_output.priority.value}",
                event_type="success",
                payload=ceo_output.model_dump(),
            )

            await self._log_call(
                task_id=state.task_id,
                action="ceo_planning",
                input_payload={"prompt_length": len(prompt)},
                output_payload=ceo_output.model_dump(),
                tokens_used=tokens,
                latency_seconds=latency,
            )
            return state

        except Exception as exc:
            logger.error(f"CEO run() crashed: {exc}")
            if state.ceo_output is None:
                state.ceo_output = CEOOutput(goals=["Complete the requested task"], approved=True)
            return state

    def _build_prompt(self, state: TaskState) -> str:
        lines = [
            f"Task title: {state.title}",
            f"Task description: {state.description}",
            f"Current priority: {state.priority.value}",
        ]

        if state.acceptance_criteria:
            lines.append("")
            lines.append("Acceptance criteria:")
            for criterion in state.acceptance_criteria:
                lines.append(f"- {criterion}")

        if state.memory_hits:
            lines.append("")
            lines.append("Past context:")
            for hit in state.memory_hits[:2]:
                lines.append(f"- {hit.get('content', '')}")

        if state.human_override:
            lines.append("")
            lines.append("Highest priority human override:")
            lines.append(state.human_override)

        return "\n".join(lines)


def _parse_ceo_response(content: str) -> CEOOutput:
    clean = content.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]
        clean = clean.strip()

    priority_map = {
        "Low": Priority.LOW,
        "Medium": Priority.MEDIUM,
        "High": Priority.HIGH,
        "Critical": Priority.CRITICAL,
    }

    try:
        data = json.loads(clean)
        return CEOOutput(
            goals=data.get("goals", []),
            kpis=data.get("kpis", {}),
            constraints=data.get("constraints", {}),
            priority=priority_map.get(data.get("priority"), Priority.MEDIUM),
            approved=bool(data.get("approved", True)),
            delegation_notes=data.get("delegation_notes", ""),
        )
    except Exception as exc:
        logger.warning("CEO JSON parse failed: %s", exc)
        return CEOOutput(goals=["Complete the requested task"], approved=True)
