from __future__ import annotations

import logging
import time
from datetime import datetime

from agent.base import BaseAgent
from models.schemas import (
    TaskState,
    TaskStatus,
    QAResult,
    QAFailure,
    Severity,
    TestCounts,
)
from tools.test_runner import TestRunner

logger = logging.getLogger(__name__)

COVERAGE_THRESHOLD = 80.0
LATENCY_THRESHOLD_MS = 200.0


class QAAgent(BaseAgent):
    role = "QA"
    model = "claude-sonnet-4-5"

    async def run(self, state: TaskState) -> TaskState:
        start = time.time()
        attempt = state.retry_count + 1
        await self._publish(
            state.task_id,
            f"Running test suite (attempt {attempt})...",
        )

        runner = TestRunner()

        ref = None
        if state.dev_output:
            ref = getattr(state.dev_output, "commit_hash", None)

        try:
            report = await runner.run(
                repo=state.repo,
                ref=ref or state.branch,
                task_id=state.task_id,
            )
        except Exception as exc:
            logger.error("TestRunner failed: %s", exc)
            report = _synthetic_fail_report(str(exc))

        qa = _parse_report(report, attempt=attempt, task_id=state.task_id)
        qa = _check_acceptance(qa, state.acceptance_criteria or [])

        state.qa_result = qa
        state.retry_count = attempt

        latency = time.time() - start

        if qa.status == "pass":
            await self._publish(
                state.task_id,
                f"All tests passed — coverage {qa.coverage:.0f}%",
                event_type="success",
                payload=qa.model_dump(),
            )
        else:
            failure_summary = "; ".join(f.error for f in (qa.failures or [])[:2])
            await self._publish(
                state.task_id,
                f"Tests failed (attempt {attempt}) — {failure_summary}",
                event_type="error",
                payload=qa.model_dump(),
            )
            state.error_history = (state.error_history or []) + [failure_summary]
            state.last_error = failure_summary

        await self._log_call(
            task_id=state.task_id,
            action="qa_run",
            input_payload={"attempt": attempt, "ref": ref},
            output_payload={"status": qa.status, "failures": len(qa.failures)},
            latency_seconds=latency,
        )

        return state


def _parse_report(report: dict, attempt: int, task_id: str) -> QAResult:
    """Parse pytest-json-report dict into QAResult schema."""
    summary = report.get("summary", {})
    tests = report.get("tests", [])

    total_passed = summary.get("passed", 0)
    total_failed = summary.get("failed", 0)
    total_error = summary.get("error", 0)
    total_failed += total_error

    unit_pass = unit_fail = 0
    integ_pass = integ_fail = 0
    failures: list[QAFailure] = []

    for test in tests:
        node_id = test.get("nodeid", "")
        outcome = test.get("outcome", "passed")
        is_integ = "integration" in node_id or "e2e" in node_id

        if outcome == "passed":
            if is_integ:
                integ_pass += 1
            else:
                unit_pass += 1
        else:
            if is_integ:
                integ_fail += 1
            else:
                unit_fail += 1

            call_info = test.get("call", {}) or {}
            longrepr = call_info.get("longrepr", "") or str(test.get("longrepr", ""))
            short_msg = longrepr[:200] if longrepr else "Test failed"

            failures.append(
                QAFailure(
                    name=node_id,
                    error=short_msg,
                    severity=Severity.HIGH if "Error" in short_msg else Severity.MEDIUM,
                    location=node_id,
                )
            )

    if unit_pass + unit_fail == 0 and integ_pass + integ_fail == 0:
        unit_pass = total_passed
        unit_fail = total_failed

    coverage_pct = report.get("coverage", {}).get("totals", {}).get("percent_covered", 0.0)
    if not coverage_pct:
        coverage_pct = report.get("percent_covered", 0.0)

    passed = total_failed == 0 and total_passed > 0
    status = "pass" if passed else "fail"

    return QAResult(
        attempt=attempt,
        status=status,
        unitTests=TestCounts(**{"pass": unit_pass, "fail": unit_fail}),
        integrationTests=TestCounts(**{"pass": integ_pass, "fail": integ_fail}),
        coverage=round(coverage_pct, 1),
        latency="N/A",
        failures=failures,
    )


def _check_acceptance(qa: QAResult, criteria: list[str]) -> QAResult:
    """
    Check non-test acceptance criteria (coverage threshold etc).
    Adds synthetic failures if thresholds not met.
    """
    extra_failures = list(qa.failures)

    if qa.coverage < COVERAGE_THRESHOLD:
        extra_failures.append(
            QAFailure(
                name="coverage_threshold",
                error=f"Coverage {qa.coverage:.1f}% below required {COVERAGE_THRESHOLD:.0f}%",
                severity=Severity.MEDIUM,
                location="pytest --cov",
            )
        )
        qa.status = "fail"

    qa.failures = extra_failures
    qa.acceptance_met = qa.status == "pass"
    return qa


def _synthetic_fail_report(error_msg: str) -> dict:
    return {
        "summary": {"passed": 0, "failed": 1, "error": 0},
        "tests": [
            {
                "nodeid": "test_runner_error",
                "outcome": "failed",
                "call": {"longrepr": error_msg},
            }
        ],
        "coverage": {},
    }
