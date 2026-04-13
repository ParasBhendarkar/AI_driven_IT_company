from __future__ import annotations

from datetime import datetime

from database import async_session_maker
from memory.long_term import retrieve_memory, store_memory, delete_memory
from models.db import MemoryEntryRow
from models.schemas import MemoryCreate, MemoryEntry


async def search_memory(query: str, top_k: int = 5) -> list[MemoryEntry]:
    return await retrieve_memory(query, top_k=top_k)


async def add_memory(data: MemoryCreate) -> MemoryEntry:
    import uuid

    entry = MemoryEntry(
        id=str(uuid.uuid4()),
        content=data.content,
        tags=data.tags,
        source_task_id=data.source_task_id,
        date=datetime.utcnow().isoformat(),
    )
    await store_memory(entry)

    async with async_session_maker() as session:
        row = MemoryEntryRow(
            id=entry.id,
            content=data.content,
            tags=data.tags,
            source_task_id=data.source_task_id,
        )
        session.add(row)
        await session.commit()

    return entry


async def remove_memory(entry_id: str) -> None:
    await delete_memory(entry_id)

    async with async_session_maker() as session:
        from sqlalchemy import delete
        from models.db import MemoryEntryRow

        await session.execute(delete(MemoryEntryRow).where(MemoryEntryRow.id == entry_id))
        await session.commit()


async def list_memories(limit: int = 50) -> list[dict]:
    async with async_session_maker() as session:
        from sqlalchemy import select

        result = await session.execute(select(MemoryEntryRow).order_by(MemoryEntryRow.created_at.desc()).limit(limit))
        rows = result.scalars().all()

    return [
        {
            "id": row.id,
            "content": row.content,
            "tags": row.tags or [],
            "sourceTaskId": row.source_task_id,
            "date": row.created_at.isoformat(),
            "score": row.score,
        }
        for row in rows
    ]
