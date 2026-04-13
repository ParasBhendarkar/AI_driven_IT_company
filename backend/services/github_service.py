from models.schemas import GitHubBranch, GitHubRepository
from tools.github_user_api import list_branches, list_repositories


async def get_repositories(token: str) -> list[GitHubRepository]:
    return await list_repositories(token)


async def get_branches(token: str, repo_full_name: str) -> list[GitHubBranch]:
    return await list_branches(token, repo_full_name)
