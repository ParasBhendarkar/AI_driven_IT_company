from fastapi import APIRouter, Header, Path

from models.schemas import GitHubBranch, GitHubRepository
from services.auth_service import extract_bearer_token
from services.github_service import get_branches, get_repositories


router = APIRouter(prefix="/github", tags=["GitHub"])


@router.get("/repositories", response_model=list[GitHubRepository])
async def repositories(authorization: str | None = Header(default=None)) -> list[GitHubRepository]:
    token = extract_bearer_token(authorization)
    return await get_repositories(token)


@router.get("/repositories/{repo_full_name:path}/branches", response_model=list[GitHubBranch])
async def branches(
    repo_full_name: str = Path(...),
    authorization: str | None = Header(default=None),
) -> list[GitHubBranch]:
    token = extract_bearer_token(authorization)
    return await get_branches(token, repo_full_name)
