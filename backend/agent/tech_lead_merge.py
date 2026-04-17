from __future__ import annotations
 
import logging
import time
 
from agent.base import BaseAgent
from models.schemas import TaskState, PullRequestSummary
 
logger = logging.getLogger(__name__)
 
 
class TechLeadMergeAgent(BaseAgent):
    """
    Fan-in agent for the Module parallel path.
    Receives all open PRs from parallel Developer branches.
    Merges them sequentially into the base branch using GitHubTool.
    Sets state.merge_commit_hash on success.
    """
    role = "Tech Lead"
    model = "ollama/qwen2.5-coder:3b"
 
    async def run(self, state: TaskState) -> TaskState:
        logger.info("NODE ENTERED: tech_lead_merge")
        start = time.time()
 
        from tools.github_tool import GitHubTool
        from memory.short_term import get_task_token
        from config import settings
 
        try:
            await self._publish(
                state.task_id,
                f"Merging {len(state.pull_requests)} PRs into base branch...",
            )
 
            access_token = await get_task_token(state.task_id) or settings.GITHUB_TOKEN
            if not access_token:
                raise RuntimeError("Missing GitHub token for TechLeadMerge agent")
 
            gh = GitHubTool(
                repo=state.repo,
                branch=state.branch,  # base branch
                access_token=access_token,
            )
 
            merged_count = 0
            failed_prs: list[int] = []
            last_merge_sha: str | None = None
 
            for pr_summary in state.pull_requests:
                try:
                    # Note: GitHubTool.merge_pull_request returns the merge SHA as a string
                    sha = await gh.merge_pull_request(
                        pr_number=pr_summary.pr_number,
                        commit_message=f"chore: merge feature branch {pr_summary.branch} [conductor]",
                    )
                    if sha:
                        last_merge_sha = sha
                        pr_summary.status = "merged"
                        merged_count += 1
                        try:
                            await gh.delete_branch(pr_summary.branch)
                            await self._publish(
                                state.task_id,
                                f"Deleted merged branch {pr_summary.branch}",
                                payload={"branch": pr_summary.branch},
                            )
                        except Exception as delete_exc:
                            logger.warning("Merged PR #%s but failed to delete branch %s: %s", pr_summary.pr_number, pr_summary.branch, delete_exc)
                            await self._publish(
                                state.task_id,
                                f"Merged PR #{pr_summary.pr_number} but could not delete branch {pr_summary.branch}",
                                event_type="warning",
                                payload={"branch": pr_summary.branch, "error": str(delete_exc)},
                            )
                        await self._publish(
                            state.task_id,
                            f"Merged PR #{pr_summary.pr_number} ({pr_summary.branch})",
                            event_type="success",
                            payload={"pr_number": pr_summary.pr_number, "sha": sha},
                        )
                    else:
                        pr_summary.status = "failed"
                        failed_prs.append(pr_summary.pr_number)
                except Exception as pr_exc:
                    logger.error("Failed to merge PR #%s: %s", pr_summary.pr_number, pr_exc)
                    pr_summary.status = "failed"
                    failed_prs.append(pr_summary.pr_number)
 
            state.merge_commit_hash = last_merge_sha
 
            if failed_prs:
                state.last_error = f"PRs failed to merge: {failed_prs}"
                await self._publish(
                    state.task_id,
                    f"Merge incomplete — {len(failed_prs)} PRs failed: {failed_prs}",
                    event_type="warning",
                )
            else:
                await self._publish(
                    state.task_id,
                    f"All {merged_count} PRs merged — SHA: {last_merge_sha}",
                    event_type="success",
                )
 
            latency = time.time() - start
            await self._log_call(
                task_id=state.task_id,
                action="tech_lead_merge",
                input_payload={"pr_count": len(state.pull_requests)},
                output_payload={
                    "merged": merged_count,
                    "failed": failed_prs,
                    "merge_sha": last_merge_sha,
                },
                latency_seconds=latency,
            )
 
            return state
 
        except Exception as exc:
            logger.error(f"TechLeadMerge run() crashed: {exc}")
            state.last_error = str(exc)
            return state
