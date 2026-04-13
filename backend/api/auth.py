from fastapi import APIRouter, Header

from models.schemas import OAuthCodeRequest, OAuthTokenResponse, VerifyResponse
from services.auth_service import exchange_code, extract_bearer_token, verify_token


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/github/callback", response_model=OAuthTokenResponse)
async def github_callback(payload: OAuthCodeRequest) -> OAuthTokenResponse:
    access_token, user = await exchange_code(payload.code)
    return OAuthTokenResponse(access_token=access_token, user=user)


@router.get("/verify", response_model=VerifyResponse)
async def verify_auth(authorization: str | None = Header(default=None)) -> VerifyResponse:
    token = extract_bearer_token(authorization)
    user = await verify_token(token)
    return VerifyResponse(user=user)
