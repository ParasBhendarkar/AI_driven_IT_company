import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from uuid import uuid4

from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from sentence_transformers import SentenceTransformer

from config import settings
from models.schemas import MemoryCreate, MemoryEntry


EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="memory")
_qdrant_client: QdrantClient | None = None
_embedder: SentenceTransformer | None = None


def get_qdrant() -> QdrantClient:
    global _qdrant_client

    if _qdrant_client is None:
        _qdrant_client = QdrantClient(url=settings.QDRANT_URL)

    return _qdrant_client


def _get_embedder() -> SentenceTransformer:
    global _embedder

    if _embedder is None:
        _embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)

    return _embedder


def _ensure_collection_sync() -> None:
    client = get_qdrant()
    collections = client.get_collections().collections
    exists = any(collection.name == settings.QDRANT_COLLECTION for collection in collections)

    if exists:
        return

    client.create_collection(
        collection_name=settings.QDRANT_COLLECTION,
        vectors_config=qdrant_models.VectorParams(
            size=EMBEDDING_DIMENSION,
            distance=qdrant_models.Distance.COSINE,
        ),
    )


async def ensure_collection() -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_executor, _ensure_collection_sync)


def embed(text: str) -> list[float]:
    model = _get_embedder()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


async def store_memory(memory: MemoryCreate | MemoryEntry) -> MemoryEntry:
    loop = asyncio.get_running_loop()
    await ensure_collection()
    entry = _normalize_memory(memory)
    vector = await loop.run_in_executor(_executor, embed, entry.content)
    client = get_qdrant()

    payload = entry.model_dump(by_alias=True)

    await loop.run_in_executor(
        _executor,
        lambda: client.upsert(
            collection_name=settings.QDRANT_COLLECTION,
            points=[
                qdrant_models.PointStruct(
                    id=entry.id,
                    vector=vector,
                    payload=payload,
                )
            ],
        ),
    )

    return entry


async def retrieve_memory(query: str, limit: int = 5, top_k: int | None = None) -> list[MemoryEntry]:
    loop = asyncio.get_running_loop()
    await ensure_collection()
    vector = await loop.run_in_executor(_executor, embed, query)
    client = get_qdrant()
    result_limit = top_k if top_k is not None else limit

    results = await loop.run_in_executor(
        _executor,
        lambda: _search_points(client, vector, result_limit),
    )

    memories: list[MemoryEntry] = []
    for result in results:
        payload = result.payload or {}
        payload["score"] = result.score
        memories.append(MemoryEntry.model_validate(payload))

    return memories


def _search_points(client: QdrantClient, vector: list[float], limit: int):
    if hasattr(client, "search"):
        return client.search(
            collection_name=settings.QDRANT_COLLECTION,
            query_vector=vector,
            limit=limit,
            with_payload=True,
        )

    response = client.query_points(
        collection_name=settings.QDRANT_COLLECTION,
        query=vector,
        limit=limit,
        with_payload=True,
    )
    return response.points


async def delete_memory(memory_id: str) -> None:
    loop = asyncio.get_running_loop()
    client = get_qdrant()

    await loop.run_in_executor(
        _executor,
        lambda: client.delete(
            collection_name=settings.QDRANT_COLLECTION,
            points_selector=qdrant_models.PointIdsList(points=[memory_id]),
        ),
    )


def _normalize_memory(memory: MemoryCreate | MemoryEntry) -> MemoryEntry:
    if isinstance(memory, MemoryEntry):
        return memory

    return MemoryEntry(
        id=str(uuid4()),
        content=memory.content,
        tags=memory.tags,
        sourceTaskId=memory.source_task_id,
        date=datetime.utcnow(),
        score=None,
    )
