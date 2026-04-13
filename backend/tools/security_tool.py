import asyncio


class SecurityTool:
    """Semgrep security scanner (Phase 2)"""

    async def run_semgrep(self, repo_path: str) -> dict:
        """Run Semgrep security scan - STUB for Phase 1"""
        await asyncio.sleep(0.1)  # Simulate scan
        return {
            "results": [],
            "errors": [],
        }
