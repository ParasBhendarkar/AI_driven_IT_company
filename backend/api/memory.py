from fastapi import APIRouter, Query

from models.schemas import MemoryCreate, MemoryEntry
from services.memory_service import search_memory, add_memory, remove_memory, list_memories

router = APIRouter(tags=["Memory"])


@router.get("/memory")
async def list_memory_endpoint(limit: int = Query(50, ge=1, le=200)) -> list[dict]:
    return await list_memories(limit=limit)


@router.get("/memory/search")
async def search_memory_endpoint(
    q: str = Query(..., min_length=1),
    limit: int = Query(5, ge=1, le=20),
) -> list[MemoryEntry]:
    return await search_memory(q, top_k=limit)


@router.post("/memory", response_model=MemoryEntry, status_code=201)
async def add_memory_endpoint(data: MemoryCreate) -> MemoryEntry:
    return await add_memory(data)


@router.delete("/memory/{entry_id}", status_code=204)
async def delete_memory_endpoint(entry_id: str) -> None:
    await remove_memory(entry_id)
