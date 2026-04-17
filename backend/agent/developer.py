from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import time

from agent.base import BaseAgent
from config import settings
from core.retry import build_retry_context
from memory.short_term import get_task_token
from models.schemas import DevOutput, FileChange, TaskState
from tools.github_tool import GitHubTool

logger = logging.getLogger(__name__)


class DeveloperAgent(BaseAgent):
    role = "Developer"
    model = "ollama/qwen2.5-coder:3b"
    retry_model = settings.DEV_RETRY_MODEL

    SYSTEM_PROMPT = """
You are an expert software developer agent inside an autonomous AI company system.
 
You receive a task description, acceptance criteria, the base branch, the working
branch, and the current contents of relevant repository files.
 
Return ONLY valid JSON in this exact shape:
{
  "commit_message": "short git commit message",
  "pr_title": "pull request title",
  "pr_body": "pull request description",
  "files": [
    {
      "path": "relative/file.py",
      "summary": "one sentence summary of the change",
      "content": "full updated file content as plain UTF-8 string"
    }
  ]
}
 
Rules:
- BRANCH ISOLATION: You are working on branch {branch}. This branch already exists — the orchestrator created it before calling you. Do NOT create new branches. All commits go to {branch} only.
- If you are given a TDD test plan (lines starting with "--- TDD TEST PLAN"), your primary goal is to write code that makes those specific tests pass. Write the test files first if they do not exist, then write the implementation.
- Modify only files relevant to the task.
- Return full file contents for every changed file as plain UTF-8 in content.
- KEEP IMPORTS INTACT: If you use a new library (like math or json), you MUST include the import statement at the top of the file.
- Keep changes minimal and correct.
- Do not wrap the JSON in markdown fences.
"""

    async def run(self, state: TaskState) -> TaskState:
        logger.info("NODE ENTERED: developer")
        start = time.time()

        try:
            await self._publish(state.task_id, "Reading repository and planning changes...")

            access_token = await get_task_token(state.task_id) or settings.GITHUB_TOKEN
            if not access_token:
                raise RuntimeError("Missing GitHub token for Developer agent")

            work_branch = state.branch

            gh = GitHubTool(
                repo=state.repo,
                branch=work_branch,
                access_token=access_token,
            )
            await gh.ensure_branch_exists()
            base_branch = await asyncio.to_thread(lambda: gh.repo.default_branch)

            file_context = await self._read_file_context(gh, state)
            messages = [{"role": "user", "content": self._build_prompt(state, base_branch, work_branch, file_context)}]

            system_with_branch = self.SYSTEM_PROMPT.replace("{branch}", work_branch)
 
            response = await self._call_llm(
                messages=messages,
                system=system_with_branch,
                temperature=0.1,
                max_tokens=4096,
                timeout_seconds=240,
                json_mode=True,
            )
            tokens_total = response.usage.total_tokens if response and response.usage else 0
            if response is None:
                await self._publish(
                    state.task_id,
                    "Primary code generation timed out. Retrying with compact prompt...",
                    event_type="warning",
                )
                compact_messages = [
                    {
                        "role": "user",
                        "content": self._build_compact_prompt(state, base_branch, work_branch, file_context),
                    }
                ]
                response = await self._call_llm_with_model(
                    model=self.retry_model,
                    messages=compact_messages,
                    system=system_with_branch,
                    temperature=0.0,
                    max_tokens=2048,
                    timeout_seconds=180,
                    json_mode=True,
                )
                if response is not None and response.usage:
                    tokens_total += response.usage.total_tokens


            if response is None:
                state.last_error = "Developer model timed out"
                await self._publish(
                    state.task_id,
                    "Model timed out twice. Using deterministic fallback to ensure code is written.",
                    event_type="warning",
                )
                plan = await self._build_deterministic_fallback_plan(state, gh, file_context)
            else:
                try:
                    plan = await self._parse_plan_with_repair(
                        raw=response.choices[0].message.content or "",
                        messages=messages,
                        state=state,
                    )
                except Exception as exc:
                    await self._publish(
                        state.task_id,
                        "Structured developer output failed; using deterministic fallback implementation.",
                        event_type="warning",
                        payload={"error": str(exc)},
                    )
                    plan = await self._build_deterministic_fallback_plan(state, gh, file_context)

            if not plan.get("files"):
                raise RuntimeError("Developer produced no file edits")
            file_changes: list[FileChange] = []
            commit_sha: str | None = None

            context_map = {path: content for path, content in file_context}
            reviewed_file_contents: dict[str, str] = {}

            for change in plan["files"]:
                resolved_path = self._resolve_output_path(change["path"], context_map)
                content = self._decode_content(change)
                if context_map.get(resolved_path) == content:
                    await self._publish(
                        state.task_id,
                        f"Skipped {resolved_path} (no content change detected)",
                        event_type="warning",
                        payload={"path": resolved_path},
                    )
                    continue
                file_changes.append(
                    FileChange(
                        file_path=resolved_path,
                        change_type="modify",
                        summary=change["summary"],
                        patch=None,
                    )
                )
                reviewed_file_contents[resolved_path] = content
                await self._publish(
                    state.task_id,
                    f"Generated {resolved_path} - {change['summary']}",
                    payload={"path": resolved_path},
                )

            state.reviewed_file_contents = reviewed_file_contents

            if not file_changes:
                raise RuntimeError("Developer produced no material file changes")

            commit_message = plan.get("commit_message") or f"feat: update {state.title}"
            pr_title = plan.get("pr_title") or f"Implement {state.title}"
            pr_body = plan.get("pr_body") or f"Automated implementation for task: {state.title}"

            for change in file_changes:
                content = reviewed_file_contents[change.file_path]
                write_result = await gh.create_or_update_file(
                    path=change.file_path,
                    content=content,
                    message=commit_message,
                )
                commit_sha = write_result.get("commit_sha") or commit_sha
                await self._publish(
                    state.task_id,
                    f"Committed {change.file_path} to {work_branch}",
                    payload={"path": change.file_path, "commit_sha": write_result.get("commit_sha")},
                )

            pr_result = await gh.open_pull_request(
                title=pr_title,
                body=pr_body,
                base=base_branch,
            )

            summary = f"Generated {len(file_changes)} file(s), committed changes, and opened PR #{pr_result['number']}"

            state.dev_output = DevOutput(
                summary=summary,
                branch=work_branch,
                commit_hash=commit_sha,
                pr_number=pr_result["number"],
                commit_message=commit_message,
                pr_title=pr_title,
                pr_body=pr_body,
                files_changed=file_changes,
            )
            state.pr_number = pr_result["number"]
            state.commit_hash = commit_sha

            latency = time.time() - start

            await self._log_call(
                task_id=state.task_id,
                action="developer_run",
                input_payload={"prompt_length": len(messages[0]["content"])},
                output_payload={
                    "files_changed": len(file_changes),
                    "commit_hash": commit_sha,
                    "pr_number": pr_result["number"],
                },
                tokens_used=tokens_total,
                latency_seconds=latency,
            )

            await self._publish(
                state.task_id,
                summary,
                event_type="success",
                payload={"pr_number": pr_result["number"], "commit_hash": commit_sha},
            )

            return state

        except Exception as exc:
            logger.error(f"Developer run() crashed: {exc}")
            state.last_error = str(exc)
            state.dev_output = DevOutput(
                summary=f"Agent error: {str(exc)}",
                branch=state.branch,
            )
            return state

    async def _read_file_context(self, gh: GitHubTool, state: TaskState) -> list[tuple[str, str]]:
        context: list[tuple[str, str]] = []
        for path in self._extract_paths(state):
            for candidate in self._candidate_paths(path):
                content = await gh.read_file(candidate)
                if content is not None:
                    context.append((candidate, content))
                    await self._publish(state.task_id, f"Read file: {candidate}")
                    break
        return context

    def _build_prompt(
        self,
        state: TaskState,
        base_branch: str,
        work_branch: str,
        file_context: list[tuple[str, str]],
    ) -> str:
        lines = [
            f"Task: {state.title}",
            f"Description: {state.description}",
            f"Repository: {state.repo}",
            f"Base branch: {base_branch}",
            f"Working branch: {work_branch}",
            "",
            "Acceptance criteria:",
        ]
        for criterion in state.acceptance_criteria or []:
            lines.append(f"  - {criterion}")

        if state.qa_result and state.retry_count > 0:
            lines.append("")
            lines.append(build_retry_context(state.qa_result, state.memory_hits or []))

        if state.critic_output:
            root_cause = getattr(
                state.critic_output,
                "root_cause",
                getattr(state.critic_output, "summary", ""),
            )
            fix = getattr(
                state.critic_output,
                "fix",
                getattr(state.critic_output, "recommendation", ""),
            )
            lines.append("")
            lines.append("--- CRITIC ROOT CAUSE ANALYSIS ---")
            lines.append(f"Root cause: {root_cause}")
            lines.append(f"Suggested fix: {fix}")

        if state.memory_hits and state.retry_count == 0:
            lines.append("")
            lines.append("--- RELEVANT PAST KNOWLEDGE ---")
            for hit in state.memory_hits:
                lines.append(f"[{hit.get('score', 0):.0%}] {hit.get('content', '')}")

        if state.tl_review_feedback:
            lines.append("")
            lines.append("--- TEAM LEADER CODE REVIEW FEEDBACK ---")
            lines.append("The Team Leader rejected your previous submission.")
            lines.append(f"Specific issues to fix: {state.tl_review_feedback}")
            lines.append("Fix ONLY these issues. Do not change anything else.")

        if state.tl_final_feedback:
            lines.append("")
            lines.append("--- TEAM LEADER FINAL REVIEW FEEDBACK ---")
            lines.append("Final review rejected. Address these gaps:")
            lines.append(state.tl_final_feedback)

        if state.human_override:
            lines.append("")
            lines.append("HUMAN OVERRIDE INSTRUCTION (HIGHEST PRIORITY)")
            lines.append(state.human_override)
            lines.append("Follow this instruction exactly. It supersedes everything above.")

        lines.append("")
        lines.append("Repository files:")
        for path, content in file_context:
            lines.append("")
            lines.append(f"FILE: {path}")
            lines.append(content)

        return "\n".join(lines)

    def _build_compact_prompt(
        self,
        state: TaskState,
        base_branch: str,
        work_branch: str,
        file_context: list[tuple[str, str]],
    ) -> str:
        lines = [
            f"Task: {state.title}",
            f"Description: {state.description}",
            f"Repository: {state.repo}",
            f"Base branch: {base_branch}",
            f"Working branch: {work_branch}",
            "",
            "Acceptance criteria:",
        ]
        for criterion in state.acceptance_criteria or []:
            lines.append(f"  - {criterion}")

        lines.append("")
        lines.append("Target files:")
        if file_context:
            for path, _ in file_context:
                lines.append(f"  - {path}")
        else:
            for path in self._extract_paths(state):
                lines.append(f"  - {path}")

        if state.tl_review_feedback:
            lines.append("")
            lines.append(f"Previous review feedback: {state.tl_review_feedback}")

        return "\n".join(lines)

    def _extract_paths(self, state: TaskState) -> list[str]:
        paths = []
        if state.team_leader_output and state.team_leader_output.file_targets:
            paths.extend(state.team_leader_output.file_targets)
        
        text = "\n".join([state.title, state.description, *state.acceptance_criteria, *state.context_refs])
        matches = re.findall(r"\b[\w./-]+\.[A-Za-z0-9]+\b", text)
        paths.extend(matches)
        
        ordered = list(dict.fromkeys(paths))
        return ordered or ["README.md"]

    def _candidate_paths(self, path: str) -> list[str]:
        candidates = [path]
        if path.startswith("src/"):
            candidates.append(path[4:])
        if path.startswith("src/tests/"):
            candidates.append(f"tests/{path[len('src/tests/'):]}")
        if not path.startswith("src/"):
            candidates.append(f"src/{path}")
        if path.startswith("tests/"):
            candidates.append(path[len("tests/"):])
        return list(dict.fromkeys(candidates))

    def _parse_plan(self, raw: str) -> dict:
        clean = self._extract_json_object(raw.strip())
        data = json.loads(self._escape_json_controls(clean))
        for file_item in data.get("files", []):
            if "content" not in file_item and "content_b64" not in file_item:
                raise ValueError(
                    f"File item for path '{file_item.get('path', '')}' must include content or content_b64"
                )
        return {
            "commit_message": data["commit_message"],
            "pr_title": data["pr_title"],
            "pr_body": data["pr_body"],
            "files": data["files"],
        }

    async def _call_llm_with_model(
        self,
        model: str,
        messages: list[dict],
        system: str,
        temperature: float,
        max_tokens: int,
        timeout_seconds: int,
        json_mode: bool,
    ):
        original_model = self.model
        self.model = model
        try:
            return await self._call_llm(
                messages=messages,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout_seconds=timeout_seconds,
                json_mode=json_mode,
            )
        finally:
            self.model = original_model

    async def _parse_plan_with_repair(
        self,
        raw: str,
        messages: list[dict],
        state: TaskState,
    ) -> dict:
        try:
            return self._parse_plan(raw)
        except Exception as first_error:
            await self._publish(
                state.task_id,
                "Model output was malformed JSON, attempting auto-repair...",
                event_type="warning",
                payload={"error": str(first_error)},
            )

            repair_system = """
You are a JSON repair assistant.
Convert the provided malformed model output into strict valid JSON with no markdown fences.
Keep the exact semantic intent.
Use this exact schema:
{
  "commit_message": "string",
  "pr_title": "string",
  "pr_body": "string",
  "files": [
    {
      "path": "relative/file.py",
      "summary": "string",
      "content": "full updated file content as plain UTF-8 string"
    }
  ]
}
Only output JSON.
"""
            repair_messages = [
                {
                    "role": "user",
                    "content": (
                        "Original task prompt:\n"
                        f"{messages[0]['content']}\n\n"
                        "Malformed output to repair:\n"
                        f"{raw}"
                    ),
                }
            ]
            repair_response = await self._call_llm(
                messages=repair_messages,
                system=repair_system,
                temperature=0.0,
                max_tokens=4096,
                timeout_seconds=240,
                json_mode=True,
            )
            if repair_response is None:
                raise RuntimeError("Repair LLM call returned None")
            repaired_raw = repair_response.choices[0].message.content or ""
            try:
                return self._parse_plan(repaired_raw)
            except Exception:
                retry_system = """
You are a software developer agent that MUST return strict JSON only.
Return exactly this schema and nothing else:
{
  "commit_message": "string",
  "pr_title": "string",
  "pr_body": "string",
  "files": [
    {
      "path": "relative/path.py",
      "summary": "string",
      "content": "full updated file content as plain UTF-8 string"
    }
  ]
}
"""
                retry_response = await self._call_llm(
                    messages=messages,
                    system=retry_system,
                    temperature=0.0,
                    max_tokens=4096,
                    timeout_seconds=240,
                    json_mode=True,
                )
                if retry_response is None:
                    raise RuntimeError("Retry LLM call returned None")
                retry_raw = retry_response.choices[0].message.content or ""
                return self._parse_plan(retry_raw)

    async def _build_deterministic_fallback_plan(
        self,
        state: TaskState,
        gh: GitHubTool,
        file_context: list[tuple[str, str]],
    ) -> dict:
        context_map = {path: content for path, content in file_context}
        targets = self._extract_paths(state)
        if not targets:
            targets = ["TASK_IMPLEMENTATION.md"]

        files: list[dict] = []
        for raw_path in targets[:3]:
            path = self._pick_existing_or_default_path(context_map, raw_path)
            original = context_map.get(path)
            if original is None:
                original = await gh.read_file(path) or ""
            updated = self._apply_generic_fallback_patch(path, original, state)
            if updated != original:
                files.append(
                    {
                        "path": path,
                        "summary": "Add deterministic fallback scaffold for requested task",
                        "content": updated,
                    }
                )

        if not files:
            files.append(
                {
                    "path": "TASK_IMPLEMENTATION.md",
                    "summary": "Add task implementation notes scaffold",
                    "content": self._render_markdown_task_stub(state),
                }
            )

        return {
            "commit_message": "chore: add deterministic task scaffold",
            "pr_title": "Add deterministic fallback scaffold",
            "pr_body": "Adds generic implementation scaffolding so work can continue when LLM output fails.",
            "files": files,
        }

    def _resolve_output_path(self, path: str, context_map: dict[str, str]) -> str:
        if path in context_map:
            return path
        if path.startswith("src/") and path[4:] in context_map:
            return path[4:]
        if f"src/{path}" in context_map:
            return f"src/{path}"
        if path.startswith("tests/") and f"src/{path}" in context_map:
            return f"src/{path}"
        return path

    def _pick_existing_or_default_path(self, context_map: dict[str, str], default_path: str) -> str:
        if default_path in context_map:
            return default_path
        if f"src/{default_path}" in context_map:
            return f"src/{default_path}"
        if default_path.startswith("test_") and f"tests/{default_path}" in context_map:
            return f"tests/{default_path}"
        if default_path.startswith("test_"):
            return f"tests/{default_path}"
        return default_path

    def _apply_generic_fallback_patch(self, path: str, content: str, state: TaskState) -> str:
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if ext == "py":
            marker = "def task_implementation_placeholder("
            if marker in content:
                return content
            block = (
                "\n\ndef task_implementation_placeholder():\n"
                f"    \"\"\"TODO: {state.title}\"\"\"\n"
                f"    raise NotImplementedError(\"Implement task: {state.title}\")\n"
            )
            return (content.rstrip() + block + "\n") if content.strip() else block.lstrip("\n")
        if ext in {"js", "ts", "jsx", "tsx"}:
            marker = "taskImplementationPlaceholder"
            if marker in content:
                return content
            block = (
                "\n\nexport function taskImplementationPlaceholder() {\n"
                f"  throw new Error(\"Implement task: {state.title}\");\n"
                "}\n"
            )
            return (content.rstrip() + block) if content.strip() else block.lstrip("\n")
        if ext in {"java", "kt", "cs", "go", "rs", "cpp", "c", "h"}:
            comment = self._comment_prefix_for_ext(ext)
            marker = "TASK_IMPLEMENTATION_PLACEHOLDER"
            if marker in content:
                return content
            block = (
                f"\n\n{comment} TASK_IMPLEMENTATION_PLACEHOLDER\n"
                f"{comment} TODO: {state.title}\n"
                f"{comment} {state.description}\n"
            )
            return (content.rstrip() + block) if content.strip() else block.lstrip("\n")
        if ext in {"md", "txt"}:
            return self._render_markdown_task_stub(state) if not content.strip() else content.rstrip() + "\n\n" + self._render_markdown_task_stub(state)
        return (content.rstrip() + "\n\n" + self._render_markdown_task_stub(state)) if content.strip() else self._render_markdown_task_stub(state)

    def _render_markdown_task_stub(self, state: TaskState) -> str:
        lines = [
            "# Task Implementation Placeholder",
            "",
            f"- Title: {state.title}",
            f"- Description: {state.description}",
            "",
            "## Acceptance Criteria",
        ]
        if state.acceptance_criteria:
            lines.extend([f"- {c}" for c in state.acceptance_criteria])
        else:
            lines.append("- Add implementation details here.")
        return "\n".join(lines) + "\n"

    def _comment_prefix_for_ext(self, ext: str) -> str:
        if ext == "py":
            return "#"
        return "//"

    def _work_branch_name(self, state: TaskState) -> str:
        slug = re.sub(r"[^\w\s-]", "", state.title.lower())
        slug = re.sub(r"[\s_-]+", "-", slug).strip("-")[:50]
        return f"feat/{slug}"

    def _extract_json_object(self, raw: str) -> str:
        cleaned = raw
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```", 2)[1].replace("json", "", 1).strip()

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("Developer model did not return a JSON object")
        return cleaned[start : end + 1]

    def _escape_json_controls(self, raw: str) -> str:
        escaped: list[str] = []
        in_string = False
        escaping = False

        for char in raw:
            if in_string:
                if escaping:
                    escaped.append(char)
                    escaping = False
                    continue
                if char == "\\":
                    escaped.append(char)
                    escaping = True
                    continue
                if char == '"':
                    escaped.append(char)
                    in_string = False
                    continue
                if char == "\n":
                    escaped.append("\\n")
                    continue
                if char == "\r":
                    escaped.append("\\r")
                    continue
                if char == "\t":
                    escaped.append("\\t")
                    continue
                escaped.append(char)
                continue

            escaped.append(char)
            if char == '"':
                in_string = True

        return "".join(escaped)

    def _decode_content(self, file_item: dict) -> str:
        content_b64 = file_item.get("content_b64")
        if isinstance(content_b64, str) and content_b64:
            try:
                return base64.b64decode(content_b64).decode("utf-8")
            except Exception:
                logger.warning("Invalid content_b64 payload for path %s", file_item.get("path"))
        # Fallback: plain UTF-8 content key (preferred for lightweight models)
        return str(file_item.get("content", ""))

