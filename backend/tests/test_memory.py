import pytest
from datetime import datetime
from uuid import uuid4

from memory.long_term import delete_memory, ensure_collection, retrieve_memory, store_memory
from memory.short_term import delete_state, get_state, save_state
from models.schemas import MemoryEntry, Priority, TaskState, TaskStatus


@pytest.mark.asyncio
async def test_redis_state_storage():
    """Test saving and retrieving task state from Redis"""
    task_id = f"test-{uuid4()}"

    state = TaskState(
        task_id=task_id,
        title="Test Task",
        description="Test description",
        repo="owner/repo",
        branch="main",
        priority=Priority.MEDIUM,
        acceptance_criteria=["Test criteria"],
        context_refs=[],
        status=TaskStatus.PENDING,
    )

    await save_state(state)

    retrieved = await get_state(task_id)
    assert retrieved is not None
    assert retrieved.id == task_id
    assert retrieved.title == "Test Task"
    assert retrieved.status == TaskStatus.PENDING

    await delete_state(task_id)
    deleted = await get_state(task_id)
    assert deleted is None


@pytest.mark.asyncio
async def test_qdrant_vector_search():
    """Test storing and searching memories in Qdrant"""
    await ensure_collection()

    entry = MemoryEntry(
        id=str(uuid4()),
        content="IsolationForest requires n_samples >= 2 for training",
        source_task_id="test-task-1",
        agent="Developer",
        date=datetime.utcnow(),
        tags=["python", "ml", "debugging"],
    )

    await store_memory(entry)

    results = await retrieve_memory("error with isolation forest one sample", top_k=1)

    assert len(results) > 0
    assert results[0].content == entry.content
    assert results[0].score is not None
    assert results[0].score > 0.5

    await delete_memory(entry.id)
