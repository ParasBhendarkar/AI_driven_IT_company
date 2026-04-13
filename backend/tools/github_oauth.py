import httpx
from fastapi import HTTPException, status

from config import settings
from models.schemas import GitHubUser


TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)


async def exchange_code_for_token(code: str) -> str:
    payload = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "client_secret": settings.GITHUB_CLIENT_SECRET,
        "code": code,
        "redirect_uri": settings.GITHUB_REDIRECT_URI,
    }
    headers = {
        "Accept": "application/json",
        "User-Agent": "conductor-api",
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                settings.GITHUB_OAUTH_TOKEN_URL,
                data=payload,
                headers=headers,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="GitHub OAuth token exchange failed",
        ) from exc

    data = response.json()

    if response.status_code >= 400:
        detail = data.get("error_description") or data.get("error") or "GitHub OAuth token exchange failed"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
        )

    access_token = data.get("access_token")

    if not access_token:
        detail = data.get("error_description") or data.get("error") or "GitHub OAuth token exchange failed"
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)

    return access_token


async def fetch_user(token: str) -> GitHubUser:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "conductor-api",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, base_url=settings.GITHUB_API_BASE) as client:
            user_response = await client.get("/user", headers=headers)

            if user_response.status_code == status.HTTP_401_UNAUTHORIZED:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired GitHub access token",
                )

            if user_response.status_code >= 400:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"GitHub user fetch failed: {user_response.status_code}",
                )

            user_payload = user_response.json()
            email = user_payload.get("email")

            if not email:
                email = await fetch_primary_email(client, token)
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub user fetch failed",
        ) from exc

    return GitHubUser(
        login=user_payload["login"],
        name=user_payload.get("name"),
        avatar_url=user_payload.get("avatar_url"),
        email=email,
    )


async def fetch_primary_email(client: httpx.AsyncClient, token: str) -> str | None:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "conductor-api",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        response = await client.get("/user/emails", headers=headers)
    except httpx.HTTPError:
        return None

    if response.status_code != status.HTTP_200_OK:
        return None

    emails = response.json()
    return _pick_best_email(emails)


def _pick_best_email(emails: list[dict]) -> str | None:
    if not emails:
        return None

    for email_entry in emails:
        if email_entry.get("primary") and email_entry.get("verified"):
            return email_entry.get("email")

    for email_entry in emails:
        if email_entry.get("verified"):
            return email_entry.get("email")

    return emails[0].get("email")
