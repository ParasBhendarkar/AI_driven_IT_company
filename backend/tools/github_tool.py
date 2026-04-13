import asyncio
from typing import Any

from fastapi import HTTPException, status
from github import Github
from github.GithubException import GithubException, UnknownObjectException

from tools.github_oauth import TIMEOUT


class GitHubTool:
    def __init__(self, repo: str, branch: str, access_token: str):
        self.repo_name = repo
        self.branch = branch
        self.access_token = access_token
        self.client = Github(
            login_or_token=access_token,
            timeout=int(TIMEOUT.read),
            per_page=100,
        )
        self.repo = self.client.get_repo(repo)

    async def ensure_branch_exists(self) -> str:
        try:
            branch = await asyncio.to_thread(self.repo.get_branch, self.branch)
            return branch.name
        except UnknownObjectException:
            default_branch_name = await asyncio.to_thread(lambda: self.repo.default_branch)
            source_branch = await asyncio.to_thread(self.repo.get_branch, default_branch_name)
            ref = f"refs/heads/{self.branch}"

            try:
                await asyncio.to_thread(
                    self.repo.create_git_ref,
                    ref=ref,
                    sha=source_branch.commit.sha,
                )
                return self.branch
            except GithubException as exc:
                raise self._github_http_exception(
                    exc,
                    default_detail=f"Failed to create branch '{self.branch}'",
                ) from exc
        except GithubException as exc:
            raise self._github_http_exception(
                exc,
                default_detail=f"Failed to access branch '{self.branch}'",
            ) from exc

    async def read_file(self, path: str) -> str | None:
        try:
            contents = await asyncio.to_thread(self.repo.get_contents, path, ref=self.branch)
        except UnknownObjectException:
            return None
        except GithubException as exc:
            raise self._github_http_exception(
                exc,
                default_detail=f"Failed to read file '{path}'",
            ) from exc

        if isinstance(contents, list):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Path '{path}' is a directory, not a file",
            )

        return contents.decoded_content.decode("utf-8")

    async def create_or_update_file(
        self,
        path: str,
        content: str,
        message: str,
    ) -> dict[str, Any]:
        await self.ensure_branch_exists()

        try:
            existing = await asyncio.to_thread(self.repo.get_contents, path, ref=self.branch)
        except UnknownObjectException:
            existing = None
        except GithubException as exc:
            raise self._github_http_exception(
                exc,
                default_detail=f"Failed to check file '{path}'",
            ) from exc

        try:
            if existing is None:
                result = await asyncio.to_thread(
                    self.repo.create_file,
                    path=path,
                    message=message,
                    content=content,
                    branch=self.branch,
                )
            else:
                if isinstance(existing, list):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Path '{path}' is a directory, not a file",
                    )

                result = await asyncio.to_thread(
                    self.repo.update_file,
                    path=path,
                    message=message,
                    content=content,
                    sha=existing.sha,
                    branch=self.branch,
                )
        except GithubException as exc:
            raise self._github_http_exception(
                exc,
                default_detail=f"Failed to write file '{path}'",
            ) from exc

        return {
            "path": path,
            "branch": self.branch,
            "commit_sha": result["commit"].sha,
        }

    async def open_pull_request(
        self,
        title: str,
        body: str,
        base: str | None = None,
    ) -> dict[str, Any]:
        await self.ensure_branch_exists()
        base_branch = base or await asyncio.to_thread(lambda: self.repo.default_branch)

        try:
            pr = await asyncio.to_thread(
                self.repo.create_pull,
                title=title,
                body=body,
                head=self.branch,
                base=base_branch,
            )
        except GithubException as exc:
            raise self._github_http_exception(
                exc,
                default_detail="Failed to open pull request",
            ) from exc

        return {
            "number": pr.number,
            "url": pr.html_url,
            "title": pr.title,
            "base": base_branch,
            "head": self.branch,
        }

    def _github_http_exception(self, exc: GithubException, default_detail: str) -> HTTPException:
        detail = default_detail

        if getattr(exc, "data", None):
            if isinstance(exc.data, dict):
                detail = exc.data.get("message") or detail

        status_code = exc.status if exc.status else status.HTTP_502_BAD_GATEWAY
        if status_code < 400:
            status_code = status.HTTP_502_BAD_GATEWAY

        return HTTPException(status_code=status_code, detail=detail)
