from fastapi import HTTPException, status

from models.schemas import GitHubUser
from tools.github_oauth import exchange_code_for_token, fetch_user


def extract_bearer_token(authorization: str | None) -> str:
    if authorization is None or not authorization.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    parts = authorization.split(" ", 1)

    if parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization must use Bearer scheme",
        )

    if len(parts) < 2 or not parts[1].strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing token in Authorization header",
        )

    return parts[1].strip()


async def exchange_code(code: str) -> tuple[str, GitHubUser]:
    if not code.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub OAuth code is required",
        )

    token = await exchange_code_for_token(code.strip())
    user = await fetch_user(token)
    return token, user


async def verify_token(token: str) -> GitHubUser:
    return await fetch_user(token)
