from fastapi import APIRouter, Header, HTTPException

from models.schemas import OverrideRequest
from services.auth_service import extract_bearer_token
from services.escalation_service import get_inbox, apply_override
from services.task_service import abort_task

router = APIRouter(tags=["Inbox"])


@router.get("/inbox")
async def inbox_endpoint() -> list[dict]:
    return await get_inbox()


@router.patch("/tasks/{task_id}/override")
async def override_task(
    task_id: str,
    body: OverrideRequest,
    authorization: str | None = Header(default=None),
) -> dict:
    extract_bearer_token(authorization)
    try:
        return await apply_override(task_id, body.action)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch("/tasks/{task_id}/abort")
async def abort_task_endpoint(
    task_id: str,
    authorization: str | None = Header(default=None),
) -> dict:
    extract_bearer_token(authorization)
    await abort_task(task_id)
    return {"status": "aborted", "task_id": task_id}
