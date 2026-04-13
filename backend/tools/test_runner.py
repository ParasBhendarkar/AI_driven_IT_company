from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path


class TestRunner:
    """
    Phase 1 test runner scaffold.

    This is intentionally a stub for Module 1C. The full clone-and-pytest
    implementation lands in Module 2, but the public interface is ready now.
    """

    def __init__(
        self,
        repo: str | None = None,
        branch: str | None = None,
        access_token: str | None = None,
        timeout_seconds: int = 300,
    ) -> None:
        self.repo = repo or ""
        self.branch = branch or ""
        self.access_token = access_token
        self.timeout_seconds = timeout_seconds

    async def _run_command(
        self,
        command: list[str],
        cwd: str | Path | None = None,
    ) -> tuple[int, str, str]:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(cwd) if cwd else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            return 124, "", f"Command timed out after {self.timeout_seconds}s"

        return process.returncode, stdout.decode("utf-8", errors="replace"), stderr.decode(
            "utf-8",
            errors="replace",
        )

    def _build_error_report(self, error: str) -> dict:
        return {
            "status": "error",
            "summary": {"passed": 0, "failed": 1, "error": 0},
            "repo": self.repo,
            "branch": self.branch,
            "framework": "pytest",
            "phase": "module-1c-stub",
            "duration_seconds": 0.0,
            "tests": [
                {
                    "nodeid": "test_runner_error",
                    "outcome": "failed",
                    "call": {"longrepr": error},
                }
            ],
            "coverage": {"totals": {"percent_covered": 0.0}},
            "failures": [
                {
                    "type": "runner_error",
                    "message": error,
                }
            ],
            "stdout": "",
            "stderr": error,
        }

    async def run(
        self,
        repo: str | None = None,
        ref: str | None = None,
        task_id: str | None = None,
    ) -> dict:
        """
        Phase 1 stub.

        The final implementation will clone the repo, checkout the target
        branch, and execute pytest. For now we keep the interface stable and
        return deterministic mock data for the rest of the pipeline.
        """
        if repo:
            self.repo = repo
        if ref:
            self.branch = ref

        if "/" not in self.repo:
            return self._build_error_report("Repository must be in 'owner/repo' format")

        started_at = time.perf_counter()

        try:
            with tempfile.TemporaryDirectory(prefix="conductor-tests-") as temp_dir:
                repo_dir = Path(temp_dir) / self.repo.split("/", 1)[1]

                # Phase 1 note:
                # We intentionally do not clone or run pytest yet. This temp
                # directory scaffolding keeps the control flow close to the
                # final Module 2 implementation.
                mock_stdout = (
                    "Phase 1 stub: clone skipped, checkout skipped, pytest skipped.\n"
                    f"Prepared workspace at {repo_dir}"
                )

            duration = round(time.perf_counter() - started_at, 3)
            return {
                "status": "success",
                "summary": {"passed": 6, "failed": 0, "error": 0},
                "repo": self.repo,
                "branch": self.branch,
                "framework": "pytest",
                "phase": "module-1c-stub",
                "duration_seconds": duration,
                "tests": [
                    {"nodeid": "tests/test_stub.py::test_example_1", "outcome": "passed"},
                    {"nodeid": "tests/test_stub.py::test_example_2", "outcome": "passed"},
                    {"nodeid": "tests/test_stub.py::test_example_3", "outcome": "passed"},
                    {"nodeid": "tests/test_stub.py::test_example_4", "outcome": "passed"},
                    {"nodeid": "tests/test_stub.py::test_example_5", "outcome": "passed"},
                    {"nodeid": "tests/test_stub.py::test_example_6", "outcome": "passed"},
                ],
                "coverage": {
                    "totals": {"percent_covered": 82.4},
                },
                "failures": [],
                "stdout": mock_stdout,
                "stderr": "",
            }
        except Exception as exc:
            return self._build_error_report(str(exc))
