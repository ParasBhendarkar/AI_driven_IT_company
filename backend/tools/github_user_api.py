from urllib.parse import quote

import httpx
from fastapi import HTTPException, status

from config import settings
from models.schemas import GitHubBranch, GitHubRepository


TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)


def _github_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "conductor-api",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def list_repositories(token: str) -> list[GitHubRepository]:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, base_url=settings.GITHUB_API_BASE) as client:
            response = await client.get(
                "/user/repos",
                headers=_github_headers(token),
                params={
                    "per_page": 100,
                    "sort": "updated",
                    "affiliation": "owner,collaborator,organization_member",
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub repos fetch failed",
        ) from exc

    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired GitHub access token",
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub repos fetch failed",
        )

    return [
        GitHubRepository(
            id=repo["id"],
            name=repo["name"],
            full_name=repo["full_name"],
            private=bool(repo["private"]),
            default_branch=repo.get("default_branch") or "main",
            html_url=repo["html_url"],
        )
        for repo in response.json()
    ]


async def list_branches(token: str, repo_full_name: str) -> list[GitHubBranch]:
    owner, repo = _parse_repo_full_name(repo_full_name)
    owner = quote(owner, safe="")
    repo = quote(repo, safe="")

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, base_url=settings.GITHUB_API_BASE) as client:
            response = await client.get(
                f"/repos/{owner}/{repo}/branches",
                headers=_github_headers(token),
                params={"per_page": 100},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub branches fetch failed",
        ) from exc

    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired GitHub access token",
        )

    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found or no access",
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub branches fetch failed",
        )

    return [
        GitHubBranch(name=branch["name"], protected=branch.get("protected", False))
        for branch in response.json()
    ]


def _parse_repo_full_name(repo_full_name: str) -> tuple[str, str]:
    if "/" not in repo_full_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repository must be in owner/repo format",
        )

    owner, repo = repo_full_name.split("/", 1)
    owner = owner.strip()
    repo = repo.strip()

    if not owner or not repo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repository must be in owner/repo format",
        )

    return owner, repo
